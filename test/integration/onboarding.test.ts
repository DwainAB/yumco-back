/**
 * Questionnaire du cockpit : liens d'invitation, création du restaurant, accès du gérant.
 */
import { describe, expect, it, vi } from 'vitest';
import { sendEmail } from '../../src/modules/email/email.service.js';
import { api, makeRestaurant, makeUser, prisma } from '../helpers.js';

const CLOUDINARY = `https://res.cloudinary.com/${process.env.CLOUDINARY_CLOUD_NAME}/image/upload/v1/yumco/onboarding`;

const COCKPIT = { 'x-cockpit-key': 'test-cockpit-key' };
const PNG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 0]);

const service = (open: string, close: string) => ({ open, close });
const openDay = { closed: false, lunch: service('12:00', '14:30'), dinner: service('19:00', '22:30') };

const answers = (overrides: Record<string, unknown> = {}) => ({
  name: 'Le Petit Bistrot',
  restaurantType: 'Bistrot',
  address: { street: '12 rue de la Paix', postalCode: '75002', city: 'Paris', country: 'France' },
  phone: '+33 1 23 45 67 89',
  email: 'Contact@PetitBistrot.fr',
  googleReviewUrl: 'https://g.page/r/petit-bistrot/review',
  manager: { firstName: 'Camille', lastName: 'Martin', email: 'camille@petitbistrot.fr', phone: '+33 6 12 34 56 78' },
  hours: {
    mon: { closed: true, lunch: null, dinner: null },
    tue: openDay,
    wed: openDay,
    thu: openDay,
    fri: openDay,
    sat: { closed: false, lunch: null, dinner: service('19:00', '23:30') },
    sun: { closed: true, lunch: null, dinner: null },
  },
  onsite: { enabled: true, tables: 3, seatsPerTable: 4 },
  takesReservations: true,
  onlineOrdering: true,
  pickup: true,
  preparationTime: 25,
  delivery: {
    enabled: true,
    lunch: false,
    dinner: true,
    maxKm: 6,
    zones: [
      { fromKm: 0, toKm: 3, fee: 2.5, freeFrom: 30 },
      { fromKm: 4, toKm: 6, fee: 4, freeFrom: null },
    ],
  },
  menu: { aLaCarte: true, allYouCanEat: true, formulas: [{ name: 'Midi', price: 19.9 }] },
  wantsOnlinePayment: true,
  customRequests: 'Mettre en avant la terrasse',
  logo: { id: 'logo', url: `${CLOUDINARY}/logo.png`, name: 'logo.png' },
  images: [{ file: { id: 'img', url: `${CLOUDINARY}/salle.png`, name: 'salle.png' }, description: 'La salle' }],
  branding: { colors: ['#1E3A5F'], font: 'Playfair Display' },
  ...overrides,
});

const newInvitation = async (plan = 'business_ai', recipient_email?: string) => {
  const res = await api().post('/onboarding/invitations').set(COCKPIT).send({ subscription_plan: plan, recipient_email });
  expect(res.status).toBe(201);
  return { ...res.body, token: new URL(res.body.url).searchParams.get('t')! } as { id: number; url: string; token: string; email_sent: boolean };
};

describe('accès du cockpit', () => {
  it('refuse les routes du cockpit sans la bonne clé', async () => {
    expect((await api().post('/onboarding/invitations').send({ subscription_plan: 'starter' })).status).toBe(401);
    expect((await api().get('/onboarding/submissions').set({ 'x-cockpit-key': 'mauvaise' })).status).toBe(401);
  });
});

