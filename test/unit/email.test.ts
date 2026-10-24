/**
 * Corps des requêtes d'envoi d'e-mails (Resend, Brevo).
 */
import { describe, expect, it } from 'vitest';
import { parseSender, toBrevoPayload, toResendPayload } from '../../src/modules/email/email.service.js';

const message = { to: 'client@example.com', subject: 'Sujet', body: '<p>Bonjour</p>', attachments: [{ name: 'ticket.pdf', content: 'JVBERi0=' }] };

describe('e-mails', () => {
  it('lit l’expéditeur avec ou sans nom', () => {
    expect(parseSender('contact@yumco.fr')).toEqual({ name: null, email: 'contact@yumco.fr' });
    expect(parseSender('Yumco <onboarding@resend.dev>')).toEqual({ name: 'Yumco', email: 'onboarding@resend.dev' });
    expect(parseSender('"Yumco" <onboarding@resend.dev>')).toEqual({ name: 'Yumco', email: 'onboarding@resend.dev' });
  });

  it('construit la requête Resend', () => {
    expect(toResendPayload('Yumco <onboarding@resend.dev>', message)).toEqual({
      from: 'Yumco <onboarding@resend.dev>',
      to: ['client@example.com'],
      subject: 'Sujet',
      html: '<p>Bonjour</p>',
      attachments: [{ filename: 'ticket.pdf', content: 'JVBERi0=' }],
    });
    expect(toResendPayload('onboarding@resend.dev', { ...message, attachments: [] })).not.toHaveProperty('attachments');
  });

  it('garde la requête Brevo du backend Python', () => {
    expect(toBrevoPayload('contact@yumco.fr', message)).toEqual({
      sender: { email: 'contact@yumco.fr' },
      to: [{ email: 'client@example.com' }],
      subject: 'Sujet',
      htmlContent: '<p>Bonjour</p>',
      attachment: [{ name: 'ticket.pdf', content: 'JVBERi0=' }],
    });
  });
});
