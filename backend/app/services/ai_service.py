import json
import logging
import os
from typing import Any

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an expert Wall Street Chief Investment Officer (CIO). You receive raw portfolio data (including exact sectors and weights) and advanced quantitative metrics (Returns, Volatility, Max Drawdown, Sharpe Ratio).\n"
    "Write a comprehensive institutional due-diligence report in Italian, in a professional, assertive advisory tone.\n"
    "STRICT RULES:\n"
    "- GOLDEN RULE: Do NOT merely list the assets, percentages, or returns. INTERPRET the data. Correlate the assets.\n"
    "- FORMATTING RESTRICTIONS: Do NOT use tables, headings (#, ##), or emojis. They break the frontend UI.\n"
    "- PERMITTED FORMATTING: You MUST use **bold text** to highlight key financial concepts, risk factors, metric names, and specific ticker symbols.\n"
    "- Structure the report EXACTLY into these 5 numbered sections (write '1. Panoramica Esecutiva', '2. Analisi Settoriale' etc. as plain text text to separate sections):\n"
    "  1. Panoramica Esecutiva: Synthesize the core macro-strategy of the portfolio (e.g., core-satellite, value vs growth, barbell).\n"
    "  2. Analisi Settoriale: Analyze the sector exposure using the provided 'sector' strings. Evaluate concentration risks and sector synergies.\n"
    "  3. Performance dei Singoli Asset: Explain the portfolio return by identifying which assets acted as growth drivers (outperformers) and which as defensive anchors or laggards.\n"
    "  4. Dinamiche di Rischio: Evaluate the **Annualized Volatility**, **Max Drawdown**, and **Sharpe Ratio** provided in the input. Explain how resilient the portfolio is to stress.\n"
    "  5. Insight Operativi (Bulleted list with '-'): Provide a concise list of at least 3 tactical rebalancing suggestions or macroeconomic vulnerabilities to monitor.\n"
    "- Be concise, dense with information, and consistent. Do NOT add a disclaimer yourself: one is appended automatically."
)

NEWS_SUMMARY_SYSTEM_PROMPT = (
    "You are a financial news editor writing a private briefing for a client. "
    "You receive a list of recent news items about a single company (each with title, publisher, "
    "publication date and, when available, a short summary).\n"
    "Write the briefing in Italian, in a professional and neutral tone, as flowing prose.\n"
    "STRICT RULES:\n"
    "- Synthesize the news in your OWN words. Do NOT copy headlines or summaries verbatim and do NOT "
    "use quotation marks around copied text.\n"
    "- Base the briefing EXCLUSIVELY on the items provided. NEVER invent news, figures, prices, "
    "ratings or events not present in the input.\n"
    "- Do NOT use tables, bullet points, lists or headings. Narrative paragraphs only.\n"
    "- Do NOT give buy/sell recommendations or price forecasts.\n"
    "- Produce at most two short paragraphs: group the items by recurring theme and convey the overall "
    "tone (positive, negative or mixed) that emerges, citing publishers generically (e.g. 'secondo Reuters').\n"
    "- No preamble. Do NOT add a disclaimer yourself: one is appended automatically."
)

TICKER_TREND_SYSTEM_PROMPT = (
    "You are an expert equity analyst writing a private briefing for a client. "
    "You receive DETERMINISTIC metrics for a single stock computed mostly over the last 12 months "
    "(company name, sector, current price, price one year ago, returns over 1 month / 3 months / 6 months / "
    "1 year, annualized volatility, 52-week high/low, percentage distance from the 52-week high and low, "
    "max drawdown, average daily volume, and when available the trailing P/E ratio and the dividend yield).\n"
    "Write the analysis in Italian, in a professional advisory tone, as flowing prose.\n"
    "STRICT RULES:\n"
    "- Do NOT use tables, bullet points, lists or headings. Narrative paragraphs only.\n"
    "- Base every statement EXCLUSIVELY on the figures provided. NEVER invent, guess or approximate, and "
    "do NOT mention metrics absent from the input (e.g. no alpha, beta, Sharpe or news).\n"
    "- If a value is null/absent (e.g. P/E or dividend yield), simply omit it: do NOT state it is unavailable.\n"
    "- Do NOT forecast future prices and do NOT give buy/sell recommendations.\n"
    "- Produce EXACTLY two concise paragraphs:\n"
    "  Paragraph 1 (Andamento): describe the price trajectory across the available horizons, citing the "
    "1-month, 3-month, 6-month and 1-year returns, the current price versus one year ago, and the position "
    "relative to the 52-week high and low.\n"
    "  Paragraph 2 (Rischio, valutazione e reddito): comment on the annualized volatility, the max drawdown "
    "and the average daily volume; and, only if present in the input, on the P/E ratio (valuation) and the "
    "dividend yield (income), citing the exact values.\n"
    "- No preamble. Do NOT add a disclaimer yourself: one is appended automatically."
)

