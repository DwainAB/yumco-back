import asyncio
import base64

import httpx

from app.core.config import settings

BREVO_SEND_EMAIL_URL = "https://api.brevo.com/v3/smtp/email"


async def send_email(to: str, subject: str, body: str, attachments: list[dict[str, str]] | None = None):
    if not settings.BREVO_API_KEY:
        raise RuntimeError("BREVO_API_KEY is not configured")

    if not settings.MAIL_FROM:
        raise RuntimeError("MAIL_FROM is not configured")

    payload = {
        "sender": {
            "email": settings.MAIL_FROM,
        },
        "to": [
            {
                "email": to,
            }
        ],
        "subject": subject,
        "htmlContent": body,
    }
    if attachments:
        payload["attachment"] = attachments

    headers = {
        "accept": "application/json",
        "api-key": settings.BREVO_API_KEY,
        "content-type": "application/json",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(BREVO_SEND_EMAIL_URL, json=payload, headers=headers)

    if response.status_code >= 400:
        raise RuntimeError(f"Brevo email API error ({response.status_code}): {response.text}")


async def send_email_safe(to: str, subject: str, body: str, timeout_seconds: float = 20.0) -> bool:
    try:
        await asyncio.wait_for(send_email(to=to, subject=subject, body=body), timeout=timeout_seconds)
        return True
    except Exception as exc:
        print("[email] send failed", {"to": to, "subject": subject, "error": str(exc)})
        return False


def build_base64_attachment(filename: str, content: bytes) -> dict[str, str]:
    return {
        "name": filename,
        "content": base64.b64encode(content).decode("ascii"),
    }
