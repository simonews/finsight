import json
from typing import Any
import time
import pandas as pd

import yfinance as yf
from celery.utils.log import get_task_logger
from datetime import datetime, timezone

from app.core.cache import CACHE_TTL_SECONDS, get_redis_sync

logger = get_task_logger(__name__)


def fetch_ticker_info(ticker: str, retries: int = 1) -> dict[str, Any]:
    cache_key = f"yf_cache:info:{ticker.upper()}"
    client = get_redis_sync()
    try:
        cached = client.get(cache_key)
        if cached is not None:
            logger.info("yfinance INFO cache HIT for %s", ticker)
            return json.loads(cached)
    except Exception:
        pass
    logger.info("yfinance INFO cache MISS for %s - downloading", ticker)
    info: dict[str, Any] = {}
    for attempt in range(retries + 1):
        try:
            info = yf.Ticker(ticker).info
        except Exception:
            info = {}
        if info and info.get("regularMarketPrice") is not None:
            break
        if attempt < retries:
            time.sleep(0.8)
    if info and info.get("regularMarketPrice") is not None:
        try:
            client.set(cache_key, json.dumps(info, default=str), ex=CACHE_TTL_SECONDS)
        except Exception:
            pass
    return info

def _normalize_news_item(item: dict) -> dict | None:
    # nuovo schema yfinance: campi sotto "content"; vecchio schema: top-level
    content = item.get("content") if isinstance(item.get("content"), dict) else item
    title = content.get("title")
    if not title:
        return None
    provider = content.get("provider")
    publisher = provider.get("displayName") if isinstance(provider, dict) else content.get("publisher")
    summary = content.get("summary") or content.get("description")
    published = content.get("pubDate") or content.get("displayTime")
    if published is None and content.get("providerPublishTime") is not None:
        try:
            published = datetime.fromtimestamp(
                int(content["providerPublishTime"]), tz=timezone.utc
            ).isoformat()
        except Exception:
            published = None
    return {"title": title, "publisher": publisher, "published": published, "summary": summary}


def fetch_ticker_news(ticker: str, limit: int = 8, retries: int = 1) -> list[dict]:
    cache_key = f"yf_cache:news:{ticker.upper()}"
    client = get_redis_sync()
    try:
        cached = client.get(cache_key)
        if cached is not None:
            logger.info("yfinance NEWS cache HIT for %s", ticker)
            return json.loads(cached)
    except Exception:
        pass
    logger.info("yfinance NEWS cache MISS for %s - downloading", ticker)
    raw: list = []
    for attempt in range(retries + 1):
        try:
            raw = yf.Ticker(ticker).news or []
        except Exception:
            raw = []
        if raw:
            break
        if attempt < retries:
            time.sleep(0.8)
    items: list[dict] = []
    for it in raw:
        if not isinstance(it, dict):
            continue
        norm = _normalize_news_item(it)
        if norm is not None:
            items.append(norm)
        if len(items) >= limit:
            break
    if items:
        try:
            client.set(cache_key, json.dumps(items, default=str), ex=CACHE_TTL_SECONDS)
        except Exception:
            pass
    return items

def fetch_etf_holdings(ticker: str, limit: int = 10, retries: int = 1) -> list[dict]:
    cache_key = f"yf_cache:holdings:{ticker.upper()}"
    client = get_redis_sync()
    try:
        cached = client.get(cache_key)
        if cached is not None:
            logger.info("yfinance HOLDINGS cache HIT for %s", ticker)
            return json.loads(cached)
    except Exception:
        pass
    logger.info("yfinance HOLDINGS cache MISS for %s - downloading", ticker)
    holdings: list[dict] = []
    for attempt in range(retries + 1):
        try:
            fd = yf.Ticker(ticker).funds_data
            df = getattr(fd, "top_holdings", None)
            if df is not None and not df.empty:
                rows = []
                for symbol, row in df.iterrows():
                    hp = row.get("Holding Percent")
                    name = row.get("Name")
                    rows.append({
                        "ticker": str(symbol).upper(),
                        "name": str(name) if pd.notna(name) else None,
                        "weight_pct": round(float(hp) * 100.0, 2) if pd.notna(hp) else None,
                    })
                    if len(rows) >= limit:
                        break
                holdings = rows
        except Exception:
            holdings = []
        if holdings:
            break
        if attempt < retries:
            time.sleep(0.8)
    if holdings:
        try:
            client.set(cache_key, json.dumps(holdings, default=str), ex=CACHE_TTL_SECONDS)
        except Exception:
            pass
    return holdings

def fetch_dividends(ticker: str, years: int = 6, retries: int = 1) -> list[dict]:
    cache_key = f"yf_cache:dividends:{ticker.upper()}"
    client = get_redis_sync()
    try:
        cached = client.get(cache_key)
        if cached is not None:
            logger.info("yfinance DIVIDENDS cache HIT for %s", ticker)
            return json.loads(cached)
    except Exception:
        pass
    logger.info("yfinance DIVIDENDS cache MISS for %s - downloading", ticker)
    items: list[dict] = []
    for attempt in range(retries + 1):
        try:
            div = yf.Ticker(ticker).dividends
            if div is not None and not div.empty:
                cutoff = pd.Timestamp.now(tz=div.index.tz) - pd.DateOffset(years=years)
                div = div[div.index >= cutoff]
                items = [
                    {"date": idx.strftime("%Y-%m-%d"), "amount": round(float(val), 4)}
                    for idx, val in div.items()
                    if pd.notna(val)
                ]
        except Exception:
            items = []
        if items:
            break
        if attempt < retries:
            time.sleep(0.8)
    if items:
        try:
            client.set(cache_key, json.dumps(items, default=str), ex=CACHE_TTL_SECONDS)
        except Exception:
            pass
    return items

def fetch_analyst_targets(ticker: str) -> dict:
    info = fetch_ticker_info(ticker) or {}
    current = info.get("currentPrice") or info.get("regularMarketPrice")
    mean = info.get("targetMeanPrice")
    low = info.get("targetLowPrice")
    high = info.get("targetHighPrice")
    n = info.get("numberOfAnalystOpinions")
    rec = info.get("recommendationKey")
    upside = round((float(mean) / float(current) - 1.0) * 100.0, 2) if (current and mean) else None
    return {
        "current_price": round(float(current), 2) if current is not None else None,
        "target_low": round(float(low), 2) if low is not None else None,
        "target_mean": round(float(mean), 2) if mean is not None else None,
        "target_high": round(float(high), 2) if high is not None else None,
        "upside_pct": upside,
        "num_analysts": int(n) if n is not None else None,
        "recommendation": rec,
    }