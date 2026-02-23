"""
Publisher Agent — Handles API integrations for LinkedIn and Medium.

LinkedIn: Full OAuth 2.0 (3-legged) flow with token management via Secret Manager.
Medium: Integration token-based publishing.

LinkedIn OAuth flow:
1. User visits /auth/linkedin on the Dashboard
2. Redirect to LinkedIn authorization URL
3. LinkedIn redirects back to /auth/linkedin/callback with auth code
4. Exchange code for access token (valid 60 days)
5. Store token in Secret Manager

Usage:
    linkedin = LinkedInPublisher()
    url = linkedin.get_authorization_url(state="csrf-token")
    # ... user completes OAuth ...
    result = await linkedin.publish_post(draft)

    medium = MediumPublisher()
    result = await medium.publish_article(draft)
"""
import logging
from datetime import UTC, datetime
from typing import Optional
from urllib.parse import urlencode

import httpx

from config.secrets import get_secret
from config.settings import settings
from models.schemas import LinkedInDraft, MediumDraft, PublishResult

logger = logging.getLogger(__name__)

# LinkedIn API constants
LINKEDIN_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_API_BASE = "https://api.linkedin.com"
LINKEDIN_POSTS_URL = f"{LINKEDIN_API_BASE}/rest/posts"
LINKEDIN_USERINFO_URL = f"{LINKEDIN_API_BASE}/v2/userinfo"

# Medium API constants
MEDIUM_API_BASE = "https://api.medium.com/v1"


class LinkedInPublisher:
    """Handles LinkedIn OAuth and post creation via the Posts API."""

    def __init__(self) -> None:
        self.client_id: Optional[str] = None
        self.client_secret: Optional[str] = None
        self.access_token: Optional[str] = None
        self.user_id: Optional[str] = None

    def _load_credentials(self) -> None:
        """Load LinkedIn credentials from Secret Manager."""
        self.client_id = get_secret("linkedin-client-id")
        self.client_secret = get_secret("linkedin-client-secret")
        self.access_token = get_secret("linkedin-access-token")
        if not self.client_id or not self.client_secret:
            raise ValueError(
                "LinkedIn client credentials not configured in Secret Manager. "
                "See docs/LINKEDIN_SETUP.md for setup instructions."
            )

    def get_authorization_url(self, state: str) -> str:
        """
        Generate the LinkedIn OAuth authorization URL.

        The user must visit this URL to grant permission. After approval,
        LinkedIn redirects to the configured redirect URI with an auth code.

        Args:
            state: CSRF protection token (random string, verify on callback).

        Returns:
            The full LinkedIn authorization URL.
        """
        self._load_credentials()
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": settings.LINKEDIN_REDIRECT_URI,
            "state": state,
            "scope": "w_member_social openid profile",
        }
        return f"{LINKEDIN_AUTH_URL}?{urlencode(params)}"

    async def exchange_code_for_token(self, code: str) -> dict:
        """
        Exchange authorization code for access token.

        The code has a 30-minute lifespan. Access tokens are valid for 60 days.

        Args:
            code: The authorization code from LinkedIn callback.

        Returns:
            Token response dict with access_token, expires_in, etc.
        """
        self._load_credentials()
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    LINKEDIN_TOKEN_URL,
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "redirect_uri": settings.LINKEDIN_REDIRECT_URI,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                response.raise_for_status()
                token_data = response.json()

                self.access_token = token_data["access_token"]
                self._store_token(self.access_token)

                return token_data
            except httpx.HTTPStatusError as e:
                logger.error(
                    f"LinkedIn token exchange failed: {e.response.status_code} "
                    f"{e.response.text}"
                )
                raise

    async def get_user_profile(self) -> dict:
        """
        Fetch the authenticated user's LinkedIn profile.

        Uses the OpenID Connect userinfo endpoint to get the person URN (sub field).
        """
        self._load_credentials()
        if not self.access_token:
            raise ValueError("No access token. Complete OAuth flow first.")

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    LINKEDIN_USERINFO_URL,
                    headers={"Authorization": f"Bearer {self.access_token}"},
                )
                response.raise_for_status()
                profile = response.json()
                self.user_id = profile.get("sub")
                return profile
            except httpx.HTTPStatusError as e:
                logger.error(f"LinkedIn profile fetch failed: {e.response.text}")
                raise

    async def publish_post(self, draft: LinkedInDraft) -> PublishResult:
        """
        Publish a LinkedIn post.

        Uses the Posts API (replaces deprecated ugcPosts).
        Requires w_member_social scope.

        Args:
            draft: The LinkedIn post draft to publish.

        Returns:
            PublishResult with success status and post URL.
        """
        self._load_credentials()
        if not self.access_token:
            raise ValueError("No LinkedIn access token. Complete OAuth flow first.")

        if not self.user_id:
            await self.get_user_profile()

        payload = {
            "author": f"urn:li:person:{self.user_id}",
            "commentary": draft.content,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    LINKEDIN_POSTS_URL,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.access_token}",
                        "X-Restli-Protocol-Version": "2.0.0",
                        "Linkedin-Version": settings.LINKEDIN_API_VERSION,
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
                post_id = response.headers.get("x-restli-id", "unknown")

                return PublishResult(
                    platform="linkedin",
                    success=True,
                    post_id=post_id,
                    post_url=f"https://www.linkedin.com/feed/update/{post_id}",
                    published_at=datetime.now(UTC),
                )
        except httpx.HTTPStatusError as e:
            logger.error(
                f"LinkedIn publish failed: {e.response.status_code} {e.response.text}"
            )
            return PublishResult(
                platform="linkedin",
                success=False,
                error=f"{e.response.status_code}: {e.response.text}",
                published_at=datetime.now(UTC),
            )

    def _store_token(self, token: str) -> None:
        """Store access token as a new version in Secret Manager."""
        try:
            from google.cloud import secretmanager

            client = secretmanager.SecretManagerServiceClient()
            parent = f"projects/{settings.GCP_PROJECT}/secrets/linkedin-access-token"
            client.add_secret_version(
                request={
                    "parent": parent,
                    "payload": {"data": token.encode("utf-8")},
                }
            )
            logger.info("LinkedIn access token stored in Secret Manager")
        except Exception as e:
            logger.error(f"Failed to store LinkedIn token: {e}")


