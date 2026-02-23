"""Tests for the ContentProcessor agent."""
import json
from unittest.mock import MagicMock, patch

import pytest

from models.schemas import ScoutReport


class TestContentProcessor:
    """Unit tests for ContentProcessor — mocks httpx and Vertex AI client."""

    def _mock_gemini_response(self, text: str) -> MagicMock:
        """Create a mock Gemini response."""
        mock_response = MagicMock()
        mock_response.text = text
        return mock_response

    @patch("agents.content_processor.httpx.Client")
    @patch("agents.content_processor.genai.Client")
    def test_process_url_returns_scout_report(
        self, mock_genai_cls, mock_httpx_cls
    ):
        """URL processing should fetch page, summarize, and return ScoutReport."""
        from agents.content_processor import ContentProcessor

        # Mock HTTP response
        mock_http_response = MagicMock()
        mock_http_response.text = (
            "<html><body><h1>AI Breakthrough</h1>"
            "<p>A major AI advancement was announced today.</p></body></html>"
        )
        mock_http_response.headers = {"content-type": "text/html"}
        mock_http_client = MagicMock()
        mock_http_client.__enter__ = MagicMock(return_value=mock_http_client)
        mock_http_client.__exit__ = MagicMock(return_value=False)
        mock_http_client.get.return_value = mock_http_response
        mock_httpx_cls.return_value = mock_http_client

        # Mock Gemini response
        summary = json.dumps(
            {
                "headline": "Major AI Breakthrough Announced",
                "summary": "Researchers announced a significant advancement in AI.",
                "linkedin_angle": "What this means for AI practitioners",
                "topic_tags": ["AI", "Research"],
            }
        )
        mock_genai_instance = MagicMock()
        mock_genai_instance.models.generate_content.return_value = (
            self._mock_gemini_response(summary)
        )
        mock_genai_cls.return_value = mock_genai_instance

        processor = ContentProcessor()
        report = processor.process_url("https://example.com/article")

        assert isinstance(report, ScoutReport)
        assert len(report.items) == 1
        assert report.items[0].headline == "Major AI Breakthrough Announced"
        assert report.source_type == "manual"
        assert report.source_url == "https://example.com/article"

    @patch("agents.content_processor.genai.Client")
    def test_process_text_returns_scout_report(self, mock_genai_cls):
        """Text processing should summarize and return ScoutReport."""
        from agents.content_processor import ContentProcessor

        summary = json.dumps(
            {
                "headline": "New Framework Released",
                "summary": "A new agent framework simplifies AI development.",
                "linkedin_angle": "Practical implications for developers",
                "topic_tags": ["AI", "Agents", "Developer Tools"],
            }
        )
        mock_genai_instance = MagicMock()
        mock_genai_instance.models.generate_content.return_value = (
            self._mock_gemini_response(summary)
        )
        mock_genai_cls.return_value = mock_genai_instance

        processor = ContentProcessor()
        report = processor.process_text(
            "A new agent framework was released that simplifies AI development.",
            title="New Framework Released",
        )

        assert isinstance(report, ScoutReport)
        assert len(report.items) == 1
        assert report.items[0].headline == "New Framework Released"
        assert report.source_type == "manual"
        assert report.source_url == ""

    @patch("agents.content_processor.genai.Client")
    def test_process_text_empty_raises_error(self, mock_genai_cls):
        """Empty text input should raise ValueError."""
        from agents.content_processor import ContentProcessor

        mock_genai_instance = MagicMock()
        mock_genai_cls.return_value = mock_genai_instance

        processor = ContentProcessor()
        with pytest.raises(ValueError, match="empty"):
            processor.process_text("")

    @patch("agents.content_processor.httpx.Client")
    @patch("agents.content_processor.genai.Client")
    def test_process_url_fallback_on_bad_json(
        self, mock_genai_cls, mock_httpx_cls
    ):
        """URL processing should use fallback when Gemini returns bad JSON."""
        from agents.content_processor import ContentProcessor

        # Mock HTTP response
        mock_http_response = MagicMock()
        mock_http_response.text = "<html><body>Some content</body></html>"
        mock_http_response.headers = {"content-type": "text/html"}
        mock_http_client = MagicMock()
        mock_http_client.__enter__ = MagicMock(return_value=mock_http_client)
        mock_http_client.__exit__ = MagicMock(return_value=False)
        mock_http_client.get.return_value = mock_http_response
        mock_httpx_cls.return_value = mock_http_client

        # Mock Gemini returning non-JSON
        mock_genai_instance = MagicMock()
        mock_genai_instance.models.generate_content.return_value = (
            self._mock_gemini_response("This is just plain text, no JSON here.")
        )
        mock_genai_cls.return_value = mock_genai_instance

        processor = ContentProcessor()
        report = processor.process_url("https://example.com/article")

        assert isinstance(report, ScoutReport)
        assert len(report.items) == 1
        # Fallback should still produce a valid NewsItem
        assert report.items[0].headline == "Content Summary"
        assert report.source_type == "manual"
