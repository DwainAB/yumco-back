/**
 * Comptes utilisateurs et appareils (user_service.py).
 */
import { env } from '../../config/env.js';
import { prisma } from '../../db/prisma.js';
import { badGateway, forbidden } from '../../lib/http-error.js';
import type { CurrentUser } from '../../middleware/auth.js';
import { sendEmail } from '../email/email.service.js';
import { generatePassword, hashPassword } from './password.js';
import type { UserCreate, UserUpdate } from './users.schemas.js';

const withRoles = { roles: { orderBy: { id: 'asc' } } } as const;

export const getUserByEmail = (email: string) => prisma.user.findFirst({ where: { email }, include: withRoles });

export const getUserById = (userId: number) => prisma.user.findFirst({ where: { id: userId }, include: withRoles });

/** Premier rôle d'un utilisateur, quel que soit le restaurant. */
export const firstRoleOf = (userId: number) => prisma.role.findFirst({ where: { user_id: userId }, orderBy: { id: 'asc' } });

/**
 * Crée le compte avec un mot de passe temporaire envoyé par e-mail.
 * Si l'e-mail ne part pas, rien n'est enregistré (502).
 */
export const createUser = async (data: UserCreate) => {
  const password = generatePassword();
  const hashed = await hashPassword(password);
  let userId: number;
  try {
    userId = await prisma.$transaction(
      async (tx) => {
        const user = await tx.user.create({
          data: {
            email: data.email,
            hashed_password: hashed,
            first_name: data.first_name,
            last_name: data.last_name,
            phone: data.phone ?? null,
            is_admin: data.is_admin,
          },
        });
        if (data.restaurant_id != null && data.role != null) {
          await tx.role.create({ data: { user_id: user.id, restaurant_id: data.restaurant_id, type: data.role } });
        }
        await sendEmail({
          to: data.email,
          subject: 'Bienvenue sur Yumco',
          body: `<h1>Bonjour ${data.first_name},</h1><p>Votre mot de passe temporaire : <strong>${password}</strong></p>`,
        });
        return user.id;
      },
      { timeout: 30_000 },
    );
  } catch (error) {
    throw badGateway(`User creation failed because welcome email could not be sent: ${(error as Error).message}`);
  }
  return prisma.user.findUniqueOrThrow({ where: { id: userId }, include: withRoles });
};

const MANAGER_ROLES = new Set(['owner', 'manager']);

/** Vérifie que `currentUser` peut changer le rôle de `user`. */
const assertCanChangeRole = async (user: CurrentUser, currentUser: CurrentUser, targetRestaurantId: number | null) => {
  if (env.STRICT_RESTAURANT_ACCESS) {
    // Correction : la permission est vérifiée sur le restaurant de l'utilisateur modifié.
    if (currentUser.is_admin) return;
    const role = targetRestaurantId === null ? null : currentUser.roles.find((r) => r.restaurant_id === targetRestaurantId);
    if (!role || !MANAGER_ROLES.has(role.type)) throw forbidden('Not allowed to change roles');
    return;
  }
  const currentRole = await firstRoleOf(currentUser.id);
  if (!currentRole || !MANAGER_ROLES.has(currentRole.type)) throw forbidden('Not allowed to change roles');
};

export const updateUser = async (user: CurrentUser, data: UserUpdate, currentUser: CurrentUser) => {
  if (data.role) {
    const userRole = await firstRoleOf(user.id);
    await assertCanChangeRole(user, currentUser, userRole?.restaurant_id ?? null);
    if (userRole) await prisma.role.update({ where: { id: userRole.id }, data: { type: data.role } });
  }

  const changes: Record<string, unknown> = {};
  for (const [field, value] of Object.entries(data)) {
    if (value === undefined) continue;
    if (field === 'password') {
      if (value !== null) changes.hashed_password = await hashPassword(value as string);
    } else if (field !== 'role' && field !== 'expo_push_token') {
      changes[field] = value;
    }
  }
  return prisma.user.update({ where: { id: user.id }, data: changes, include: withRoles });
};

export const registerUserDevice = async (user: CurrentUser, token: string, platform?: string | null, deviceName?: string | null) => {
  const fields = { user_id: user.id, platform: platform ?? null, device_name: deviceName ?? null, is_active: true, last_seen_at: new Date() };
  const device = await prisma.userDevice.findFirst({ where: { expo_push_token: token } });
  if (!device) return prisma.userDevice.create({ data: { expo_push_token: token, ...fields } });
  return prisma.userDevice.update({ where: { id: device.id }, data: fields });
};

export const unregisterUserDevice = async (user: CurrentUser, token: string) => {
  const device = await prisma.userDevice.findFirst({ where: { user_id: user.id, expo_push_token: token } });
  if (device) await prisma.userDevice.update({ where: { id: device.id }, data: { is_active: false, last_seen_at: new Date() } });
};

export const deleteUser = (userId: number) => prisma.user.delete({ where: { id: userId } });
