/**
 * Questionnaire du cockpit : liens d'invitation, création du restaurant à partir des réponses, accès du gérant.
 *
 * Parcours : le cockpit crée un lien (une offre, usage unique) → le restaurateur remplit le questionnaire → le restaurant
 * est créé aussitôt → le cockpit récupère les réponses et lance le design → une fois le site en ligne, le cockpit demande
 * l'envoi des accès : le compte du gérant est créé avec un mot de passe provisoire envoyé par e-mail.
 */
import { createHash, randomBytes } from 'node:crypto';
import { env } from '../../config/env.js';
import { prisma, Prisma, type Tx } from '../../db/prisma.js';
import { conflict, HttpError, notFound, serviceUnavailable, badGateway } from '../../lib/http-error.js';
import { generatePassword, hashPassword } from '../auth/password.js';
import { sendEmail } from '../email/email.service.js';
import { insertRestaurant } from '../restaurants/restaurants.service.js';
import type { RestaurantCreate } from '../restaurants/restaurants.schemas.js';
import { credentialsEmail, invitationEmail } from './onboarding.emails.js';
import { DAY_KEYS, type QuestionnaireAnswers, type SubscriptionPlan } from './onboarding.schemas.js';

/** Images envoyées au plus depuis un même lien (logo + 15 images, avec de la marge pour les remplacements). */
export const MAX_UPLOADS_PER_INVITATION = 40;

const gone = (detail: string) => new HttpError(410, detail);

const hashToken = (token: string) => createHash('sha256').update(token).digest('hex');

const formLink = (token: string) => {
  if (!env.ONBOARDING_FORM_URL) throw serviceUnavailable('ONBOARDING_FORM_URL is not configured');
  const url = new URL(env.ONBOARDING_FORM_URL);
  url.searchParams.set('t', token);
  return url.toString();
};

/** Même règle que la plateforme (lib/restaurantRoutes.js) : `<nom-en-minuscules>-<id>`. */
export const platformUrl = (restaurantId: number, name: string) => {
  const slug = name
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return `${env.PLATFORM_BASE_URL.replace(/\/$/, '')}/${slug ? `${slug}-${restaurantId}` : restaurantId}`;
};

/* ---------- Liens d'invitation ---------- */

export const createInvitation = async (plan: SubscriptionPlan, recipientEmail: string | null) => {
  const token = randomBytes(32).toString('base64url');
  const url = formLink(token);
  const expiresAt = new Date(Date.now() + env.ONBOARDING_LINK_DAYS * 24 * 3600 * 1000);
  const invitation = await prisma.onboardingInvitation.create({
    data: { token_hash: hashToken(token), subscription_plan: plan, recipient_email: recipientEmail, expires_at: expiresAt },
  });

  let emailError: string | null = null;
  if (recipientEmail) {
    try {
      await sendEmail({ to: recipientEmail, ...invitationEmail(url, expiresAt) });
    } catch (error) {
      emailError = (error as Error).message;
    }
  }
  return { invitation, url, emailSent: Boolean(recipientEmail) && !emailError, emailError };
};

export const listInvitations = () =>
  prisma.onboardingInvitation.findMany({ orderBy: { id: 'desc' }, take: 100, include: { restaurant: { select: { name: true } } } });

export const cancelInvitation = async (invitationId: number) => {
  const { count } = await prisma.onboardingInvitation.updateMany({ where: { id: invitationId, status: 'pending' }, data: { status: 'cancelled' } });
  if (!count) throw conflict('Only a pending invitation can be cancelled');
};

/** Lien encore utilisable : sinon 404 (inconnu) ou 410 (déjà envoyé, annulé ou expiré). */
export const findOpenInvitation = async (token: string) => {
  const invitation = await prisma.onboardingInvitation.findUnique({ where: { token_hash: hashToken(token) } });
  if (!invitation) throw notFound('Invitation not found');
  if (invitation.status !== 'pending') throw gone(invitation.status === 'cancelled' ? 'Invitation cancelled' : 'Questionnaire already submitted');
  if (invitation.expires_at.getTime() < Date.now()) throw gone('Invitation expired');
  return invitation;
};

/** Compte une image envoyée depuis le lien ; refuse au-delà de la limite. */
export const registerUpload = async (invitationId: number) => {
  const { count } = await prisma.onboardingInvitation.updateMany({
    where: { id: invitationId, status: 'pending', upload_count: { lt: MAX_UPLOADS_PER_INVITATION } },
    data: { upload_count: { increment: 1 } },
  });
  if (!count) throw new HttpError(429, 'Too many uploads for this invitation');
};

