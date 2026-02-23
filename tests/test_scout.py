"""Tests for the Scout agent."""
import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from models.schemas import NewsItem, ScoutReport


class TestScoutAgent:
    """Unit tests for ScoutAgent — mocks the Vertex AI client."""

    def _mock_response(self, text: str) -> MagicMock:
        """Create a mock Gemini response with grounding metadata."""
        mock_web = MagicMock()
        mock_web.uri = "https://example.com/article"
        mock_web.title = "Test Article"

        mock_chunk = MagicMock()
        mock_chunk.web = mock_web

        mock_metadata = MagicMock()
        mock_metadata.grounding_chunks = [mock_chunk]

        mock_candidate = MagicMock()
        mock_candidate.grounding_metadata = mock_metadata

        mock_response = MagicMock()
        mock_response.text = text
        mock_response.candidates = [mock_candidate]

        return mock_response

    @patch("agents.scout.genai.Client")
    def test_search_returns_scout_report(self, mock_client_cls):
        """Scout should return a ScoutReport with parsed news items."""
        from agents.scout import ScoutAgent

        items = [
            {
                "headline": "GPT-5 Released",
                "summary": "OpenAI releases GPT-5 with major improvements.",
                "source_url": "https://openai.com/gpt5",
                "linkedin_angle": "What this means for AI engineers",
                "topic_tags": ["AI", "LLM"],
            }
        ]
        mock_response = self._mock_response(json.dumps(items))
        mock_instance = MagicMock()
        mock_instance.models.generate_content.return_value = mock_response
        mock_client_cls.return_value = mock_instance

        scout = ScoutAgent()
        report = scout.search(topics=["AI"])

        assert isinstance(report, ScoutReport)
        assert len(report.items) == 1
        assert report.items[0].headline == "GPT-5 Released"
        assert report.topics == ["AI"]
        assert len(report.grounding_sources) == 1

    @patch("agents.scout.genai.Client")
    def test_search_fallback_on_invalid_json(self, mock_client_cls):
        """Scout should return a fallback item when JSON parsing fails."""
        from agents.scout import ScoutAgent

        mock_response = self._mock_response("Here are some trends I found...")
        mock_instance = MagicMock()
        mock_instance.models.generate_content.return_value = mock_response
        mock_client_cls.return_value = mock_instance

        scout = ScoutAgent()
        report = scout.search(topics=["AI"])

        assert len(report.items) == 1
        assert report.items[0].headline == "AI/Tech News Roundup"

    @patch("agents.scout.genai.Client")
    def test_search_handles_api_error(self, mock_client_cls):
        """Scout should raise when the API call fails."""
        from agents.scout import ScoutAgent

        mock_instance = MagicMock()
        mock_instance.models.generate_content.side_effect = RuntimeError("API error")
        mock_client_cls.return_value = mock_instance

        scout = ScoutAgent()
        with pytest.raises(RuntimeError, match="API error"):
            scout.search()
