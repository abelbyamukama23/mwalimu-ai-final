# ruff: noqa: E501
"""Transactional email service for Mwalimu using Resend delivery."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

RESEND_API_ENDPOINT = "https://api.resend.com/emails"


class EmailDeliveryError(Exception):
    """Raised when email delivery via Resend fails."""


def _get_resend_config() -> dict[str, str]:
    """Retrieve Resend API configuration from Django settings."""
    return {
        "api_key": getattr(settings, "RESEND_API_KEY", "").strip(),
        "from_email": getattr(
            settings,
            "EMAIL_FROM",
            "Mwalimu <onboarding@resend.dev>",
        ),
        "frontend_url": getattr(
            settings,
            "FRONTEND_PUBLIC_URL",
            "http://localhost:3000",
        ).rstrip("/"),
    }


def _send_resend_email(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: str | None = None,
) -> dict[str, Any]:
    """Send an email via the Resend API.

    In development / sandbox mode (when RESEND_API_KEY is unset or starts with 're_mock_'),
    the email is simulated and logged safely without logging raw OTP values.
    """
    config = _get_resend_config()
    api_key = config["api_key"]
    from_email = config["from_email"]

    if not api_key or api_key == "mock" or api_key.startswith("re_mock_"):
        logger.info(
            "Resend API key not configured. Mocked delivery to %s for subject: '%s'",
            to_email,
            subject,
        )
        return {"id": "mock_email_id", "simulated": True}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "from": from_email,
        "to": [to_email],
        "subject": subject,
        "html": html_content,
    }
    if text_content:
        payload["text"] = text_content

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                RESEND_API_ENDPOINT,
                headers=headers,
                json=payload,
            )
            if response.status_code not in (200, 201):
                logger.error(
                    "Resend API error (HTTP %d) for recipient %s: %s",
                    response.status_code,
                    to_email,
                    response.text,
                )
                raise EmailDeliveryError(
                    f"Resend delivery failed with status {response.status_code}"
                )
            return response.json()  # type: ignore[no-any-return]
    except Exception as exc:
        if isinstance(exc, EmailDeliveryError):
            raise
        logger.exception("Unexpected exception sending email to %s: %s", to_email, exc)
        raise EmailDeliveryError(f"Email delivery failed: {exc}") from exc


def render_verification_otp_html(otp: str, frontend_url: str) -> str:
    """Render the responsive HTML template for account verification OTP."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Verify your Mwalimu Account</title>