/* ---------- Création du restaurant ---------- */

const money = (value: number) => new Prisma.Decimal(value.toFixed(2));

/** Réponses → restaurant au format de POST /restaurants (même transformation que l'application pour les zones). */
export const toRestaurantCreate = (a: QuestionnaireAnswers, plan: SubscriptionPlan): RestaurantCreate => {
  const delivers = a.onlineOrdering && a.delivery.enabled;
  return {
    name: a.name,
    email: a.email,
    phone: a.phone,
    google_review_url: a.googleReviewUrl || null,
    address: { street: a.address.street, city: a.address.city, postal_code: a.address.postalCode, country: a.address.country },
    subscription_plan: plan,
    config: {
      accept_orders: a.onlineOrdering,
      preparation_time: a.preparationTime,
      pickup: a.onlineOrdering && a.pickup,
      midday_delivery: delivers && a.delivery.lunch,
      evening_delivery: delivers && a.delivery.dinner,
      max_delivery_km: delivers ? a.delivery.maxKm : null,
      onsite: a.onsite.enabled,
      reservation: a.takesReservations,
      a_la_carte: a.menu.aLaCarte,
      all_you_can_eat: a.menu.allYouCanEat,
      // Paiement en ligne : activé à la main une fois le compte Stripe du restaurant configuré.
      payment_online: false,
      payment_onsite: true,
    },
    // Une zone « frais X €, gratuite dès Y € » = deux tranches, comme dans l'application (InformationScreen).
    delivery_tiers: delivers
      ? a.delivery.zones.flatMap((zone) => [
          { min_km: zone.fromKm, max_km: zone.toKm, price: money(zone.fee), min_order_amount: money(0) },
          ...(zone.freeFrom !== null ? [{ min_km: zone.fromKm, max_km: zone.toKm, price: money(0), min_order_amount: money(zone.freeFrom) }] : []),
        ])
      : [],
    opening_hours: DAY_KEYS.map((key, index) => {
      const d = a.hours[key];
      const closed = d.closed || (!d.lunch && !d.dinner);
      return {
        day: index,
        lunch_open: closed ? null : (d.lunch?.open ?? null),
        lunch_close: closed ? null : (d.lunch?.close ?? null),
        dinner_open: closed ? null : (d.dinner?.open ?? null),
        dinner_close: closed ? null : (d.dinner?.close ?? null),
        is_closed: closed,
      };
    }),
  };
};

const isRemote = (url: string) => url.startsWith('https://');

const insertOnboardedRestaurant = async (tx: Tx, a: QuestionnaireAnswers, plan: SubscriptionPlan, invitationId: number | null) => {
  const restaurantId = await insertRestaurant(tx, toRestaurantCreate(a, plan));

  if (a.onsite.enabled && a.onsite.tables > 0) {
    await tx.table.createMany({
      data: Array.from({ length: a.onsite.tables }, (_, i) => ({
        restaurant_id: restaurantId,
        table_number: String(i + 1),
        number_of_people: a.onsite.seatsPerTable,
        is_available: true,
        temporary: false,
      })),
    });
  }
  if (a.menu.allYouCanEat && a.menu.formulas.length) {
    await tx.allYouCanEat.createMany({ data: a.menu.formulas.map((f) => ({ restaurant_id: restaurantId, name: f.name, price: money(f.price) })) });
  }

  await tx.restaurantSite.create({
    data: {
      restaurant_id: restaurantId,
      invitation_id: invitationId,
      cuisine_type: a.restaurantType,
      custom_requests: a.customRequests || null,
      // Images du cockpit (fichiers locaux) : seules les URL publiques sont gardées en base.
      logo_url: a.logo && isRemote(a.logo.url) ? a.logo.url : null,
      images: a.images.filter((img) => isRemote(img.file.url)).map((img) => ({ url: img.file.url, description: img.description })),
      brand_colors: a.branding.colors,
      brand_font: a.branding.font,
      wants_online_payment: a.wantsOnlinePayment,
      manager_first_name: a.manager.firstName,
      manager_last_name: a.manager.lastName,
      manager_email: a.manager.email,
      manager_phone: a.manager.phone,
    },
  });
  return restaurantId;
};