describe('liens d’invitation', () => {
  it('crée un lien à usage unique vers la page du questionnaire, sans stocker le jeton', async () => {
    const invitation = await newInvitation('pro_ai');
    expect(invitation.url).toMatch(/^https:\/\/questionnaire\.yumco\.test\/\?t=[\w-]{43}$/);
    const row = await prisma.onboardingInvitation.findUniqueOrThrow({ where: { id: invitation.id } });
    expect(row.subscription_plan).toBe('pro_ai');
    expect(row.token_hash).not.toContain(invitation.token);
    expect((await api().get(`/onboarding/forms/${invitation.token}`)).body.status).toBe('open');
  });

  it('envoie le lien par e-mail quand une adresse est donnée', async () => {
    const invitation = await newInvitation('starter', 'resto@example.com');
    expect(invitation.email_sent).toBe(true);
    expect(sendEmail).toHaveBeenCalledWith(expect.objectContaining({ to: 'resto@example.com', body: expect.stringContaining(invitation.url.replace(/&/g, '&amp;')) }));
  });

  it('refuse une offre inconnue', async () => {
    expect((await api().post('/onboarding/invitations').set(COCKPIT).send({ subscription_plan: 'gold' })).status).toBe(422);
  });

  it('refuse un lien inconnu, expiré ou annulé', async () => {
    expect((await api().get(`/onboarding/forms/${'x'.repeat(43)}`)).status).toBe(404);

    const expired = await newInvitation();
    await prisma.onboardingInvitation.update({ where: { id: expired.id }, data: { expires_at: new Date(Date.now() - 1000) } });
    expect((await api().get(`/onboarding/forms/${expired.token}`)).status).toBe(410);

    const cancelled = await newInvitation();
    expect((await api().post(`/onboarding/invitations/${cancelled.id}/cancel`).set(COCKPIT)).status).toBe(204);
    expect((await api().post(`/onboarding/forms/${cancelled.token}/submit`).send(answers())).status).toBe(410);
  });
});

describe('questionnaire public', () => {
  it('crée le restaurant complet avec l’offre du lien', async () => {
    const invitation = await newInvitation('business_ai');
    const res = await api().post(`/onboarding/forms/${invitation.token}/submit`).send(answers());
    expect(res.status).toBe(201);

    const restaurant = await prisma.restaurant.findUniqueOrThrow({
      where: { id: res.body.restaurant_id },
      include: { address: true, config: true, delivery_tiers: { orderBy: { id: 'asc' } }, opening_hours: { orderBy: { day: 'asc' } }, tables: true, all_you_can_eat_offers: true, site: true },
    });
    expect(restaurant).toMatchObject({ name: 'Le Petit Bistrot', email: 'contact@petitbistrot.fr', subscription_plan: 'business_ai', ai_monthly_quota: 500, google_review_url: 'https://g.page/r/petit-bistrot/review' });
    expect(restaurant.address).toMatchObject({ street: '12 rue de la Paix', postal_code: '75002', city: 'Paris', country: 'France' });
    expect(restaurant.config).toMatchObject({
      accept_orders: true,
      preparation_time: 25,
      pickup: true,
      midday_delivery: false,
      evening_delivery: true,
      max_delivery_km: 6,
      onsite: true,
      reservation: true,
      a_la_carte: true,
      all_you_can_eat: true,
      payment_online: false,
      payment_onsite: true,
    });
    expect(restaurant.delivery_tiers.map((t) => [t.min_km, t.max_km, String(t.price), String(t.min_order_amount)])).toEqual([
      [0, 3, '2.5', '0'],
      [0, 3, '0', '30'],
      [4, 6, '4', '0'],
    ]);
    expect(restaurant.opening_hours).toHaveLength(7);
    expect(restaurant.opening_hours[0]).toMatchObject({ day: 0, is_closed: true, lunch_open: null });
    expect(restaurant.opening_hours[1]).toMatchObject({ day: 1, is_closed: false, lunch_open: '12:00', lunch_close: '14:30', dinner_open: '19:00', dinner_close: '22:30' });
    expect(restaurant.opening_hours[5]).toMatchObject({ day: 5, lunch_open: null, dinner_close: '23:30' });
    expect(restaurant.tables.map((t) => [t.table_number, t.number_of_people])).toEqual([['1', 4], ['2', 4], ['3', 4]]);
    expect(restaurant.all_you_can_eat_offers.map((o) => [o.name, String(o.price)])).toEqual([['Midi', '19.9']]);
    expect(restaurant.site).toMatchObject({
      invitation_id: invitation.id,
      status: 'design',
      cuisine_type: 'Bistrot',
      wants_online_payment: true,
      manager_email: 'camille@petitbistrot.fr',
      logo_url: `${CLOUDINARY}/logo.png`,
      brand_colors: ['#1E3A5F'],
      credentials_sent_at: null,
    });

    // Le lien ne sert qu'une fois.
    expect((await api().post(`/onboarding/forms/${invitation.token}/submit`).send(answers())).status).toBe(410);
    expect((await api().get(`/onboarding/forms/${invitation.token}`)).status).toBe(410);
    expect(await prisma.restaurant.count()).toBe(1);
  });

  it('ne crée ni livraison ni vente à emporter sans commande en ligne', async () => {
    const invitation = await newInvitation('starter');
    const res = await api()
      .post(`/onboarding/forms/${invitation.token}/submit`)
      .send(answers({ onlineOrdering: false, onsite: { enabled: false, tables: 0, seatsPerTable: 2 }, menu: { aLaCarte: true, allYouCanEat: false, formulas: [] } }));
    expect(res.status).toBe(201);
    const restaurant = await prisma.restaurant.findUniqueOrThrow({ where: { id: res.body.restaurant_id }, include: { config: true, delivery_tiers: true, tables: true } });
    expect(restaurant.subscription_plan).toBe('starter');
    expect(restaurant.config).toMatchObject({ accept_orders: false, pickup: false, midday_delivery: false, evening_delivery: false, max_delivery_km: null, onsite: false });
    expect(restaurant.delivery_tiers).toEqual([]);
    expect(restaurant.tables).toEqual([]);
  });

  it('refuse des réponses incohérentes', async () => {
    const { token } = await newInvitation();
    const post = (overrides: Record<string, unknown>) => api().post(`/onboarding/forms/${token}/submit`).send(answers(overrides));
    const delivery = answers().delivery;

    expect((await post({ hours: Object.fromEntries(['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'].map((d) => [d, { closed: true, lunch: null, dinner: null }])) })).status).toBe(422);
    expect((await post({ delivery: { ...delivery, zones: [{ fromKm: 0, toKm: 3, fee: 2, freeFrom: null }, { fromKm: 3, toKm: 6, fee: 4, freeFrom: null }] } })).status).toBe(422);
    expect((await post({ delivery: { ...delivery, maxKm: 5 } })).status).toBe(422);
    expect((await post({ delivery: { ...delivery, lunch: false, dinner: false } })).status).toBe(422);
    expect((await post({ pickup: false, delivery: { ...delivery, enabled: false } })).status).toBe(422);
    expect((await post({ menu: { aLaCarte: false, allYouCanEat: false, formulas: [] } })).status).toBe(422);
    // Images venues d'ailleurs que le formulaire.
    expect((await post({ logo: { id: 'x', url: 'https://example.com/logo.png', name: 'logo.png' } })).status).toBe(422);
    expect(await prisma.restaurant.count()).toBe(0);
  });

  it('reçoit les images envoyées depuis le lien', async () => {
    const { token } = await newInvitation();
    const res = await api().post(`/onboarding/forms/${token}/uploads`).attach('file', PNG, 'salle.png');
    expect(res.status).toBe(201);
    expect(res.body.url).toBe(`${CLOUDINARY}/photo.png`);
    expect((await api().post(`/onboarding/forms/${token}/uploads`).attach('file', Buffer.from('pas une image'), 'x.png')).status).toBe(415);
    expect((await api().post(`/onboarding/forms/${'y'.repeat(43)}/uploads`).attach('file', PNG, 'a.png')).status).toBe(404);
  });
});

