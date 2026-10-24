/**
 * E-mails du questionnaire : lien envoyé au restaurateur, puis accès envoyés au gérant une fois le site en ligne.
 */
import { env } from '../../config/env.js';

const escapeHtml = (value: string) =>
  value.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);

const layout = (content: string) => `<!doctype html>
<html lang="fr"><body style="margin:0;padding:24px;background:#f5f5f7;font-family:Arial,Helvetica,sans-serif;color:#1d1d1f">
<div style="max-width:560px;margin:0 auto;background:#fff;border-radius:12px;padding:32px;line-height:1.55;font-size:15px">
${content}
<p style="margin-top:32px;color:#6e6e73;font-size:13px">L’équipe Yumco</p>
</div></body></html>`;

const button = (href: string, label: string) =>
  `<p style="margin:24px 0"><a href="${escapeHtml(href)}" style="display:inline-block;background:#ff6b6b;color:#fff;text-decoration:none;padding:12px 22px;border-radius:8px;font-weight:bold">${escapeHtml(label)}</a></p>`;

export const invitationEmail = (link: string, expiresAt: Date) => ({
  subject: 'Créons ensemble le site de votre restaurant',
  body: layout(`
<h1 style="font-size:22px;margin:0 0 16px">Bonjour,</h1>
<p>Pour créer le site internet de votre restaurant et votre espace de commande en ligne, il ne reste qu’à répondre à quelques questions : informations du restaurant, horaires, services, livraison et identité visuelle.</p>
${button(link, 'Remplir le questionnaire')}
<p>Comptez une quinzaine de minutes. Une fois le questionnaire envoyé, nous nous occupons de tout et vous recevrez vos accès dès que votre site sera en ligne.</p>
<p style="color:#6e6e73;font-size:13px">Ce lien est personnel et valable jusqu’au ${expiresAt.toLocaleDateString('fr-FR', { timeZone: 'Europe/Paris' })}.</p>`),
});

interface CredentialsEmail {
  firstName: string;
  restaurantName: string;
  siteUrl: string;
  platformUrl: string | null;
  email: string;
  /** null : le compte existait déjà, le gérant garde son mot de passe. */
  temporaryPassword: string | null;
}

export const credentialsEmail = ({ firstName, restaurantName, siteUrl, platformUrl, email, temporaryPassword }: CredentialsEmail) => {
  const stores = [
    env.APP_IOS_URL ? `<a href="${escapeHtml(env.APP_IOS_URL)}">App Store (iPhone)</a>` : null,
    `<a href="${escapeHtml(env.APP_ANDROID_URL)}">Google Play (Android)</a>`,
  ].filter(Boolean);
  const access = temporaryPassword
    ? `<p>Vos identifiants de connexion :</p>
<table style="border-collapse:collapse;margin:8px 0 16px">
<tr><td style="padding:4px 16px 4px 0;color:#6e6e73">E-mail</td><td style="padding:4px 0"><strong>${escapeHtml(email)}</strong></td></tr>
<tr><td style="padding:4px 16px 4px 0;color:#6e6e73">Mot de passe provisoire</td><td style="padding:4px 0"><strong style="font-family:monospace;font-size:16px">${escapeHtml(temporaryPassword)}</strong></td></tr>
</table>
<p>Après votre première connexion, choisissez votre propre mot de passe dans <strong>Paramètres › Mon profil › Mot de passe</strong>.</p>`
    : `<p>Connectez-vous avec votre compte habituel (<strong>${escapeHtml(email)}</strong>) : ${escapeHtml(restaurantName)} y apparaît désormais.</p>`;

  return {
    subject: `Votre site ${restaurantName} est en ligne`,
    body: layout(`
<h1 style="font-size:22px;margin:0 0 16px">Bonjour ${escapeHtml(firstName)},</h1>
<p>Bonne nouvelle : le site internet de <strong>${escapeHtml(restaurantName)}</strong> est prêt et actuellement en ligne.</p>
${button(siteUrl, 'Voir mon site')}
${platformUrl ? `<p>Votre page de commande et de réservation : <a href="${escapeHtml(platformUrl)}">${escapeHtml(platformUrl)}</a></p>` : ''}
<h2 style="font-size:17px;margin:28px 0 8px">Gérer votre restaurant</h2>
<p>Votre menu, vos horaires, vos commandes et vos réservations se gèrent depuis l’application Yumco : ${stores.join(' · ')}.</p>
${access}
<h2 style="font-size:17px;margin:28px 0 8px">Dernière étape</h2>
<p>Ajoutez vos plats dans l’application : ils apparaîtront aussitôt sur votre page de commande. Tout le reste (horaires, livraison, services) est déjà configuré d’après vos réponses, et reste modifiable dans l’application.</p>`),
  };
};