/** Questionnaire rempli depuis le lien : le lien est consommé et le restaurant créé dans la même transaction. */
export const submitInvitation = (invitationId: number, plan: SubscriptionPlan, answers: QuestionnaireAnswers) =>
  prisma.$transaction(async (tx) => {
    // Garde contre un double envoi : seul le premier passe.
    const { count } = await tx.onboardingInvitation.updateMany({
      where: { id: invitationId, status: 'pending' },
      data: { status: 'submitted', answers: answers as Prisma.InputJsonValue, submitted_at: new Date() },
    });
    if (!count) throw gone('Questionnaire already submitted');
    const restaurantId = await insertOnboardedRestaurant(tx, answers, plan, invitationId);
    await tx.onboardingInvitation.update({ where: { id: invitationId }, data: { restaurant_id: restaurantId } });
    return restaurantId;
  });

/** Questionnaire rempli directement dans le cockpit, sans lien. */
export const createFromCockpit = (plan: SubscriptionPlan, answers: QuestionnaireAnswers) =>
  prisma.$transaction((tx) => insertOnboardedRestaurant(tx, answers, plan, null));

/* ---------- Suivi par le cockpit ---------- */

/** Questionnaires envoyés depuis un lien, pas encore récupérés par le cockpit. */
export const listSubmissions = () =>
  prisma.onboardingInvitation.findMany({ where: { status: 'submitted' }, orderBy: { submitted_at: 'asc' }, include: { restaurant: { select: { name: true } } } });

export const markImported = async (invitationId: number) => {
  const { count } = await prisma.onboardingInvitation.updateMany({
    where: { id: invitationId, status: 'submitted' },
    data: { status: 'imported', imported_at: new Date() },
  });
  if (!count) throw conflict('Only a submitted questionnaire can be marked as imported');
};

const findSite = async (restaurantId: number) => {
  const site = await prisma.restaurantSite.findUnique({ where: { restaurant_id: restaurantId }, include: { restaurant: { include: { config: true } } } });
  if (!site || site.restaurant.is_deleted) throw notFound('Restaurant site not found');
  return site;
};

export const getSite = findSite;

export const updateSite = async (restaurantId: number, data: { status?: string; site_url?: string | null; repo_url?: string | null }) => {
  await findSite(restaurantId);
  return prisma.restaurantSite.update({ where: { restaurant_id: restaurantId }, data });
};

/**
 * Site en ligne : crée le compte du gérant (propriétaire du restaurant) et lui envoie ses accès.
 * Si l'e-mail ne part pas, rien n'est enregistré (502), comme à la création d'un compte.
 * Si un compte existe déjà avec cet e-mail, il est rattaché au restaurant et garde son mot de passe.
 */
export const sendCredentials = async (restaurantId: number, siteUrl: string) => {
  const site = await findSite(restaurantId);
  if (site.credentials_sent_at) throw conflict('Credentials already sent for this restaurant');

  const existing = await prisma.user.findFirst({ where: { email: { equals: site.manager_email, mode: 'insensitive' } } });
  const temporaryPassword = existing ? null : generatePassword();
  const hashed = temporaryPassword ? await hashPassword(temporaryPassword) : null;
  const config = site.restaurant.config;
  const message = credentialsEmail({
    firstName: site.manager_first_name,
    restaurantName: site.restaurant.name,
    siteUrl,
    platformUrl: config?.accept_orders || config?.reservation ? platformUrl(restaurantId, site.restaurant.name) : null,
    email: existing?.email ?? site.manager_email,
    temporaryPassword,
  });

  try {
    return await prisma.$transaction(
      async (tx) => {
        const user =
          existing ??
          (await tx.user.create({
            data: {
              email: site.manager_email,
              hashed_password: hashed!,
              first_name: site.manager_first_name,
              last_name: site.manager_last_name,
              phone: site.manager_phone,
              is_admin: false,
            },
          }));
        await tx.role.upsert({
          where: { user_id_restaurant_id: { user_id: user.id, restaurant_id: restaurantId } },
          create: { user_id: user.id, restaurant_id: restaurantId, type: 'owner' },
          update: { type: 'owner' },
        });
        const updated = await tx.restaurantSite.update({
          where: { restaurant_id: restaurantId },
          data: { owner_user_id: user.id, credentials_sent_at: new Date(), status: 'online', site_url: siteUrl },
        });
        await sendEmail({ to: user.email, ...message });
        return { site: updated, userId: user.id, accountCreated: !existing };
      },
      { timeout: 30_000 },
    );
  } catch (error) {
    if (error instanceof HttpError) throw error;
    throw badGateway(`Credentials could not be sent: ${(error as Error).message}`);
  }
};
