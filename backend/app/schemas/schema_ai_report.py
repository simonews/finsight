import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AIReportBase(BaseModel):
    report_text: str


class AIReportCreate(AIReportBase):
    portfolio_id: uuid.UUID


class AIReportRead(AIReportBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    portfolio_id: uuid.UUID
    generated_at: datetime