</head>
<body style="margin:0;padding:0;background-color:#FBFBFB;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#18181B;">
  <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color:#FBFBFB;padding:40px 16px;">
    <tr>
      <td align="center">
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width:480px;background-color:#FFFFFF;border:1px solid #E4E4E7;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.05);">
          <!-- Header -->
          <tr>
            <td style="padding:28px 32px;border-bottom:1px solid #F4F4F5;">
              <table border="0" cellspacing="0" cellpadding="0">
                <tr>
                  <td style="width:28px;height:28px;background-color:#18181B;border-radius:6px;text-align:center;color:#FFFFFF;font-weight:bold;font-size:16px;line-height:28px;">M</td>
                  <td style="padding-left:12px;font-size:17px;font-weight:600;color:#18181B;letter-spacing:-0.01em;">Mwalimu</td>
                </tr>
              </table>
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td style="padding:32px;">
              <h1 style="margin:0 0 12px 0;font-size:20px;font-weight:600;color:#18181B;letter-spacing:-0.02em;">Verify your email address</h1>
              <p style="margin:0 0 24px 0;font-size:14px;line-height:22px;color:#71717A;">
                Welcome to Mwalimu. To complete your account registration and access your personalized academic workspace, enter the verification code below:
              </p>
              <!-- Code Box -->
              <div style="background-color:#F4F4F5;border:1px solid #E4E4E7;border-radius:8px;padding:18px 24px;text-align:center;margin:0 0 24px 0;">
                <span style="font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;font-size:32px;font-weight:700;letter-spacing:6px;color:#18181B;">{otp}</span>
              </div>
              <p style="margin:0 0 8px 0;font-size:13px;line-height:20px;color:#71717A;">
                <strong>Note:</strong> This verification code expires in <strong>10 minutes</strong> and can only be used once.
              </p>
              <p style="margin:0;font-size:13px;line-height:20px;color:#A1A1AA;">
                If you did not request this account, you can safely disregard this email.
              </p>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="padding:24px 32px;background-color:#FAFAFA;border-top:1px solid #F4F4F5;text-align:center;">
              <p style="margin:0;font-size:12px;color:#A1A1AA;">
                Mwalimu &middot; Contextual AI Teaching &amp; Study Platform
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def render_password_reset_otp_html(otp: str, frontend_url: str) -> str:
    """Render the responsive HTML template for password reset OTP."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Reset your Mwalimu Password</title>
</head>
<body style="margin:0;padding:0;background-color:#FBFBFB;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#18181B;">
  <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color:#FBFBFB;padding:40px 16px;">
    <tr>
      <td align="center">
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width:480px;background-color:#FFFFFF;border:1px solid #E4E4E7;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.05);">
          <!-- Header -->
          <tr>
            <td style="padding:28px 32px;border-bottom:1px solid #F4F4F5;">
              <table border="0" cellspacing="0" cellpadding="0">
                <tr>
                  <td style="width:28px;height:28px;background-color:#18181B;border-radius:6px;text-align:center;color:#FFFFFF;font-weight:bold;font-size:16px;line-height:28px;">M</td>
                  <td style="padding-left:12px;font-size:17px;font-weight:600;color:#18181B;letter-spacing:-0.01em;">Mwalimu</td>
                </tr>
              </table>
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td style="padding:32px;">
              <h1 style="margin:0 0 12px 0;font-size:20px;font-weight:600;color:#18181B;letter-spacing:-0.02em;">Password Reset Code</h1>
              <p style="margin:0 0 24px 0;font-size:14px;line-height:22px;color:#71717A;">
                We received a request to reset the password for your Mwalimu account. Enter the verification code below to set a new password:
              </p>
              <!-- Code Box -->
              <div style="background-color:#F4F4F5;border:1px solid #E4E4E7;border-radius:8px;padding:18px 24px;text-align:center;margin:0 0 24px 0;">
                <span style="font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;font-size:32px;font-weight:700;letter-spacing:6px;color:#18181B;">{otp}</span>
              </div>
              <p style="margin:0 0 8px 0;font-size:13px;line-height:20px;color:#71717A;">
                <strong>Security note:</strong> This code expires in <strong>10 minutes</strong>. If you did not request a password reset, your account is still secure and you can safely ignore this email.
              </p>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="padding:24px 32px;background-color:#FAFAFA;border-top:1px solid #F4F4F5;text-align:center;">
              <p style="margin:0;font-size:12px;color:#A1A1AA;">
                Mwalimu &middot; Security &amp; Identity
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def render_welcome_html(display_name: str, frontend_url: str) -> str:
    """Render the responsive HTML template for welcome email."""
    greeting_name = f", {display_name}" if display_name else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Welcome to Mwalimu</title>
</head>
<body style="margin:0;padding:0;background-color:#FBFBFB;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#18181B;">
  <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color:#FBFBFB;padding:40px 16px;">
    <tr>
      <td align="center">
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width:480px;background-color:#FFFFFF;border:1px solid #E4E4E7;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.05);">
          <!-- Header -->
          <tr>
            <td style="padding:28px 32px;border-bottom:1px solid #F4F4F5;">
              <table border="0" cellspacing="0" cellpadding="0">
                <tr>
                  <td style="width:28px;height:28px;background-color:#18181B;border-radius:6px;text-align:center;color:#FFFFFF;font-weight:bold;font-size:16px;line-height:28px;">M</td>
                  <td style="padding-left:12px;font-size:17px;font-weight:600;color:#18181B;letter-spacing:-0.01em;">Mwalimu</td>
                </tr>
              </table>
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td style="padding:32px;">
              <h1 style="margin:0 0 12px 0;font-size:20px;font-weight:600;color:#18181B;letter-spacing:-0.02em;">Welcome to Mwalimu{greeting_name}!</h1>
              <p style="margin:0 0 16px 0;font-size:14px;line-height:22px;color:#71717A;">
                Your account is ready. Mwalimu gives you personalized AI tutors grounded in your curriculum, course documents, and local East African context.
              </p>
              <p style="margin:0 0 24px 0;font-size:14px;line-height:22px;color:#71717A;">
                You can upload lecture notes, link study drives, and engage in interactive, step-by-step Socratic learning.
              </p>
              <!-- Button -->
              <div style="margin:0 0 28px 0;">
                <a href="{frontend_url}/chat/new" style="display:inline-block;background-color:#18181B;color:#FFFFFF;text-decoration:none;font-weight:600;font-size:14px;padding:12px 24px;border-radius:8px;box-shadow:0 1px 2px rgba(0,0,0,0.05);">Open Learning Workspace</a>
              </div>
              <p style="margin:0;font-size:13px;line-height:20px;color:#A1A1AA;">
                If the button above does not work, visit <a href="{frontend_url}" style="color:#18181B;text-decoration:underline;">{frontend_url}</a> directly in your browser.
              </p>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="padding:24px 32px;background-color:#FAFAFA;border-top:1px solid #F4F4F5;text-align:center;">
              <p style="margin:0;font-size:12px;color:#A1A1AA;">
                Mwalimu &middot; Learn with deep contextual understanding
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def send_verification_otp_email(email: str, otp: str) -> None:
    """Send the 6-digit verification code email to a learner."""
    config = _get_resend_config()
    html = render_verification_otp_html(otp, config["frontend_url"])
    text = (
        f"Your Mwalimu verification code is: {otp}\n\nThis code expires in 10 minutes."
    )
    try:
        _send_resend_email(
            to_email=email,
            subject="Verify your Mwalimu Account",
            html_content=html,
            text_content=text,
        )
    except Exception as exc:
        logger.warning("Could not dispatch verification email to %s: %s", email, exc)


def send_password_reset_otp_email(email: str, otp: str) -> None:
    """Send the 6-digit password reset code email."""
    config = _get_resend_config()
    html = render_password_reset_otp_html(otp, config["frontend_url"])
    text = f"Your Mwalimu password reset code is: {otp}\n\nThis code expires in 10 minutes."
    try:
        _send_resend_email(
            to_email=email,
            subject="Reset your Mwalimu Password",
            html_content=html,
            text_content=text,
        )
    except Exception as exc:
        logger.warning("Could not dispatch password reset email to %s: %s", email, exc)


def send_welcome_email(email: str, display_name: str = "") -> None:
    """Send the welcome email following successful verification."""
    config = _get_resend_config()
    html = render_welcome_html(display_name, config["frontend_url"])
    url = config["frontend_url"]
    text = f"Welcome to Mwalimu! Your account is ready: {url}/chat/new"
    try:
        _send_resend_email(
            to_email=email,
            subject="Welcome to Mwalimu",
            html_content=html,
            text_content=text,
        )
    except Exception as exc:
        logger.warning("Could not dispatch welcome email to %s: %s", email, exc)

