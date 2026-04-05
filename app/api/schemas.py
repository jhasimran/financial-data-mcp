from __future__ import annotations

from pydantic import BaseModel, Field


class SessionCreateResponse(BaseModel):
    session_id: str


class SessionStatusResponse(BaseModel):
    session_id: str
    has_data: bool
    source_count: int
    warning_count: int


class IngestResponse(BaseModel):
    session_id: str
    count: int
    sources: int
    warnings: list[str]


class ChatRequest(BaseModel):
    session_id: str
    question: str | None = Field(default=None)


class ChatResponse(BaseModel):
    session_id: str
    status: str
    answer: str
    tool_calls: list[str]
    supporting_data: dict
    warnings: list[str]
    missing_input: str | None = None
