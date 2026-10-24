/**
 * Avant chaque fichier de test : configuration de test, services externes simulés, base vidée entre les tests.
 */
import { afterAll, afterEach, beforeEach, vi } from 'vitest';

process.loadEnvFile('.env.test');

// Aucun e-mail, aucune notification, aucun appel à Nominatim ni à Cloudinary pendant les tests.
vi.mock('../src/modules/email/email.service.js', async (importOriginal) => {
  const original = await importOriginal<typeof import('../src/modules/email/email.service.js')>();
  return { ...original, sendEmail: vi.fn(async () => undefined), sendEmailSafe: vi.fn(async () => true) };
});
vi.mock('../src/modules/notifications/push.service.js', async (importOriginal) => {
  const original = await importOriginal<typeof import('../src/modules/notifications/push.service.js')>();
  return { ...original, notifyNewOrder: vi.fn(async () => undefined), notifyNewReservation: vi.fn(async () => undefined) };
});
vi.mock('../src/modules/geo/geo.service.js', async (importOriginal) => {
  const original = await importOriginal<typeof import('../src/modules/geo/geo.service.js')>();
  return { ...original, geocodeAddress: vi.fn(async () => ({ lat: 48.8566, lng: 2.3522, place_name: 'Paris' })) };
});
vi.mock('../src/modules/uploads/cloudinary.service.js', () => ({
  uploadImage: vi.fn(async (_file: Buffer, folder = 'yumco/products') => `https://res.cloudinary.com/${process.env.CLOUDINARY_CLOUD_NAME}/image/upload/v1/${folder}/photo.png`),
  deleteImage: vi.fn(async () => ({ result: 'ok' })),
}));

const { truncateAll } = await import('./helpers.js');
const { flushBackgroundTasks } = await import('../src/lib/background.js');
const { prisma } = await import('../src/db/prisma.js');

beforeEach(async () => {
  await truncateAll();
});

afterEach(async () => {
  await flushBackgroundTasks();
  vi.clearAllMocks();
});

afterAll(async () => {
  await prisma.$disconnect();
});
