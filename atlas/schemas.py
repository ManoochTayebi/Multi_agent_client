from typing import Literal
from pydantic import BaseModel, Field

Intent = Literal['returns_investigation', 'product_discovery', 'order_tracking', 'personal_stylist']


class Plan(BaseModel):
    intents: list[Intent] = Field(default_factory=list, max_length=4)
    order_id: str | None = Field(default=None, pattern=r'^O\d{4,8}$')
    category: str | None = None
    budget_cents: int | None = Field(default=None, ge=0, le=1000000)
    size: Literal['XS', 'S', 'M', 'L', 'XL'] | None = None
    language: Literal['en', 'fr'] = 'en'
    rationale: str = Field(default='', max_length=500)


class AgentPlan(BaseModel):
    steps: list[str] = Field(min_length=1, max_length=5)


class JudgeVerdict(BaseModel):
    passed: bool
    issues: list[str] = Field(default_factory=list)


class SessionRequest(BaseModel):
    customer_id: str = Field(default='C0001', pattern=r'^C\d{4}$')


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class Decision(BaseModel):
    approve: bool
    reason: str = Field(min_length=3, max_length=500)
