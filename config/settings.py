"""
Centralized configuration for AI Content Engine.

Uses environment variables with sensible defaults.
GCP auth: google.auth.default() locally, SA impersonation in prod.
"""
import os
from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class Settings:
    """Immutable application settings loaded from environment."""

    # GCP
    GCP_PROJECT: str = os.getenv("GCP_PROJECT", "dan-sandpit")
    GCP_REGION: str = os.getenv("GCP_REGION", "us-central1")

    # Vertex AI models
    SCOUT_MODEL: str = os.getenv("SCOUT_MODEL", "gemini-2.0-flash")
    EDITOR_MODEL: str = os.getenv("EDITOR_MODEL", "gemini-2.0-pro")

    # BigQuery
    BQ_DATASET: str = os.getenv("BQ_DATASET", "content_engine")
    BQ_TABLE: str = os.getenv("BQ_TABLE", "post_history")

    # LinkedIn OAuth
    LINKEDIN_REDIRECT_URI: str = os.getenv(
        "LINKEDIN_REDIRECT_URI",
        "http://localhost:8080/auth/linkedin/callback",
    )
    LINKEDIN_API_VERSION: str = os.getenv("LINKEDIN_API_VERSION", "202602")

    # Dashboard
    DASHBOARD_PORT: int = int(os.getenv("PORT", "8080"))

    # Scout topics (comma-separated in env)
    SCOUT_TOPICS: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.SCOUT_TOPICS:
            topics_str = os.getenv(
                "SCOUT_TOPICS",
                "AI,machine learning,LLM,generative AI,cloud computing",
            )
            object.__setattr__(
                self, "SCOUT_TOPICS", [t.strip() for t in topics_str.split(",")]
            )


settings = Settings()