describe('suivi par le cockpit', () => {
  it('liste les questionnaires reçus, puis les marque comme récupérés', async () => {
    const invitation = await newInvitation();
    const { body } = await api().post(`/onboarding/forms/${invitation.token}/submit`).send(answers());

    const submissions = await api().get('/onboarding/submissions').set(COCKPIT);
    expect(submissions.body).toHaveLength(1);
    expect(submissions.body[0]).toMatchObject({ id: invitation.id, status: 'submitted', restaurant_id: body.restaurant_id, restaurant_name: 'Le Petit Bistrot' });
    expect(submissions.body[0].answers.manager.firstName).toBe('Camille');
    expect(submissions.body[0].platform_url).toBe(`https://platform.yumco.fr/le-petit-bistrot-${body.restaurant_id}`);

    expect((await api().post(`/onboarding/submissions/${invitation.id}/imported`).set(COCKPIT)).status).toBe(204);
    expect((await api().get('/onboarding/submissions').set(COCKPIT)).body).toEqual([]);
    expect((await api().post(`/onboarding/submissions/${invitation.id}/imported`).set(COCKPIT)).status).toBe(409);
  });

  it('crée le restaurant directement depuis le cockpit avec l’offre choisie', async () => {
    const res = await api()
      .post('/onboarding/restaurants')
      .set(COCKPIT)
      .send({ subscription_plan: 'pro_ai', answers: answers({ logo: { id: 'l', url: '/api/uploads/0b5c.png', name: 'logo.png' } }) });
    expect(res.status).toBe(201);
    const restaurant = await prisma.restaurant.findUniqueOrThrow({ where: { id: res.body.restaurant_id }, include: { site: true } });
    expect(restaurant.subscription_plan).toBe('pro_ai');
    // Fichier local du cockpit : pas d'URL publique à garder.
    expect(restaurant.site).toMatchObject({ invitation_id: null, logo_url: null });
    expect(res.body.platform_url).toBe(`https://platform.yumco.fr/le-petit-bistrot-${res.body.restaurant_id}`);
  });

  it('met à jour la fiche du site', async () => {
    const { body } = await api().post('/onboarding/restaurants').set(COCKPIT).send({ subscription_plan: 'starter', answers: answers() });
    const res = await api().patch(`/onboarding/restaurants/${body.restaurant_id}/site`).set(COCKPIT).send({ status: 'development', repo_url: 'https://github.com/Yumco/le-petit-bistrot' });
    expect(res.status).toBe(200);
    expect(res.body).toMatchObject({ status: 'development', repo_url: 'https://github.com/Yumco/le-petit-bistrot' });
    expect((await api().get(`/onboarding/restaurants/${body.restaurant_id}/site`).set(COCKPIT)).body.status).toBe('development');
  });
});

