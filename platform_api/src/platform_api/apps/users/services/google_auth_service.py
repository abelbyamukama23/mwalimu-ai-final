"""Google OAuth 2.0 / OpenID Connect authorization and account linking service."""

from __future__ import annotations

import logging
import urllib.parse
import uuid
from typing import Any

import httpx
from django.conf import settings
from django.core import signing
from django.utils import timezone

from platform_api.apps.users.models import User, UserProfile

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
GOOGLE_SCOPES = ["openid", "email", "profile"]


class GoogleAuthError(Exception):
    """Raised when Google OAuth authorization, exchange, or claim validation fails."""


def is_google_auth_configured() -> bool:
    """Return True if real Google Client credentials exist in settings."""
    client_id = getattr(settings, "GOOGLE_CLIENT_ID", "").strip()
    client_secret = getattr(settings, "GOOGLE_CLIENT_SECRET", "").strip()
    return bool(
        client_id and client_secret and not client_id.startswith("mwalimu-oauth-client")
    )


def generate_google_oauth_state(redirect_uri: str) -> str:
    """Generate a tamper-proof cryptographically signed state token."""
    payload = {
        "nonce": uuid.uuid4().hex,
        "redirect_uri": redirect_uri,
        "timestamp": timezone.now().isoformat(),
    }
    return signing.dumps(payload, salt="mwalimu.auth.google")


def decode_google_oauth_state(state_token: str) -> dict[str, Any]:
    """Decode and verify a signed state token, raising on tamper or expiry."""
    try:
        data = signing.loads(
            state_token,
            salt="mwalimu.auth.google",
            max_age=900,  # 15 min expiry
        )
        if isinstance(data, dict):
            return data
        raise GoogleAuthError("Malformed OAuth state payload.")
    except Exception as exc:
        raise GoogleAuthError(f"Invalid or expired Google OAuth state: {exc}") from exc


def get_google_authorization_url(redirect_uri: str) -> tuple[str, str]:
    """Construct Google OAuth authorization URL and signed state token."""
    state = generate_google_oauth_state(redirect_uri)

    if not is_google_auth_configured():
        # In dev or test mode, return local dev redirect
        dev_params = urllib.parse.urlencode(
            {
                "state": state,
                "redirect_uri": redirect_uri,
                "demo": "true",
            }
        )
        return f"/api/v1/auth/google/sandbox/?{dev_params}", state

    client_id = settings.GOOGLE_CLIENT_ID
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "state": state,
        "access_type": "offline",
        "prompt": "select_account",
    }
    auth_url = f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
    return auth_url, state


def exchange_google_code_and_get_identity(
    code: str,
    redirect_uri: str,
    state: str,
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Exchange code with Google for tokens and fetch verified user identity claims."""
    # 1. Validate signed state
    decode_google_oauth_state(state)

    # 2. Handle simulated code in dev / testing
    if code.startswith("google_sandbox_") or not is_google_auth_configured():
        demo_email = "learner.google@mwalimu.ai"
        return {
            "sub": f"google_sandbox_sub_{uuid.uuid4().hex[:12]}",
            "email": demo_email,
            "email_verified": True,
            "name": "Google Learner",
            "picture": "",
        }

    client_id = settings.GOOGLE_CLIENT_ID
    client_secret = settings.GOOGLE_CLIENT_SECRET

    payload = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }

    client = http_client or httpx.Client(timeout=10.0)
    try:
        with client:
            token_resp = client.post(GOOGLE_TOKEN_URL, data=payload)
            if token_resp.status_code != 200:
                err_text = token_resp.text
                raise GoogleAuthError(
                    f"Token exchange failed (HTTP {token_resp.status_code}): {err_text}"
                )
            token_data = token_resp.json()
            access_token = token_data.get("access_token")
            if not access_token:
                raise GoogleAuthError("No access token returned by Google.")


            # Fetch verified userinfo
            userinfo_resp = client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if userinfo_resp.status_code != 200:
                raise GoogleAuthError("Failed to fetch user profile from Google.")

            userinfo = userinfo_resp.json()
            sub = userinfo.get("sub")
            email = userinfo.get("email")
            email_verified = userinfo.get("email_verified", False)

            if not sub or not email:
                raise GoogleAuthError("Missing essential identity claims from Google.")

            if not email_verified:
                raise GoogleAuthError("Your Google email is not verified by Google.")

            return {
                "sub": str(sub),
                "email": str(email).strip().lower(),
                "email_verified": bool(email_verified),
                "name": str(userinfo.get("name", "")).strip(),
                "picture": str(userinfo.get("picture", "")).strip(),
            }
    except Exception as exc:
        if isinstance(exc, GoogleAuthError):
            raise
        logger.exception("Google OAuth network communication failure: %s", exc)
        raise GoogleAuthError(f"Failed to communicate with Google: {exc}") from exc


def resolve_or_create_google_user(identity: dict[str, Any]) -> tuple[User, bool]:
    """Find existing user or create a new verified Mwalimu account from Google identity.

    Returns:
        tuple[User, bool]: (user instance, created_flag)
    """
    sub = identity["sub"]
    email = identity["email"].strip().lower()
    name = identity.get("name", "")
    picture = identity.get("picture", "")

    now = timezone.now()

    # 1. Match by existing Google sub
    user = User.objects.filter(google_sub=sub).first()
    if user:
        if not user.is_email_verified:
            user.is_email_verified = True
            user.email_verified_at = now
            user.save(update_fields=["is_email_verified", "email_verified_at"])
        # Ensure profile exists
        UserProfile.objects.get_or_create(user=user)
        return user, False

    # 2. Match by email address (Safe linking to existing user)
    user = User.objects.filter(email=email).first()
    if user:
        user.google_sub = sub
        if not user.is_email_verified:
            user.is_email_verified = True
            user.email_verified_at = now
        user.save(
            update_fields=["google_sub", "is_email_verified", "email_verified_at"]
        )

        profile, _ = UserProfile.objects.get_or_create(user=user)
        if not profile.display_name and name:
            profile.display_name = name
            profile.save(update_fields=["display_name"])
        if not profile.avatar_url and picture:
            profile.avatar_url = picture
            profile.save(update_fields=["avatar_url"])

        return user, False

    # 3. Create new verified User + Profile
    new_user = User.objects.create_user(
        email=email,
        password=None,  # Unusable password for OAuth-only users
        google_sub=sub,
        is_email_verified=True,
        email_verified_at=now,
    )

    display_name = name if name else email.split("@")[0]
    UserProfile.objects.create(
        user=new_user,
        display_name=display_name,
        avatar_url=picture,
    )

    return new_user, True
