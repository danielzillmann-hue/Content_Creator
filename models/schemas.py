"""
Pydantic models for data flowing between agents.

Pipeline: Scout → Editor → Dashboard → Publisher
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class NewsItem(BaseModel):
    """A single news item discovered by the Scout agent."""

    headline: str
    summary: str
    source_url: str = ""
    linkedin_angle: str = ""
    topic_tags: list[str] = Field(default_factory=list)


class ScoutReport(BaseModel):
    """Output of the Scout agent — a collection of discovered news items."""

    generated_at: datetime
    topics: list[str]
    items: list[NewsItem]
    raw_response: str = ""
    grounding_sources: list[dict] = Field(default_factory=list)


class LinkedInDraft(BaseModel):
    """A LinkedIn post draft produced by the Editor agent."""

    content: str
    source_items: list[str] = Field(default_factory=list)


class MediumDraft(BaseModel):
    """A Medium article draft produced by the Editor agent."""

    title: str
    content_markdown: str
    tags: list[str] = Field(default_factory=list)
    source_items: list[str] = Field(default_factory=list)


class EditorOutput(BaseModel):
    """Output of the Editor agent — LinkedIn + Medium drafts."""

    scout_report_id: str
    linkedin_draft: LinkedInDraft
    medium_draft: MediumDraft


class PublishResult(BaseModel):
    """Result of publishing to a platform."""

    platform: str  # "linkedin" or "medium"
    success: bool
    post_id: str = ""
    post_url: str = ""
    error: str = ""
    published_at: datetime


class ContentPipeline(BaseModel):
    """Full pipeline state stored in BigQuery."""

    id: str
    created_at: datetime
    scout_output: Optional[ScoutReport] = None
    editor_output: Optional[EditorOutput] = None
    status: str = "draft"  # draft, approved, rejected, published
    linkedin_result: Optional[PublishResult] = None
    medium_result: Optional[PublishResult] = None
    approved_by: str = ""
    approved_at: Optional[datetime] = None
