"""Question/history contracts shared by ordinary and streaming endpoints."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_QUESTION_LENGTH = 2000


class HistoryMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class Question(BaseModel):
    question: str
    history: list[HistoryMessage] = Field(default_factory=list, max_length=6)

    @field_validator("history")
    @classmethod
    def history_budget(cls, messages):
        if sum(len(message.content) for message in messages) > 24000:
            raise ValueError("History exceeds the 24000 character budget")
        return messages
