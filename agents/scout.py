"""
Scout Agent — Discovers trending AI/tech news using Google Search grounding.

Uses Vertex AI's Google Search grounding feature via the google-genai SDK.
The model receives live Google Search results as context, enabling it to
find and summarize current news beyond its training cutoff.

Usage:
    scout = ScoutAgent()
    report = scout.search()  # Uses default topics from settings
    report = scout.search(topics=["AI agents", "Gemini"])
"""
import json
import logging
import re
from datetime import UTC, datetime
from typing import Optional

from google import genai
from google.genai.types import (
    GenerateContentConfig,
    GoogleSearch,
    HttpOptions,
    Tool,
)

from config.settings import settings
from models.schemas import NewsItem, ScoutReport

logger = logging.getLogger(__name__)


class ScoutAgent:
    """Finds trending AI/tech news using Vertex AI with Google Search grounding."""

    def __init__(self) -> None:
        self.client = genai.Client(
            vertexai=True,
            project=settings.GCP_PROJECT,
            location=settings.GCP_REGION,
            http_options=HttpOptions(api_version="v1"),
        )
        self.model = settings.SCOUT_MODEL
        self._search_tool = Tool(google_search=GoogleSearch())

    def search(self, topics: Optional[list[str]] = None) -> ScoutReport:
        """
        Search for trending news on the given topics.

        Args:
            topics: List of topic keywords. Defaults to settings.SCOUT_TOPICS.

        Returns:
            ScoutReport with discovered news items and summaries.
        """
        topics = topics or settings.SCOUT_TOPICS
        today = datetime.now(UTC).strftime("%Y-%m-%d")

        prompt = f"""You are a tech news scout. Today is {today}.

Search for the most interesting and trending news from the past 24 hours
about the following topics: {', '.join(topics)}.

For each news item you find, provide:
1. A concise headline
2. A 2-3 sentence summary of why this matters
3. The source URL
4. Why this would interest a tech-savvy LinkedIn audience

Find 3-5 of the most compelling stories. Prioritize:
- Breaking news and announcements
- Significant product launches or updates
- Research breakthroughs
- Industry shifts and trends

Return your findings as a JSON array with these fields:
headline, summary, source_url, linkedin_angle, topic_tags

Return ONLY the JSON array, no other text."""

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=GenerateContentConfig(
                    tools=[self._search_tool],
                    temperature=1.0,  # Google recommends 1.0 for grounded search
                ),
            )
            return self._parse_response(response, topics)

        except Exception as e:
            logger.error(f"Scout search failed: {e}", exc_info=True)
            raise

    def _parse_response(
        self, response: object, topics: list[str]
    ) -> ScoutReport:
        """Parse the Gemini response into a structured ScoutReport."""
        grounding_sources = self._extract_grounding_sources(response)
        news_items = self._extract_news_items(response.text, grounding_sources)

        return ScoutReport(
            generated_at=datetime.now(UTC),
            topics=topics,
            items=news_items,
            raw_response=response.text,
            grounding_sources=grounding_sources,
        )

    def _extract_grounding_sources(self, response: object) -> list[dict]:
        """Extract source attribution from grounding metadata."""
        sources: list[dict] = []
        try:
            if hasattr(response, "candidates") and response.candidates:
                candidate = response.candidates[0]
                metadata = getattr(candidate, "grounding_metadata", None)
                if metadata and hasattr(metadata, "grounding_chunks"):
                    for chunk in metadata.grounding_chunks:
                        web = getattr(chunk, "web", None)
                        if web:
                            sources.append(
                                {"uri": web.uri, "title": getattr(web, "title", "")}
                            )
        except Exception as e:
            logger.warning(f"Could not extract grounding sources: {e}")
        return sources

    def _extract_news_items(
        self, text: str, sources: list[dict]
    ) -> list[NewsItem]:
        """Extract structured news items from model response text."""
        # Try to extract JSON array from the response
        json_match = re.search(r"\[.*\]", text, re.DOTALL)
        if json_match:
            try:
                items_data = json.loads(json_match.group())
                return [
                    NewsItem(
                        headline=item.get("headline", ""),
                        summary=item.get("summary", ""),
                        source_url=item.get("source_url", ""),
                        linkedin_angle=item.get("linkedin_angle", ""),
                        topic_tags=item.get("topic_tags", []),
                    )
                    for item in items_data
                    if isinstance(item, dict)
                ]
            except json.JSONDecodeError:
                logger.warning(
                    "Failed to parse JSON from scout response, using fallback"
                )

        # Fallback: return single item with full text
        return [
            NewsItem(
                headline="AI/Tech News Roundup",
                summary=text[:500],
                source_url="",
                linkedin_angle="General AI/tech trends",
                topic_tags=["AI"],
            )
        ]
