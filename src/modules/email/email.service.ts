/**
 * Envoi d'e-mails (email_service.py) : Resend si RESEND_API_KEY est configurée, sinon Brevo.
 */
import { env } from '../../config/env.js';
import { logger } from '../../lib/logger.js';

const RESEND_SEND_EMAIL_URL = 'https://api.resend.com/emails';
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

/** MAIL_FROM : « contact@yumco.fr » ou « Yumco <contact@yumco.fr> ». */
export const parseSender = (from: string) => {
  const match = /^\s*(.*?)\s*<([^>]+)>\s*$/.exec(from);
  return match ? { name: match[1].replace(/^"|"$/g, '') || null, email: match[2].trim() } : { name: null, email: from.trim() };
};

/** Corps de la requête Resend (https://resend.com/docs/api-reference/emails/send-email). */
export const toResendPayload = (from: string, { to, subject, body, attachments }: EmailMessage) => {
  const sender = parseSender(from);
  return {
    from: sender.name ? `${sender.name} <${sender.email}>` : sender.email,
    to: [to],
    subject,
    html: body,
    ...(attachments?.length ? { attachments: attachments.map((a) => ({ filename: a.name, content: a.content })) } : {}),
  };
};

/** Corps de la requête Brevo (comportement du backend Python). */
export const toBrevoPayload = (from: string, { to, subject, body, attachments }: EmailMessage) => {
  const sender = parseSender(from);
  return {
    sender: sender.name ? { name: sender.name, email: sender.email } : { email: sender.email },
    to: [{ email: to }],
    subject,
    htmlContent: body,
    ...(attachments?.length ? { attachment: attachments } : {}),
  };
};

export const sendEmail = async (message: EmailMessage, timeoutMs = 20_000) => {
  if (!env.MAIL_FROM) throw new Error('MAIL_FROM is not configured');

  let request: { url: string; headers: Record<string, string>; payload: unknown; provider: string };
  if (env.RESEND_API_KEY) {
    request = {
      provider: 'Resend',
      url: RESEND_SEND_EMAIL_URL,
      headers: { authorization: `Bearer ${env.RESEND_API_KEY}`, 'content-type': 'application/json' },
      payload: toResendPayload(env.MAIL_FROM, message),
    };
  } else if (env.BREVO_API_KEY) {
    request = {
      provider: 'Brevo',
      url: BREVO_SEND_EMAIL_URL,
      headers: { accept: 'application/json', 'api-key': env.BREVO_API_KEY, 'content-type': 'application/json' },
      payload: toBrevoPayload(env.MAIL_FROM, message),
    };
  } else {
    throw new Error('No email provider configured (RESEND_API_KEY or BREVO_API_KEY)');
  }

  const response = await fetch(request.url, {
    method: 'POST',
    headers: request.headers,
    body: JSON.stringify(request.payload),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (response.status >= 400) {
    throw new Error(`${request.provider} email API error (${response.status}): ${await response.text()}`);
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
