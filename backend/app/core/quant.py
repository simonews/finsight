import math
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf


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


def calculate_portfolio_metrics(positions: list[dict[str, Any]]) -> dict[str, Any]:
    if not positions:
        return {"error": "No positions provided"}

    tickers = [str(p["ticker"]).upper() for p in positions]
    quantities = {str(p["ticker"]).upper(): float(p["quantity"]) for p in positions}

    try:
        raw = yf.download(tickers, period="1y", progress=False)
    except Exception as exc:
        return {"error": f"Market data download failed: {exc}"}

    if raw is None or raw.empty:
        return {"error": "No market data available for the requested tickers"}

    prices = _extract_prices(raw, tickers).dropna()
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