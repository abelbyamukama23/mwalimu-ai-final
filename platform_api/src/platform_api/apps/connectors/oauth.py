"""OAuth 2.0 provider integration and token exchange service with Production and Dev Sandbox support."""

from __future__ import annotations

import base64
import json
import logging
import urllib.parse
import uuid
from typing import Any

import httpx
from django.conf import settings
from django.core import signing

logger = logging.getLogger(__name__)


class OAuthError(Exception):
    """Raised when an OAuth authorization or token exchange fails."""


PROVIDER_CONFIGS: dict[str, dict[str, Any]] = {
    "google": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scopes": [
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/userinfo.email",
        ],
        "client_id_setting": "GOOGLE_CLIENT_ID",
        "client_secret_setting": "GOOGLE_CLIENT_SECRET",
        "access_type": "offline",
        "prompt": "consent",
    },
    "notion": {
        "auth_url": "https://api.notion.com/v1/oauth/authorize",
        "token_url": "https://api.notion.com/v1/oauth/token",
        "scopes": [],
        "client_id_setting": "NOTION_CLIENT_ID",
        "client_secret_setting": "NOTION_CLIENT_SECRET",
    },
}


def is_provider_configured(provider: str) -> bool:
    """Return True if real production OAuth credentials exist in settings."""
    cfg = PROVIDER_CONFIGS.get(provider.lower())
    if not cfg:
        return False
    client_id = getattr(settings, cfg["client_id_setting"], "")
    client_secret = getattr(settings, cfg["client_secret_setting"], "")
    return bool(
        client_id
        and client_secret
        and not client_id.startswith("mwalimu-oauth-client")
    )


def generate_oauth_state(
    provider: str, library_id: uuid.UUID, user_id: uuid.UUID
) -> str:
    """Generate a tamper-proof cryptographically signed state token."""
    payload = {
        "provider": provider,
        "library_id": str(library_id),
        "user_id": str(user_id),
        "nonce": str(uuid.uuid4()),
    }
    return signing.dumps(payload, salt="mwalimu.connectors.oauth")


def decode_oauth_state(state_token: str) -> dict[str, Any]:
    """Decode and verify a signed state token, raising OAuthError on tamper."""
    try:
        data = signing.loads(
            state_token, salt="mwalimu.connectors.oauth", max_age=1800  # 30 min max
        )
        if isinstance(data, dict):
            return data
        raise OAuthError("Malformed state payload.")
    except Exception as exc:
        raise OAuthError(f"Invalid or expired OAuth state token: {exc}") from exc


def get_oauth_authorization_url(
    provider: str,
    library_id: uuid.UUID,
    user_id: uuid.UUID,
    redirect_uri: str,
) -> str:
    """Construct provider OAuth authorization URL (or development sandbox URL)."""
    cfg = PROVIDER_CONFIGS.get(provider.lower())
    if not cfg:
        raise OAuthError(f"Unsupported OAuth provider: '{provider}'")

    state = generate_oauth_state(provider, library_id, user_id)

    # If in development without registered Google Cloud App, route through dev sandbox
    if not is_provider_configured(provider):
        sandbox_params = urllib.parse.urlencode(
            {
                "state": state,
                "provider": provider,
                "redirect_uri": redirect_uri,
            }
        )
        return f"/api/v1/connectors/oauth/{provider}/sandbox/?{sandbox_params}"

    client_id = getattr(settings, cfg["client_id_setting"])
    params: dict[str, str] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
    }

    if cfg.get("scopes"):
        params["scope"] = " ".join(cfg["scopes"])
    if cfg.get("access_type"):
        params["access_type"] = cfg["access_type"]
    if cfg.get("prompt"):
        params["prompt"] = cfg["prompt"]

    if provider == "notion":
        params["owner"] = "user"

    return f"{cfg['auth_url']}?{urllib.parse.urlencode(params)}"


def exchange_oauth_code(
    provider: str,
    code: str,
    redirect_uri: str,
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Exchange authorization code for access and refresh tokens."""
    cfg = PROVIDER_CONFIGS.get(provider.lower())
    if not cfg:
        raise OAuthError(f"Unsupported OAuth provider: '{provider}'")

    # Handle Sandbox Simulation Code in Development
    if code.startswith("sandbox_demo_code_") or not is_provider_configured(provider):
        return {
            "oauth_token": f"sandbox_token_{uuid.uuid4().hex[:16]}",
            "refresh_token": f"sandbox_refresh_{uuid.uuid4().hex[:16]}",
            "token_type": "Bearer",
            "account_email": "demo.user@mwalimu.ai",
            "is_sandbox": True,
        }

    client_id = getattr(settings, cfg["client_id_setting"])
    client_secret = getattr(settings, cfg["client_secret_setting"])

    headers = {"Accept": "application/json"}
    payload: dict[str, str] = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }

    if provider == "notion":
        auth_bytes = f"{client_id}:{client_secret}".encode("utf-8")
        headers["Authorization"] = f"Basic {base64.b64encode(auth_bytes).decode('utf-8')}"
    else:
        payload["client_id"] = client_id
        payload["client_secret"] = client_secret

    client = http_client or httpx.Client(timeout=15.0)
    try:
        with client:
            resp = client.post(cfg["token_url"], data=payload, headers=headers)
            if resp.status_code != 200:
                raise OAuthError(
                    f"Token exchange failed (HTTP {resp.status_code}): {resp.text}"
                )
            data = resp.json()
            return {
                "oauth_token": data.get("access_token"),
                "refresh_token": data.get("refresh_token"),
                "token_type": data.get("token_type", "Bearer"),
                "expires_in": data.get("expires_in"),
                "workspace_id": data.get("workspace_id"),
                "is_sandbox": False,
            }
    except Exception as exc:
        if isinstance(exc, OAuthError):
            raise
        raise OAuthError(f"Failed to communicate with {provider} token endpoint: {exc}") from exc
