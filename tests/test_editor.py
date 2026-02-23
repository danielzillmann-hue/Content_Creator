"""Tests for the Editor agent."""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from models.schemas import EditorOutput, NewsItem, ScoutReport


def _make_scout_report() -> ScoutReport:
    """Create a test ScoutReport."""
    return ScoutReport(
        generated_at=datetime(2026, 2, 23, 10, 0, 0),
        topics=["AI", "LLM"],
        items=[
            NewsItem(
                headline="Gemini 2.0 Launched",
                summary="Google launches Gemini 2.0 with improved reasoning.",
                source_url="https://blog.google/gemini2",
                linkedin_angle="Implications for AI-powered applications",
                topic_tags=["AI", "Google", "LLM"],
            ),
            NewsItem(
                headline="Claude 4 Announced",
                summary="Anthropic announces Claude 4 with enhanced safety.",
                source_url="https://anthropic.com/claude4",
                linkedin_angle="Safety-first AI development",
                topic_tags=["AI", "Anthropic"],
            ),
        ],
    )


class TestEditorAgent:
    """Unit tests for EditorAgent — mocks the Vertex AI client."""

    @patch("agents.editor.genai.Client")
    def test_write_produces_both_drafts(self, mock_client_cls):
        """Editor should produce both LinkedIn and Medium drafts."""
        from agents.editor import EditorAgent

        mock_instance = MagicMock()
        # First call = LinkedIn, second call = Medium
        mock_instance.models.generate_content.side_effect = [
            MagicMock(text="AI is changing everything.\n\n#AI #LLM"),
            MagicMock(text="# The Week in AI\n\n## Introduction\n\nBig things happening."),
        ]
        mock_client_cls.return_value = mock_instance

        editor = EditorAgent()
        output = editor.write(_make_scout_report())

        assert isinstance(output, EditorOutput)
        assert "AI" in output.linkedin_draft.content
        assert output.medium_draft.title == "The Week in AI"
        assert len(output.linkedin_draft.source_items) == 2

    @patch("agents.editor.genai.Client")
    def test_medium_title_extraction(self, mock_client_cls):
        """Editor should extract the title from the first markdown heading."""
        from agents.editor import EditorAgent

        mock_instance = MagicMock()
        mock_instance.models.generate_content.side_effect = [
            MagicMock(text="LinkedIn post content"),
            MagicMock(text="# My Custom Title\n\nArticle body here."),
        ]
        mock_client_cls.return_value = mock_instance

        editor = EditorAgent()
        output = editor.write(_make_scout_report())

        assert output.medium_draft.title == "My Custom Title"

    @patch("agents.editor.genai.Client")
    def test_medium_title_fallback(self, mock_client_cls):
        """Editor should use fallback title when no heading is present."""
        from agents.editor import EditorAgent

        mock_instance = MagicMock()
        mock_instance.models.generate_content.side_effect = [
            MagicMock(text="LinkedIn post"),
            MagicMock(text="No heading here, just text."),
        ]
        mock_client_cls.return_value = mock_instance

        editor = EditorAgent()
        output = editor.write(_make_scout_report())

        assert output.medium_draft.title == "AI/Tech Weekly Roundup"