class MediumPublisher:
    """Handles Medium article publishing via integration token."""

    def __init__(self) -> None:
        self.token: Optional[str] = None
        self.user_id: Optional[str] = None

    def _load_token(self) -> None:
        """Load Medium integration token from Secret Manager."""
        self.token = get_secret("medium-integration-token")
        if not self.token:
            raise ValueError(
                "Medium integration token not configured. "
                "Generate one at https://medium.com/me/settings/security"
            )

    async def _get_user_id(self) -> str:
        """Fetch the authenticated Medium user's ID."""
        if self.user_id:
            return self.user_id

        self._load_token()
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{MEDIUM_API_BASE}/me",
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
                data = response.json()
                self.user_id = data["data"]["id"]
                return self.user_id
            except httpx.HTTPStatusError as e:
                logger.error(f"Medium user fetch failed: {e.response.text}")
                raise

    async def publish_article(
        self, draft: MediumDraft, publish_status: str = "draft"
    ) -> PublishResult:
        """
        Publish a Medium article.

        Args:
            draft: The article draft with title, markdown content, and tags.
            publish_status: "draft", "public", or "unlisted". Default "draft".

        Returns:
            PublishResult with post URL and status.
        """
        user_id = await self._get_user_id()

        payload = {
            "title": draft.title,
            "contentFormat": "markdown",
            "content": draft.content_markdown,
            "tags": draft.tags[:5],  # Medium allows max 5 tags
            "publishStatus": publish_status,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{MEDIUM_API_BASE}/users/{user_id}/posts",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
                data = response.json()["data"]

                return PublishResult(
                    platform="medium",
                    success=True,
                    post_id=data.get("id", ""),
                    post_url=data.get("url", ""),
                    published_at=datetime.now(UTC),
                )
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Medium publish failed: {e.response.status_code} {e.response.text}"
            )
            return PublishResult(
                platform="medium",
                success=False,
                error=f"{e.response.status_code}: {e.response.text}",
                published_at=datetime.now(UTC),
            )
