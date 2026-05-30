import json
import os
import logging
from typing import Any

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an expert Wall Street quantitative analyst writing a private briefing "
    "for a client. You receive raw portfolio data and quantitative metrics "
    "(per-asset weights, 1-year return per asset, portfolio 1-year return, annualized volatility).\n"
    "Write the report in Italian, in a professional advisory tone, as flowing prose.\n"
    "STRICT RULES:\n"
    "- Do NOT use tables, bullet points, lists or headings. Narrative paragraphs only.\n"
    "- Base every statement EXCLUSIVELY on the figures provided. NEVER invent, guess or approximate. "
    "Do NOT mention alpha, beta, Sharpe or any metric absent from the input.\n"
    "- Always produce EXACTLY three paragraphs, in this fixed order, every time:\n"
    "  Paragraph 1 (Composizione): describe the portfolio composition citing the exact weight of each holding.\n"
    "  Paragraph 2 (Rischio e performance): comment on the annualized volatility, the portfolio 1-year return "
    "and the 1-year return of each individual asset, citing the exact values provided.\n"
    "  Paragraph 3 (Concentrazione e indicazione strategica): assess concentration vs diversification implied by the weights "
    "and give one forward-looking strategic consideration.\n"
    "- Be concise and consistent across runs. No preamble. Do NOT add a disclaimer yourself: one is appended automatically."
)

DISCLAIMER = (
    "\n\n_Questo report e' generato automaticamente a scopo puramente informativo e non "
    "costituisce consulenza finanziaria ne' una raccomandazione di investimento._"
)


class GenerativeAIAnalyzer:
    def __init__(self, model: str = "llama-3.3-70b-versatile") -> None:
        self._api_key = os.environ["GROQ_API_KEY"]
        self._model = model

    async def generate_portfolio_report(
        self, portfolio_data: dict[str, Any], market_data: dict[str, Any]
    ) -> str:
        user_prompt = (
            "Redigi il report narrativo per il seguente portafoglio, "
            "interpretando i dati invece di elencarli.\n\n"
            f"DATI PORTAFOGLIO:\n{json.dumps(portfolio_data, ensure_ascii=False)}\n\n"
            f"METRICHE QUANTITATIVE:\n{json.dumps(market_data, ensure_ascii=False)}"
        )

        logger.info(
            "Generating portfolio report",
            extra={"portfolio_id": portfolio_data.get("id")},
        )
        try:
            async with AsyncOpenAI(
                api_key=self._api_key,
                base_url="https://api.groq.com/openai/v1",
                timeout=30.0,
            ) as client:
                response = await client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.3,
                )
        except Exception:
            logger.exception("LLM report generation failed")
            raise
        logger.info(
            "Portfolio report generated",
            extra={"portfolio_id": portfolio_data.get("id")},
        )
        report = response.choices[0].message.content or ""
        return report + DISCLAIMER