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
    response: dict[str, object] | None = None
    citations: list[dict] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class MessageResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str | None = None
    content: str
    role: str
    status: str | None = None
    response: dict[str, object] | None = None
    citations: list[dict] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    feedback_rating: int | None = Field(default=None, ge=0, le=1)


class FeedbackCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rating: int = Field(ge=0, le=1)
    comment: str | None = None


class BookmarkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_id: str | None = Field(default=None, min_length=1)
    assistant_message_id: str | None = Field(default=None, min_length=1)
    user_message_id: str | None = Field(default=None, min_length=1)
    question: str | None = Field(default=None, min_length=1)
    answer: str | None = Field(default=None, min_length=1)
    citations: list[dict] = Field(default_factory=list)
    response: dict[str, object] | None = None


class BookmarkResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    source_session_id: str | None = None
    user_message_id: str | None = None
    assistant_message_id: str | None = None
    question: str
    answer: str
    citations: list[dict] = Field(default_factory=list)
    response: dict[str, object] | None = None
    created_at: str | None = None


class BookmarkStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    saved: bool
    item: BookmarkResponse | None = None


class SessionListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[dict] = Field(default_factory=list)
    next_cursor: str | None = None
