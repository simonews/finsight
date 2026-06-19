import io
import math
from typing import Any
import time

import numpy as np
import pandas as pd
import yfinance as yf
from celery.utils.log import get_task_logger


from app.core.cache import CACHE_TTL_SECONDS, get_redis_sync
from app.core.market_provider import fetch_ticker_info

logger = get_task_logger(__name__)

def _window_return_pct(series: "pd.Series", days: int) -> float | None:
    if len(series) <= days:
        return None
    past = float(series.iloc[-1 - days])
    last = float(series.iloc[-1])
    if past == 0:
        return None
    return round((last / past - 1.0) * 100.0, 2)


def _extract_prices(raw: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    try:
        prices = raw["Adj Close"]
    except KeyError:
        prices = raw["Close"]
    if isinstance(prices, pd.Series):
        prices = prices.to_frame(name=tickers[0])
    prices = prices.copy()
    prices.columns = [str(c).upper() for c in prices.columns]
    return prices.dropna(how="all")


def _get_prices(tickers: list[str]) -> pd.DataFrame:
    cache_key = "yf_cache:prices:" + ",".join(sorted(tickers))
    client = get_redis_sync()
    try:
        cached = client.get(cache_key)
        if cached is not None:
            logger.info("yfinance PRICES cache HIT for %s", tickers)
            return pd.read_json(io.StringIO(cached), orient="split")
    except Exception:
        pass
    logger.info("yfinance PRICES cache MISS for %s - downloading", tickers)
    raw = yf.download(tickers, period="1y", progress=False)
    if raw is None or raw.empty:
        return pd.DataFrame()
    prices = _extract_prices(raw, tickers)
    try:
        client.set(cache_key, prices.to_json(orient="split"), ex=CACHE_TTL_SECONDS)
    except Exception:
        pass
    return prices


def calculate_portfolio_metrics(positions: list[dict[str, Any]]) -> dict[str, Any]:
    if not positions:
        return {"error": "No positions provided"}

    tickers = [str(p["ticker"]).upper() for p in positions]
    quantities = {str(p["ticker"]).upper(): float(p["quantity"]) for p in positions}

    try:
        prices = _get_prices(tickers).dropna()
    except Exception as exc:
        return {"error": f"Market data download failed: {exc}"}

    if prices.empty or len(prices) < 2:
        return {"error": "Insufficient historical data to compute metrics"}

    available = [t for t in tickers if t in prices.columns]
    if not available:
        return {"error": "None of the requested tickers returned usable data"}

    prices = prices[available]
    latest = prices.iloc[-1]
    first = prices.iloc[0]

    market_values = {t: quantities[t] * float(latest[t]) for t in available}
    total_value = sum(market_values.values())
    if total_value <= 0:
        return {"error": "Total portfolio market value is zero"}

    weights = {t: market_values[t] / total_value for t in available}
    asset_returns = {t: float(latest[t] / first[t] - 1.0) for t in available}
    portfolio_return = sum(weights[t] * asset_returns[t] for t in available)

    daily_log_returns = np.log(prices / prices.shift(1)).dropna()
    weight_series = pd.Series(weights)
    portfolio_daily_log_returns = (daily_log_returns * weight_series).sum(axis=1)
    annualized_volatility = float(portfolio_daily_log_returns.std() * math.sqrt(252))

    result: dict[str, Any] = {
        "period": "1y",
        "tickers": available,
        "weights": {t: round(weights[t], 4) for t in available},
        "asset_returns_1y": {t: round(asset_returns[t], 4) for t in available},
        "portfolio_return_1y": round(portfolio_return, 4),
        "annualized_volatility": round(annualized_volatility, 4),
        "total_market_value": round(total_value, 2),
    }
    missing = [t for t in tickers if t not in available]
    if missing:
        result["missing_tickers"] = missing
    return result

def _download_close_prices(tickers: list[str], period: str, retries: int = 2) -> pd.DataFrame:
    raw = None
    for attempt in range(retries + 1):
        try:
            raw = yf.download(tickers, period=period, progress=False, auto_adjust=True)
        except Exception:
            raw = None
        if raw is not None and not raw.empty:
            break
        if attempt < retries:
            time.sleep(0.8)
    if raw is None or raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"].copy()
    else:
        closes = raw[["Close"]].copy()
        closes.columns = [tickers[0]]
    return closes.dropna(how="all")


def _get_cached_closes(tickers: list[str], period: str) -> pd.DataFrame:
    cache_key = f"yf_cache:hist:{','.join(tickers)}:{period}"
    client = None
    try:
        client = get_redis_sync()
        cached = client.get(cache_key)
        if cached:
            payload = cached.decode() if isinstance(cached, bytes) else cached
            return pd.read_json(io.StringIO(payload), orient="split")
    except Exception:
        client = None
    closes = _download_close_prices(tickers, period)
    if not closes.empty and client is not None:
        try:
            client.set(cache_key, closes.to_json(orient="split"), ex=CACHE_TTL_SECONDS)
        except Exception:
            pass
    return closes

def _extract_indicators(info: dict) -> dict:
    empty = {"fifty_two_week_high": None, "fifty_two_week_low": None,
             "avg_volume": None, "pe_ratio": None, "dividend_yield": None}
    if not info:
        return empty
    avg_vol = (
        info.get("averageVolume")
        or info.get("averageDailyVolume3Month")
        or info.get("averageVolume10days")
        or info.get("averageDailyVolume10Day")
    )
    high = info.get("fiftyTwoWeekHigh")
    low = info.get("fiftyTwoWeekLow")
    pe = info.get("trailingPE")
    raw_div = info.get("trailingAnnualDividendYield")
    if raw_div is not None:
        div = float(raw_div) * 100.0
    else:
        raw_div = info.get("dividendYield")
        div = (float(raw_div) if float(raw_div) > 1 else float(raw_div) * 100.0) if raw_div is not None else None
    return {
        "fifty_two_week_high": round(float(high), 4) if high is not None else None,
        "fifty_two_week_low": round(float(low), 4) if low is not None else None,
        "avg_volume": int(avg_vol) if avg_vol is not None else None,
        "pe_ratio": round(float(pe), 2) if pe is not None else None,
        "dividend_yield": round(div, 2) if div is not None else None,
    }


def build_portfolio_analytics(positions: list[dict], period: str = "1y") -> dict:
    empty = {
        "positions": [],
        "totals": {"cost_basis": 0.0, "current_value": 0.0, "pnl": 0.0, "pnl_pct": 0.0},
        "history": {"dates": [], "series": {}},
    }
    if not positions:
        return empty

    tickers = sorted({str(p["ticker"]).upper() for p in positions})
    closes = _get_cached_closes(tickers, period)
    if not closes.empty:
        closes.index = pd.to_datetime(closes.index)
    latest = closes.iloc[-1] if not closes.empty else None

    indicators_by_ticker: dict[str, dict] = {}
    for t in tickers:
        try:
            indicators_by_ticker[t] = _extract_indicators(fetch_ticker_info(t))
        except Exception:
            indicators_by_ticker[t] = _extract_indicators({})

    positions_out = []
    total_cost = 0.0
    total_value = 0.0
    for p in positions:
        ticker = str(p["ticker"]).upper()
        qty = float(p["quantity"])
        avg = float(p["average_price"])
        cost = qty * avg
        total_cost += cost

        current_price = None
        if latest is not None and ticker in closes.columns and pd.notna(latest[ticker]):
            current_price = float(latest[ticker])

        if current_price is not None:
            value = qty * current_price
            total_value += value
            pnl = value - cost
            pnl_pct = (pnl / cost * 100.0) if cost else 0.0
        else:
            value = pnl = pnl_pct = None

        ind = indicators_by_ticker.get(ticker, {})
        positions_out.append({
            "ticker": ticker,
            "quantity": qty,
            "average_price": round(avg, 4),
            "cost_basis": round(cost, 2),
            "current_price": round(current_price, 4) if current_price is not None else None,
            "current_value": round(value, 2) if value is not None else None,
            "pnl": round(pnl, 2) if pnl is not None else None,
            "pnl_pct": round(pnl_pct, 2) if pnl_pct is not None else None,
            "fifty_two_week_high": ind.get("fifty_two_week_high"),
            "fifty_two_week_low": ind.get("fifty_two_week_low"),
            "avg_volume": ind.get("avg_volume"),
        })

    totals = {
        "cost_basis": round(total_cost, 2),
        "current_value": round(total_value, 2),
        "pnl": round(total_value - total_cost, 2),
        "pnl_pct": round((total_value - total_cost) / total_cost * 100.0, 2) if total_cost else 0.0,
    }

    history = {"dates": [], "series": {}}
    if not closes.empty:
        history["dates"] = [d.strftime("%Y-%m-%d") for d in closes.index]
        history["series"] = {
            str(t): [round(float(v), 4) if pd.notna(v) else None for v in closes[t]]
            for t in closes.columns
        }

    metrics = {"annualized_volatility": 0.0, "portfolio_return_1y": 0.0, "per_ticker": []}
    if not closes.empty and latest is not None:
        qty_by_ticker: dict[str, float] = {}
        for p in positions:
            t = str(p["ticker"]).upper()
            qty_by_ticker[t] = qty_by_ticker.get(t, 0.0) + float(p["quantity"])

        market_value = {
            t: qty_by_ticker[t] * float(latest[t])
            for t in closes.columns
            if t in qty_by_ticker and pd.notna(latest[t])
        }
        total_mv = sum(market_value.values())
        weights = {t: (market_value[t] / total_mv if total_mv else 0.0) for t in market_value}

        returns_1y = {}
        for t in closes.columns:
            series = closes[t].dropna()
            if len(series) >= 2 and series.iloc[0] != 0:
                returns_1y[t] = float(series.iloc[-1] / series.iloc[0] - 1.0)

        portfolio_return = sum(weights.get(t, 0.0) * returns_1y.get(t, 0.0) for t in weights)

        annualized_vol = 0.0
        weighted_tickers = [t for t in closes.columns if t in weights]
        if weighted_tickers:
            log_returns = np.log(
                closes[weighted_tickers] / closes[weighted_tickers].shift(1)
            ).dropna()
            if len(log_returns) > 1:
                cov_daily = log_returns.cov()
                w_vec = np.array([weights[t] for t in weighted_tickers])
                portfolio_variance = float(w_vec @ cov_daily.values @ w_vec)
                annualized_vol = float(np.sqrt(max(portfolio_variance, 0.0) * 252))

        metrics = {
            "annualized_volatility": round(annualized_vol, 4),
            "portfolio_return_1y": round(portfolio_return, 4),
            "per_ticker": [
                {
                    "ticker": t,
                    "weight_pct": round(weights.get(t, 0.0) * 100.0, 2),
                    "return_1m_pct": _window_return_pct(closes[t].dropna(), 21),
                    "return_3m_pct": _window_return_pct(closes[t].dropna(), 63),
                    "return_6m_pct": _window_return_pct(closes[t].dropna(), 126),
                    "return_1y_pct": round(returns_1y.get(t, 0.0) * 100.0, 2),
                    "pe_ratio": indicators_by_ticker.get(t, {}).get("pe_ratio"),
                    "dividend_yield": indicators_by_ticker.get(t, {}).get("dividend_yield"),
                }
                for t in closes.columns
            ],
        }

    return {"positions": positions_out, "totals": totals, "history": history, "metrics": metrics}

def compute_ticker_trend(ticker: str, period: str = "1y") -> dict:
    ticker = ticker.upper()
    try:
        closes = _get_cached_closes([ticker], period)
    except Exception:
        closes = pd.DataFrame()
    try:
        info = fetch_ticker_info(ticker) or {}
    except Exception:
        info = {}

    if closes.empty or ticker not in closes.columns:
        return {"ticker": ticker, "error": "no_price_data"}
    series = closes[ticker].dropna()
    if len(series) < 2:
        return {"ticker": ticker, "error": "insufficient_data"}

    first = float(series.iloc[0])
    last = float(series.iloc[-1])
    return_1y_pct = round((last / first - 1.0) * 100.0, 2) if first else None

    log_ret = np.log(series / series.shift(1)).dropna()
    annualized_vol_pct = (
        round(float(log_ret.std() * math.sqrt(252)) * 100.0, 2) if len(log_ret) > 1 else None
    )

    period_high = round(float(series.max()), 4)
    period_low = round(float(series.min()), 4)
    running_max = series.cummax()
    max_drawdown_pct = round(float(((series - running_max) / running_max).min() * 100.0), 2)

    ind = _extract_indicators(info)
    high_52 = ind["fifty_two_week_high"] if ind["fifty_two_week_high"] is not None else period_high
    low_52 = ind["fifty_two_week_low"] if ind["fifty_two_week_low"] is not None else period_low
    pct_from_high = round((last / high_52 - 1.0) * 100.0, 2) if high_52 else None
    pct_from_low = round((last / low_52 - 1.0) * 100.0, 2) if low_52 else None

    return {
        "ticker": ticker,
        "name": info.get("longName") or info.get("shortName") or ticker,
        "sector": info.get("sector"),
        "period": period,
        "current_price": round(last, 4),
        "price_1y_ago": round(first, 4),
        "return_1m_pct": _window_return_pct(series, 21),
        "return_3m_pct": _window_return_pct(series, 63),
        "return_6m_pct": _window_return_pct(series, 126),
        "return_1y_pct": return_1y_pct,
        "annualized_volatility_pct": annualized_vol_pct,
        "period_high": period_high,
        "period_low": period_low,
        "fifty_two_week_high": high_52,
        "fifty_two_week_low": low_52,
        "pct_from_52w_high": pct_from_high,
        "pct_from_52w_low": pct_from_low,
        "max_drawdown_pct": max_drawdown_pct,
        "avg_volume": ind["avg_volume"],
        "pe_ratio": ind["pe_ratio"],
        "dividend_yield_pct": ind["dividend_yield"],
    }