"""
Content Processor — Converts user-provided URLs or text into ScoutReports.

Enables manual content creation: the user provides a web link or text
description, and this processor packages it into a ScoutReport that the
existing EditorAgent can consume directly.

Usage:
    processor = ContentProcessor()
    report = processor.process_url("https://example.com/article")
    report = processor.process_text("My thoughts on AI agents...")
"""
import json
import logging
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Optional

import httpx
from google import genai
from google.genai.types import GenerateContentConfig, HttpOptions

from config.settings import settings
from models.schemas import NewsItem, ScoutReport

logger = logging.getLogger(__name__)


class _HTMLTextExtractor(HTMLParser):
    """Simple HTML-to-text converter that strips tags and scripts."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip:
            text = data.strip()
            if text:
                self._parts.append(text)

    def get_text(self) -> str:
        return "\n".join(self._parts)


def _html_to_text(html: str) -> str:
    """Extract readable text from HTML, stripping tags and scripts."""
    extractor = _HTMLTextExtractor()
    extractor.feed(html)
    return extractor.get_text()


class ContentProcessor:
    """Processes user-provided content (URL or text) into a ScoutReport."""

    def __init__(self) -> None:
        self.client = genai.Client(
            vertexai=True,
            project=settings.GCP_PROJECT,
            location=settings.GCP_REGION,
            http_options=HttpOptions(api_version="v1"),
        )
        self.model = settings.SCOUT_MODEL  # Gemini Flash for summarization

    def process_url(self, url: str) -> ScoutReport:
        """
        Fetch a web page and generate a ScoutReport from its content.

        Args:
            url: The web URL to fetch and process.

        Returns:
            ScoutReport with a single NewsItem summarizing the page.
        """
        logger.info(f"Processing URL: {url}")

        # Fetch the page
        page_text = self._fetch_url(url)
        if not page_text:
            raise ValueError(f"Could not fetch content from {url}")

        # Truncate to avoid exceeding token limits
        max_chars = 15000
        if len(page_text) > max_chars:
            page_text = page_text[:max_chars] + "\n\n[Content truncated...]"

        # Summarize with Gemini
        news_item = self._summarize_content(page_text, source_url=url)

        return ScoutReport(
            generated_at=datetime.now(UTC),
            topics=news_item.topic_tags,
            items=[news_item],
            raw_response=page_text[:2000],
            source_type="manual",
            source_url=url,
        )

    def process_text(
        self, text: str, title: Optional[str] = None
    ) -> ScoutReport:
        """
        Generate a ScoutReport from user-provided text.

        Args:
            text: Free-form text description or topic.
            title: Optional title for the content.

        Returns:
            ScoutReport with a single NewsItem based on the text.
        """
        logger.info("Processing manual text input")

        if not text.strip():
            raise ValueError("Text content cannot be empty")

        news_item = self._summarize_content(
            text, title=title, source_url=""
        )

        return ScoutReport(
            generated_at=datetime.now(UTC),
            topics=news_item.topic_tags,
            items=[news_item],
            raw_response=text[:2000],
            source_type="manual",
            source_url="",
        )

    def _fetch_url(self, url: str) -> str:
        """Fetch a URL and return its text content."""
        try:
            with httpx.Client(
                follow_redirects=True,
                timeout=30.0,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (compatible; AIContentEngine/1.0)"
                    )
                },
            ) as client:
                response = client.get(url)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "")
                if "text/html" in content_type:
                    return _html_to_text(response.text)
                else:
                    # Plain text or other readable format
                    return response.text

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching {url}: {e}")
            raise ValueError(f"Failed to fetch URL (HTTP {e.response.status_code})")
        except httpx.RequestError as e:
            logger.error(f"Request error fetching {url}: {e}")
            raise ValueError(f"Failed to fetch URL: {e}")

    def _summarize_content(
        self,
        content: str,
        source_url: str = "",
        title: Optional[str] = None,
    ) -> NewsItem:
        """Use Gemini to summarize content into a NewsItem."""
        title_hint = f"\nThe user provided this title: {title}" if title else ""

        prompt = f"""Analyze the following content and extract key information for a
LinkedIn post and Medium article.{title_hint}

CONTENT:
{content}

Return a JSON object with these fields:
- headline: A compelling headline summarizing the key point (max 15 words)
- summary: A 2-3 sentence summary of the main takeaway
- linkedin_angle: Why this would interest a tech-savvy LinkedIn audience (1-2 sentences)
- topic_tags: An array of 3-5 relevant topic tags (e.g., ["AI", "LLMs", "productivity"])

Return ONLY the JSON object, no other text."""

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=GenerateContentConfig(
                    temperature=0.3,  # Lower temp for factual extraction
                    max_output_tokens=1024,
                ),
            )
            return self._parse_summary(response.text, source_url)

        except Exception as e:
            logger.error(f"Summarization failed: {e}", exc_info=True)
            # Fallback: create a basic NewsItem from the content
            return NewsItem(
                headline=title or "User-Provided Content",
                summary=content[:300],
                source_url=source_url,
                linkedin_angle="Insights from curated content",
                topic_tags=["AI", "Technology"],
            )

    def _parse_summary(self, text: str, source_url: str) -> NewsItem:
        """Parse the Gemini summary response into a NewsItem."""
        # Try to extract JSON from the response
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return NewsItem(
                    headline=data.get("headline", ""),
                    summary=data.get("summary", ""),
                    source_url=source_url,
                    linkedin_angle=data.get("linkedin_angle", ""),
                    topic_tags=data.get("topic_tags", []),
                )
            except json.JSONDecodeError:
                logger.warning("Failed to parse JSON from summary response")

        # Fallback
        return NewsItem(
            headline="Content Summary",
            summary=text[:300],
            source_url=source_url,
            linkedin_angle="Insights from curated content",
            topic_tags=["AI", "Technology"],
        )
