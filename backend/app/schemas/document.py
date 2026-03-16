from typing import Any

from pydantic import BaseModel, Field


class DocumentCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    source_type: str = Field(min_length=1, max_length=64)
    content: str = Field(min_length=1)
    product_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentResponse(BaseModel):
    id: str
    title: str
    source_type: str
    product_id: str | None = None
    metadata: dict[str, Any]
