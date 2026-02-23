"""Tests for the Publisher agents (LinkedIn + Medium)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from models.schemas import LinkedInDraft, MediumDraft


class TestLinkedInPublisher:
    """Unit tests for LinkedInPublisher."""

    @patch("agents.publisher.get_secret")
    def test_get_authorization_url(self, mock_secret):
        """Should generate a valid LinkedIn OAuth URL."""
        from agents.publisher import LinkedInPublisher

        mock_secret.side_effect = lambda k: {
            "linkedin-client-id": "test-client-id",
            "linkedin-client-secret": "test-secret",
            "linkedin-access-token": None,
        }.get(k)

        publisher = LinkedInPublisher()
        url = publisher.get_authorization_url(state="test-state")

        assert "linkedin.com/oauth/v2/authorization" in url
        assert "client_id=test-client-id" in url
        assert "state=test-state" in url
        assert "w_member_social" in url

    @patch("agents.publisher.get_secret")
    @pytest.mark.asyncio
    async def test_publish_post_success(self, mock_secret):
        """Should publish a post and return success result."""
        from agents.publisher import LinkedInPublisher

        mock_secret.side_effect = lambda k: {
            "linkedin-client-id": "test-id",
            "linkedin-client-secret": "test-secret",
            "linkedin-access-token": "test-token",
        }.get(k)

        publisher = LinkedInPublisher()
        publisher.user_id = "test-user-123"

        draft = LinkedInDraft(content="Test post content", source_items=["Test"])

        # Mock the httpx client
        with patch("agents.publisher.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.headers = {"x-restli-id": "urn:li:share:123"}
            mock_response.raise_for_status = MagicMock()

            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_ctx.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_ctx

            result = await publisher.publish_post(draft)

            assert result.success is True
            assert result.platform == "linkedin"
            assert result.post_id == "urn:li:share:123"


class TestMediumPublisher:
    """Unit tests for MediumPublisher."""

    @patch("agents.publisher.get_secret")
    @pytest.mark.asyncio
    async def test_publish_article_success(self, mock_secret):
        """Should publish an article and return success result."""
        from agents.publisher import MediumPublisher

        mock_secret.return_value = "test-medium-token"

        publisher = MediumPublisher()
        publisher.user_id = "test-medium-user"
        publisher.token = "test-medium-token"

        draft = MediumDraft(
            title="Test Article",
            content_markdown="# Test\n\nContent here.",
            tags=["AI", "test"],
        )

        with patch("agents.publisher.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {
                "data": {
                    "id": "medium-post-123",
                    "url": "https://medium.com/@user/test-article-123",
                }
            }

            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_ctx.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_ctx

            result = await publisher.publish_article(draft, publish_status="draft")

            assert result.success is True
            assert result.platform == "medium"
            assert result.post_url == "https://medium.com/@user/test-article-123"
