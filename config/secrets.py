"""
Secret Manager accessor utility.

Loads secrets from GCP Secret Manager in production,
falls back to environment variables for local development.
"""
import logging
import os
from typing import Optional

from config.settings import settings

logger = logging.getLogger(__name__)


def get_secret(secret_id: str, version: str = "latest") -> Optional[str]:
    """
    Retrieve a secret value from Secret Manager.

    Falls back to environment variable with same name (uppercase, hyphens
    replaced with underscores) for local development.

    Args:
        secret_id: The secret name in Secret Manager (e.g. "linkedin-client-id").
        version: Secret version. Defaults to "latest".

    Returns:
        The secret value, or None if not found.
    """
    # Try environment variable first (local dev)
    env_key = secret_id.upper().replace("-", "_")
    env_val = os.getenv(env_key)
    if env_val:
        return env_val

    try:
        from google.cloud import secretmanager

        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{settings.GCP_PROJECT}/secrets/{secret_id}/versions/{version}"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("utf-8")
    except Exception as e:
        logger.error(f"Failed to access secret '{secret_id}': {e}")
        return None
