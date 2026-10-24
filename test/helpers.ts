/**
 * Données et outils communs aux tests (helpers de tests/integration/conftest.py).
 */
import supertest from 'supertest';
import { createApp } from '../src/app.js';
import { prisma } from '../src/db/prisma.js';
import { Prisma } from '../src/generated/prisma/client.js';
import { createAccessToken } from '../src/modules/auth/jwt.js';
import { hashPassword } from '../src/modules/auth/password.js';

export { prisma };

export const app = createApp();
export const api = () => supertest(app);

/** Tables vidées avant chaque test (identifiants remis à 1). */
const TABLES = [
  'ai_conversation_messages',
  'ai_conversations',
  'hubrise_order_logs',
  'hubrise_connections',
  'order_items',
  'orders',
  'pending_online_orders',
  'restaurant_promo_codes',
  'review_followups',
  'restaurant_announcements',
  'delivery_tiers',
  'all_you_can_eat',
  'menu_options',
  'menu_categories',
  'menus',
  'products',
  'categories',
  'opening_hours',
  'reservations',
  'tables',
  'customers',
  'restaurant_configs',
  'user_devices',
  'roles',
  'restaurants',
  'addresses',
  'users',
];

export const truncateAll = () => prisma.$executeRawUnsafe(`TRUNCATE TABLE ${TABLES.map((t) => `"${t}"`).join(', ')} RESTART IDENTITY CASCADE`);

export const makeUser = async ({ email = 'owner@test.com', password = 'password123', isAdmin = false } = {}) =>
  prisma.user.create({
    data: {
      email,
      first_name: 'Test',
      last_name: 'Owner',
      phone: '+33600000001',
      hashed_password: await hashPassword(password),
      is_admin: isAdmin,
    },
  });

export const makeRestaurant = async (ownerId: number, name = 'Test Restaurant') => {
  const address = await prisma.address.create({ data: { street: '1 Rue du Test', city: 'Paris', postal_code: '75001', country: 'FR' } });
  const restaurant = await prisma.restaurant.create({
    data: {
      name,
      email: 'contact@test.com',
      phone: '+33100000001',
      timezone: 'Europe/Paris',
      address_id: address.id,
      subscription_status: 'active',
      subscription_plan: 'starter',
      ai_monthly_quota: 100,
      ai_monthly_token_quota: 10000,
      is_deleted: false,
      stripe_charges_enabled: false,
      stripe_payouts_enabled: false,
      stripe_details_submitted: false,
      subscription_interval: 'month',
      subscription_cancel_at_period_end: false,
      has_tablet_rental: false,
      has_printer_rental: false,
    },
  });
  await prisma.restaurantConfig.create({
    data: {
      restaurant_id: restaurant.id,
      accept_orders: true,
      preparation_time: 15,
      midday_delivery: true,
      evening_delivery: true,
      pickup: true,
      onsite: true,
      reservation: true,
      all_you_can_eat: false,
      a_la_carte: true,
      payment_online: false,
      payment_onsite: true,
      printer_enabled: false,
    },
  });
  await prisma.role.create({ data: { user_id: ownerId, restaurant_id: restaurant.id, type: 'owner' } });
  return restaurant;
};

export const makeCategory = (restaurantId: number, name = 'Burgers') => prisma.category.create({ data: { restaurant_id: restaurantId, name } });

export const makeProduct = (restaurantId: number, categoryId: number, name = 'Burger', price = 12.5) =>
  prisma.product.create({
    data: {
      restaurant_id: restaurantId,
      category_id: categoryId,
      name,
      price: new Prisma.Decimal(String(price)),
      is_available: true,
      is_deleted: false,
      available_online: true,
      available_onsite: true,
      group: 'main',
      allergens: [],
    },
  });

export const authHeaders = async (email: string) => ({ Authorization: `Bearer ${await createAccessToken(email)}` });
