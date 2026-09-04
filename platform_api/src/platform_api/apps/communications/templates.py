# ruff: noqa: E501
"""Template renderers for all platform communication intents."""

from __future__ import annotations

from typing import Any, NamedTuple

from django.conf import settings

from .intents import CommunicationIntent


class RenderedContent(NamedTuple):
    """Subject, HTML body, and plaintext body for a message."""

    subject: str
    html_body: str
    text_body: str


def _get_base_urls() -> dict[str, str]:
    """Return configured frontend and console URLs."""
    frontend = getattr(settings, "FRONTEND_PUBLIC_URL", "http://localhost:3000").rstrip("/")
    console = getattr(
        settings, "CONSOLE_PUBLIC_URL", "https://institutions.ai-mwalimu.com"
    ).rstrip("/")
    return {"frontend": frontend, "console": console}


def _email_container(title: str, content_html: str) -> str:
    """Standard responsive email container with Mwalimu brand layout."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background-color:#F8F6F0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#18181B;">
  <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color:#F8F6F0;padding:40px 16px;">
    <tr>
      <td align="center">
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width:520px;background-color:#FFFFFF;border:1px solid #E5E1D8;border-radius:12px;overflow:hidden;box-shadow:0 2px 6px rgba(0,0,0,0.04);">
          <!-- Header -->
          <tr>
            <td style="padding:24px 32px;background-color:#FAF7F2;border-bottom:1px solid #E5E1D8;">
              <table border="0" cellspacing="0" cellpadding="0">
                <tr>
                  <td style="width:28px;height:28px;background-color:#0D7A68;border-radius:6px;text-align:center;color:#FFFFFF;font-weight:bold;font-size:16px;line-height:28px;">M</td>
                  <td style="padding-left:12px;font-size:17px;font-weight:700;color:#1A1A18;letter-spacing:-0.01em;">Mwalimu</td>
                </tr>
              </table>
            </td>
          </tr>
          <!-- Body Content -->
          <tr>
            <td style="padding:32px;">
              {content_html}
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="padding:20px 32px;background-color:#FAF7F2;border-top:1px solid #E5E1D8;text-align:center;">
              <p style="margin:0;font-size:12px;color:#8C887B;">
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


def render_template_for_intent(
    intent: CommunicationIntent,
    context: dict[str, Any],
) -> RenderedContent:
    """Render subject, HTML body, and plaintext for a given intent."""
    urls = _get_base_urls()

    if intent == CommunicationIntent.AUTH_EMAIL_VERIFICATION:
        otp = context.get("otp", "")
        subject = "Verify your Mwalimu Account"
        body_html = f"""
          <h1 style="margin:0 0 12px 0;font-size:20px;font-weight:700;color:#1A1A18;">Verify your email address</h1>
          <p style="margin:0 0 24px 0;font-size:14px;line-height:22px;color:#52524E;">
            Welcome to Mwalimu. To complete your account verification and enter your workspace, enter the verification code below:
          </p>
          <div style="background-color:#F4F1EA;border:1px solid #E5E1D8;border-radius:8px;padding:18px 24px;text-align:center;margin:0 0 24px 0;">
            <span style="font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;font-size:32px;font-weight:700;letter-spacing:6px;color:#1A1A18;">{otp}</span>
          </div>
          <p style="margin:0;font-size:13px;line-height:20px;color:#8C887B;">
            This code expires in <strong>10 minutes</strong> and can only be used once. If you did not request this, you can safely ignore this email.
          </p>
        """
        text = f"Your Mwalimu verification code is: {otp}\n\nThis code expires in 10 minutes."
        return RenderedContent(subject=subject, html_body=_email_container(subject, body_html), text_body=text)

    elif intent == CommunicationIntent.AUTH_PASSWORD_RESET:
        otp = context.get("otp", "")
        subject = "Reset your Mwalimu Password"
        body_html = f"""
          <h1 style="margin:0 0 12px 0;font-size:20px;font-weight:700;color:#1A1A18;">Password Reset Code</h1>
          <p style="margin:0 0 24px 0;font-size:14px;line-height:22px;color:#52524E;">
            We received a request to reset your Mwalimu password. Enter the code below to proceed:
          </p>
          <div style="background-color:#F4F1EA;border:1px solid #E5E1D8;border-radius:8px;padding:18px 24px;text-align:center;margin:0 0 24px 0;">
            <span style="font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;font-size:32px;font-weight:700;letter-spacing:6px;color:#1A1A18;">{otp}</span>
          </div>
          <p style="margin:0;font-size:13px;line-height:20px;color:#8C887B;">
            This code expires in <strong>10 minutes</strong>. If you did not request this reset, your account is safe.
          </p>
        """
        text = f"Your Mwalimu password reset code is: {otp}\n\nThis code expires in 10 minutes."
        return RenderedContent(subject=subject, html_body=_email_container(subject, body_html), text_body=text)

    elif intent == CommunicationIntent.AUTH_WELCOME:
        name = context.get("display_name", "")
        greeting = f", {name}" if name else ""
        subject = "Welcome to Mwalimu"
        url = f"{urls['frontend']}/chat/new"
        body_html = f"""
          <h1 style="margin:0 0 12px 0;font-size:20px;font-weight:700;color:#1A1A18;">Welcome to Mwalimu{greeting}!</h1>
          <p style="margin:0 0 16px 0;font-size:14px;line-height:22px;color:#52524E;">
            Your account is verified. Mwalimu gives you personalized AI tutors grounded in your curriculum, course documents, and local context.
          </p>
          <div style="margin:24px 0;">
            <a href="{url}" style="display:inline-block;background-color:#0D7A68;color:#FFFFFF;text-decoration:none;font-weight:600;font-size:14px;padding:12px 24px;border-radius:8px;">Open Learning Workspace</a>
          </div>
        """
        text = f"Welcome to Mwalimu! Your account is ready: {url}"
        return RenderedContent(subject=subject, html_body=_email_container(subject, body_html), text_body=text)

    elif intent == CommunicationIntent.LIBRARY_INVITATION_NEW_USER:
        inviter_email = context.get("inviter_email", "A librarian")
        library_name = context.get("library_name", "Knowledge Library")
        institution_name = context.get("institution_name", "Institution")
        role = context.get("role", "Student").capitalize()
        token = context.get("token", "")
        invite_url = context.get("invite_url") or f"{urls['console']}/invite/{token}"

        subject = f"You're invited to join '{library_name}' on Mwalimu"
        body_html = f"""
          <h1 style="margin:0 0 12px 0;font-size:20px;font-weight:700;color:#1A1A18;">Invitation to Knowledge Library</h1>
          <p style="margin:0 0 16px 0;font-size:14px;line-height:22px;color:#52524E;">
            <strong>{inviter_email}</strong> has invited you to access the library <strong>"{library_name}"</strong> in <strong>{institution_name}</strong> as a <strong>{role}</strong>.
          </p>
          <p style="margin:0 0 24px 0;font-size:14px;line-height:22px;color:#52524E;">
            Create your Mwalimu account to view verified course documents, textbooks, and interactive AI study assistance:
          </p>
          <div style="margin:0 0 24px 0;">
            <a href="{invite_url}" style="display:inline-block;background-color:#0D7A68;color:#FFFFFF;text-decoration:none;font-weight:600;font-size:14px;padding:12px 24px;border-radius:8px;">Accept Invitation &amp; Register</a>
          </div>
          <p style="margin:0;font-size:13px;line-height:20px;color:#8C887B;">
            This invitation was sent specifically to your email address and will be verified upon registration.
          </p>
        """
        text = f"You're invited to join '{library_name}' ({institution_name}) on Mwalimu as a {role}.\n\nAccept invitation: {invite_url}"
        return RenderedContent(subject=subject, html_body=_email_container(subject, body_html), text_body=text)

    elif intent == CommunicationIntent.LIBRARY_INVITATION_EXISTING_USER:
        inviter_email = context.get("inviter_email", "A librarian")
        library_name = context.get("library_name", "Knowledge Library")
        institution_name = context.get("institution_name", "Institution")
        role = context.get("role", "Student").capitalize()
        token = context.get("token", "")
        invite_url = context.get("invite_url") or f"{urls['console']}/invite/{token}"

        subject = f"You've been invited to join '{library_name}'"
        body_html = f"""
          <h1 style="margin:0 0 12px 0;font-size:20px;font-weight:700;color:#1A1A18;">New Library Invitation</h1>
          <p style="margin:0 0 16px 0;font-size:14px;line-height:22px;color:#52524E;">
            <strong>{inviter_email}</strong> has invited you to join the library <strong>"{library_name}"</strong> in <strong>{institution_name}</strong> as a <strong>{role}</strong>.
          </p>
          <p style="margin:0 0 24px 0;font-size:14px;line-height:22px;color:#52524E;">
            You can review this invitation in your Notification Center or open it directly below:
          </p>
          <div style="margin:0 0 24px 0;">
            <a href="{invite_url}" style="display:inline-block;background-color:#0D7A68;color:#FFFFFF;text-decoration:none;font-weight:600;font-size:14px;padding:12px 24px;border-radius:8px;">View Invitation</a>
          </div>
        """
        text = f"{inviter_email} invited you to '{library_name}' in {institution_name}.\n\nReview: {invite_url}"
        return RenderedContent(subject=subject, html_body=_email_container(subject, body_html), text_body=text)

    elif intent == CommunicationIntent.LIBRARY_INVITATION_ACCEPTED:
        recipient_email = context.get("recipient_email", "A user")
        library_name = context.get("library_name", "Knowledge Library")
        role = context.get("role", "Student").capitalize()
        subject = f"{recipient_email} accepted your invitation to '{library_name}'"
        body_html = f"""
          <h1 style="margin:0 0 12px 0;font-size:20px;font-weight:700;color:#1A1A18;">Invitation Accepted</h1>
          <p style="margin:0;font-size:14px;line-height:22px;color:#52524E;">
            <strong>{recipient_email}</strong> has accepted your invitation to join <strong>"{library_name}"</strong> as a <strong>{role}</strong>. Access policy has been activated.
          </p>
        """
        text = f"{recipient_email} accepted your invitation to '{library_name}' as {role}."
        return RenderedContent(subject=subject, html_body=_email_container(subject, body_html), text_body=text)

    elif intent == CommunicationIntent.LIBRARY_INVITATION_DECLINED:
        recipient_email = context.get("recipient_email", "A user")
        library_name = context.get("library_name", "Knowledge Library")
        subject = f"{recipient_email} declined your invitation to '{library_name}'"
        body_html = f"""
          <h1 style="margin:0 0 12px 0;font-size:20px;font-weight:700;color:#1A1A18;">Invitation Declined</h1>
          <p style="margin:0;font-size:14px;line-height:22px;color:#52524E;">
            <strong>{recipient_email}</strong> declined the invitation to join <strong>"{library_name}"</strong>. No access was granted.
          </p>
        """
        text = f"{recipient_email} declined the invitation to join '{library_name}'."
        return RenderedContent(subject=subject, html_body=_email_container(subject, body_html), text_body=text)

    elif intent == CommunicationIntent.MEMBERSHIP_APPROVED:
        institution_name = context.get("institution_name", "Institution")
        role = context.get("role", "Member").capitalize()
        subject = f"Your membership to {institution_name} has been approved"
        body_html = f"""
          <h1 style="margin:0 0 12px 0;font-size:20px;font-weight:700;color:#1A1A18;">Membership Approved</h1>
          <p style="margin:0;font-size:14px;line-height:22px;color:#52524E;">
            Your request to join <strong>{institution_name}</strong> as a <strong>{role}</strong> has been approved by an administrator.
          </p>
        """
        text = f"Your membership to {institution_name} has been approved as {role}."
        return RenderedContent(subject=subject, html_body=_email_container(subject, body_html), text_body=text)

    elif intent == CommunicationIntent.MEMBERSHIP_SUSPENDED:
        institution_name = context.get("institution_name", "Institution")
        subject = f"Notice: Access suspended for {institution_name}"
        body_html = f"""
          <h1 style="margin:0 0 12px 0;font-size:20px;font-weight:700;color:#1A1A18;">Access Notice</h1>
          <p style="margin:0;font-size:14px;line-height:22px;color:#52524E;">
            Your active membership in <strong>{institution_name}</strong> has been temporarily suspended by an administrator.
          </p>
        """
        text = f"Your membership in {institution_name} has been suspended."
        return RenderedContent(subject=subject, html_body=_email_container(subject, body_html), text_body=text)

    # Fallback generic template
    title = context.get("title", "Mwalimu Notification")
    msg = context.get("message", "You have a new update in Mwalimu.")
    subject = f"Mwalimu: {title}"
    body_html = f"""
      <h1 style="margin:0 0 12px 0;font-size:20px;font-weight:700;color:#1A1A18;">{title}</h1>
      <p style="margin:0;font-size:14px;line-height:22px;color:#52524E;">{msg}</p>
    """
    return RenderedContent(subject=subject, html_body=_email_container(subject, body_html), text_body=msg)