describe('accès du gérant', () => {
  const createRestaurant = async () =>
    (await api().post('/onboarding/restaurants').set(COCKPIT).send({ subscription_plan: 'starter', answers: answers() })).body.restaurant_id as number;

  it('crée le compte propriétaire et envoie le mot de passe provisoire, une seule fois', async () => {
    const restaurantId = await createRestaurant();
    const res = await api().post(`/onboarding/restaurants/${restaurantId}/credentials`).set(COCKPIT).send({ site_url: 'https://lepetitbistrot.fr' });
    expect(res.status).toBe(200);
    expect(res.body.account_created).toBe(true);

    const user = await prisma.user.findUniqueOrThrow({ where: { email: 'camille@petitbistrot.fr' }, include: { roles: true } });
    expect(user).toMatchObject({ first_name: 'Camille', last_name: 'Martin', is_admin: false });
    expect(user.roles).toEqual([expect.objectContaining({ restaurant_id: restaurantId, type: 'owner' })]);

    const mail = vi.mocked(sendEmail).mock.calls.at(-1)![0];
    expect(mail.to).toBe('camille@petitbistrot.fr');
    expect(mail.body).toContain('https://lepetitbistrot.fr');
    expect(mail.body).toContain('Paramètres › Mon profil › Mot de passe');
    const password = /monospace;font-size:16px">([^<]+)</.exec(mail.body)![1].replace(/&amp;/g, '&');
    const login = await api().post('/auth/login').send({ email: 'camille@petitbistrot.fr', password });
    expect(login.status).toBe(200);

    const site = await prisma.restaurantSite.findUniqueOrThrow({ where: { restaurant_id: restaurantId } });
    expect(site).toMatchObject({ status: 'online', site_url: 'https://lepetitbistrot.fr', owner_user_id: user.id });
    expect((await api().post(`/onboarding/restaurants/${restaurantId}/credentials`).set(COCKPIT).send({ site_url: 'https://lepetitbistrot.fr' })).status).toBe(409);
  });

  it('rattache un compte existant sans changer son mot de passe', async () => {
    const existing = await makeUser({ email: 'camille@petitbistrot.fr', password: 'ancien-mot-de-passe' });
    await makeRestaurant(existing.id, 'Autre restaurant');
    const restaurantId = await createRestaurant();
    const res = await api().post(`/onboarding/restaurants/${restaurantId}/credentials`).set(COCKPIT).send({ site_url: 'https://lepetitbistrot.fr' });
    expect(res.body).toMatchObject({ account_created: false, user_id: existing.id });
    expect(await prisma.role.count({ where: { user_id: existing.id } })).toBe(2);
    expect(vi.mocked(sendEmail).mock.calls.at(-1)![0].body).not.toContain('Mot de passe provisoire');
    expect((await api().post('/auth/login').send({ email: 'camille@petitbistrot.fr', password: 'ancien-mot-de-passe' })).status).toBe(200);
  });

  it('n’enregistre rien si l’e-mail ne part pas', async () => {
    const restaurantId = await createRestaurant();
    vi.mocked(sendEmail).mockRejectedValueOnce(new Error('Brevo indisponible'));
    const res = await api().post(`/onboarding/restaurants/${restaurantId}/credentials`).set(COCKPIT).send({ site_url: 'https://lepetitbistrot.fr' });
    expect(res.status).toBe(502);
    expect(await prisma.user.count()).toBe(0);
    expect((await prisma.restaurantSite.findUniqueOrThrow({ where: { restaurant_id: restaurantId } })).credentials_sent_at).toBeNull();
  });
});
