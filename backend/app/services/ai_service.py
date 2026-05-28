import json
import os
import logging
from typing import Any

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Sei uno spietato e cinico analista quantitativo di un hedge fund. "
    "Il tuo compito è destrutturare portafogli azionari con freddezza clinica. "
    "REGOLE RIGIDE VITALI: "
    "1. NON ripetere MAI lo stesso concetto. "
    "2. VIETATO usare frasi di circostanza, preamboli, introduzioni o conclusioni ovvie (es. 'La presente analisi...', 'In conclusione...'). "
    "3. Usa un tono distaccato, telegrafico e iper-tecnico. "
    "4. Formatta l'output rigorosamente in Markdown con queste tre sezioni esatte: "
    "## 1. Fotografia Asset\n"
    "## 2. Rischio e Sovraesposizione\n"
    "## 3. Inefficienze Strutturali."
)


class GenerativeAIAnalyzer:
    def __init__(self, model: str = "llama-3.1-8b-instant") -> None:
        self._api_key = os.environ["GROQ_API_KEY"]
        self._model = model

    async def generate_portfolio_report(
        self, portfolio_data: dict[str, Any], market_data: dict[str, Any]
    ) -> str:
        user_prompt = (
            f"Analizza i seguenti dati grezzi. Zero chiacchiere, dammi i fatti.\n"
            f"DATI PORTAFOGLIO:\n{json.dumps(portfolio_data, ensure_ascii=False)}\n\n"
            f"DATI MERCATO:\n{json.dumps(market_data, ensure_ascii=False)}"
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
        return response.choices[0].message.content or ""