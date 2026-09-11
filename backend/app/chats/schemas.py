"""Pydantic request models for chat persistence."""

from pydantic import BaseModel, ConfigDict, Field


class SessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="New chat", min_length=1, max_length=200)


class SessionRename(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)


class MessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1)
    role: str = Field(default="user", pattern="^(user|assistant)$")
    status: str = Field(default="complete", max_length=30)
    response: str | None = None
    citations: list[dict] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class FeedbackCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rating: int = Field(ge=1, le=5)
    comment: str | None = None
    message_id: str | None = None
    session_id: str | None = None


class BookmarkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message_id: str = Field(min_length=1)