PEERS_SYSTEM_PROMPT = (
    "You are an equity analyst. Given a target company (name, ticker, sector, industry), "
    "propose up to 6 well-known publicly listed companies in the SAME sector/industry that an "
    "investor might consider as comparables.\n"
    "STRICT RULES:\n"
    "- Output ONLY a JSON array, no prose, no markdown, no code fences. Each element: "
    '{"ticker": "<official exchange ticker>", "name": "<company name>", '
    '"reason": "<max 12 words, in Italian, why it is a peer>"}.\n'
    "- Use real, currently listed companies and their correct primary-exchange ticker symbols.\n"
    "- Do NOT include the target company itself.\n"
    "- If unsure a ticker is real, omit it. Better fewer correct tickers than invented ones.\n"
    "- No commentary outside the JSON array."
)

DISCLAIMER = (
    "\n\n_Questo report e' generato automaticamente a scopo puramente informativo e non "
    "costituisce consulenza finanziaria ne' una raccomandazione di investimento._"
)


class GenerativeAIAnalyzer:
    def __init__(self, model: str = "openai/gpt-oss-120b") -> None:
        self._api_key = os.environ["GROQ_API_KEY"]
        self._model = model

    async def _generate(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.3, append_disclaimer: bool = True
    ) -> str:
        try:
            async with AsyncOpenAI(
                api_key=self._api_key,
                base_url="https://api.groq.com/openai/v1",
                timeout=30.0,
            ) as client:
                response = await client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=temperature,
                )
        except Exception:
            logger.exception("LLM generation failed")
            raise
        content = response.choices[0].message.content or ""
        if append_disclaimer:
            return content + DISCLAIMER
        return content

    async def generate_portfolio_report(
        self, portfolio_data: dict[str, Any], market_data: dict[str, Any]
    ) -> str:
        user_prompt = (
            "Redigi il report narrativo per il seguente portafoglio, "
            "interpretando i dati invece di elencarli.\n\n"
            f"DATI PORTAFOGLIO:\n{json.dumps(portfolio_data, ensure_ascii=False)}\n\n"
            f"METRICHE QUANTITATIVE:\n{json.dumps(market_data, ensure_ascii=False)}"
        )
        logger.info("Generating portfolio report", extra={"portfolio_id": portfolio_data.get("id")})
        report = await self._generate(SYSTEM_PROMPT, user_prompt)
        logger.info("Portfolio report generated", extra={"portfolio_id": portfolio_data.get("id")})
        return report

    async def explain_ticker_trend(self, trend_data: dict[str, Any]) -> str:
        user_prompt = (
            "Spiega l'andamento a 12 mesi del seguente titolo, "
            "interpretando i dati invece di elencarli.\n\n"
            f"DATI TITOLO:\n{json.dumps(trend_data, ensure_ascii=False)}"
        )
        logger.info("Generating ticker trend explanation", extra={"ticker": trend_data.get("ticker")})
        return await self._generate(TICKER_TREND_SYSTEM_PROMPT, user_prompt)
    
    async def summarize_news(self, ticker: str, news_items: list[dict[str, Any]]) -> str:
        user_prompt = (
            f"Riassumi le notizie recenti sul titolo {ticker}, "
            "sintetizzandole con parole tue invece di elencarle.\n\n"
            f"NOTIZIE:\n{json.dumps(news_items, ensure_ascii=False)}"
        )
        logger.info("Generating news summary", extra={"ticker": ticker})
        return await self._generate(NEWS_SUMMARY_SYSTEM_PROMPT, user_prompt)
    
    async def suggest_sector_peers(
        self, ticker: str, name: str, sector: str | None, industry: str | None
    ) -> str:
        user_prompt = (
            "Proponi titoli comparabili per la seguente azienda. Rispondi SOLO con l'array JSON.\n\n"
            f"AZIENDA TARGET:\n{json.dumps({'ticker': ticker, 'name': name, 'sector': sector, 'industry': industry}, ensure_ascii=False)}"
        )
        logger.info("Generating sector peers", extra={"ticker": ticker})
        return await self._generate(PEERS_SYSTEM_PROMPT, user_prompt, temperature=0.2, append_disclaimer=False)