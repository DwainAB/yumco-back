/**
 * Envoi d'e-mails par l'API Brevo (email_service.py).
 */
import { env } from '../../config/env.js';
import { logger } from '../../lib/logger.js';

const BREVO_SEND_EMAIL_URL = 'https://api.brevo.com/v3/smtp/email';

export interface EmailAttachment {
  name: string;
  /** Contenu encodé en base64. */
  content: string;
}

export interface EmailMessage {
  to: string;
  subject: string;
  body: string;
  attachments?: EmailAttachment[];
}

export const sendEmail = async ({ to, subject, body, attachments }: EmailMessage, timeoutMs = 20_000) => {
  if (!env.BREVO_API_KEY) throw new Error('BREVO_API_KEY is not configured');
  if (!env.MAIL_FROM) throw new Error('MAIL_FROM is not configured');

  const payload: Record<string, unknown> = {
    sender: { email: env.MAIL_FROM },
    to: [{ email: to }],
    subject,
    htmlContent: body,
  };
  if (attachments?.length) payload.attachment = attachments;

  const response = await fetch(BREVO_SEND_EMAIL_URL, {
    method: 'POST',
    headers: { accept: 'application/json', 'api-key': env.BREVO_API_KEY, 'content-type': 'application/json' },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (response.status >= 400) {
    throw new Error(`Brevo email API error (${response.status}): ${await response.text()}`);
  }
};

/** Envoi sans lever d'erreur : renvoie false en cas d'échec (send_email_safe). */
export const sendEmailSafe = async (message: EmailMessage, timeoutMs = 20_000): Promise<boolean> => {
  try {
    await sendEmail(message, timeoutMs);
    return true;
  } catch (error) {
    logger.warn({ to: message.to, subject: message.subject, error: String(error) }, '[email] send failed');
    return false;
  }
};

export const buildBase64Attachment = (name: string, content: Buffer): EmailAttachment => ({
  name,
  content: content.toString('base64'),
});
