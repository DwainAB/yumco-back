/**
 * Routes /auth (routes/auth.py).
 */
import { Router } from 'express';
import { prisma } from '../../db/prisma.js';
import { badGateway, badRequest, forbidden, notFound, unauthorized } from '../../lib/http-error.js';
import { intParams, validateRequest } from '../../lib/validation.js';
import { authenticate, checkPermission, currentUser, type CurrentUser } from '../../middleware/auth.js';
import { sendEmail } from '../email/email.service.js';
import { createAccessToken } from './jwt.js';
import { generatePassword, hashPassword, verifyPassword } from './password.js';
import {
  ResetPasswordQuery,
  UserCreate,
  UserDeviceRegisterRequest,
  UserDeviceUnregisterRequest,
  UserLogin,
  UserUpdate,
} from './users.schemas.js';
import { toUserDeviceResponse, toUserResponse } from './users.serializers.js';
import {
  createUser,
  deleteUser,
  firstRoleOf,
  getUserByEmail,
  getUserById,
  registerUserDevice,
  unregisterUserDevice,
  updateUser,
} from './users.service.js';

export const authRouter = Router();

/** Un utilisateur rattaché à un restaurant ne peut être géré que par l'équipe de ce restaurant (ou un admin). */
const assertCanManageUser = async (current: CurrentUser, userId: number) => {
  const userRole = await firstRoleOf(userId);
  if (userRole) await checkPermission(current, userRole.restaurant_id);
  else if (!current.is_admin) throw forbidden('Not allowed');
};

authRouter.post('/auth/bootstrap-admin', async (req, res) => {
  const { body } = validateRequest(req, { body: UserCreate });
  const adminExists = await prisma.user.findFirst({ where: { is_admin: true } });
  if (adminExists) throw forbidden('Bootstrap admin is no longer available');
  if (!body.is_admin) throw badRequest('bootstrap-admin only allows admin users');
  if (await getUserByEmail(body.email)) throw badRequest('Email already registered');
  res.status(201).json(toUserResponse(await createUser(body)));
});

authRouter.post('/auth/register', authenticate, async (req, res) => {
  const { body } = validateRequest(req, { body: UserCreate });
  const current = currentUser(req);
  if (body.is_admin) {
    if (!current.is_admin) throw forbidden('Not allowed to create admin users');
  } else {
    if (body.restaurant_id == null) throw badRequest('restaurant_id is required for non-admin users');
    await checkPermission(current, body.restaurant_id);
  }
  if (await getUserByEmail(body.email)) throw badRequest('Email already registered');
  res.status(201).json(toUserResponse(await createUser(body)));
});

authRouter.post('/auth/login', async (req, res) => {
  const { body } = validateRequest(req, { body: UserLogin });
  const user = await getUserByEmail(body.email);
  if (!user || !(await verifyPassword(body.password, user.hashed_password))) throw unauthorized('Invalid email or password');
  res.json({ access_token: await createAccessToken(user.email), token_type: 'bearer' });
});

authRouter.get('/auth/me', authenticate, (req, res) => {
  res.json(toUserResponse(currentUser(req)));
});

authRouter.put('/auth/me', authenticate, async (req, res) => {
  const { body } = validateRequest(req, { body: UserUpdate });
  const current = currentUser(req);
  res.json(toUserResponse(await updateUser(current, body, current)));
});

authRouter.post('/auth/me/devices/push-token', authenticate, async (req, res) => {
  const { body } = validateRequest(req, { body: UserDeviceRegisterRequest });
  res.json(toUserDeviceResponse(await registerUserDevice(currentUser(req), body.expo_push_token, body.platform, body.device_name)));
});

authRouter.delete('/auth/me/devices/push-token', authenticate, async (req, res) => {
  const { body } = validateRequest(req, { body: UserDeviceUnregisterRequest });
  await unregisterUserDevice(currentUser(req), body.expo_push_token);
  res.status(204).end();
});

authRouter.delete('/auth/me', authenticate, async (req, res) => {
  await deleteUser(currentUser(req).id);
  res.status(204).end();
});

authRouter.put('/auth/users/:user_id', authenticate, async (req, res) => {
  const { params, body } = validateRequest(req, { params: intParams('user_id'), body: UserUpdate });
  const user = await getUserById(params.user_id);
  if (!user) throw notFound('User not found');
  const current = currentUser(req);
  await assertCanManageUser(current, user.id);
  res.json(toUserResponse(await updateUser(user, body, current)));
});

authRouter.delete('/auth/users/:user_id', authenticate, async (req, res) => {
  const { params } = validateRequest(req, { params: intParams('user_id') });
  const user = await getUserById(params.user_id);
  if (!user) throw notFound('User not found');
  await assertCanManageUser(currentUser(req), user.id);
  await deleteUser(user.id);
  res.status(204).end();
});

authRouter.post('/auth/reset-password', authenticate, async (req, res) => {
  const { query } = validateRequest(req, { query: ResetPasswordQuery });
  const user = await getUserByEmail(query.email);
  if (!user) throw notFound('User not found');
  await assertCanManageUser(currentUser(req), user.id);

  const newPassword = generatePassword();
  try {
    await sendEmail({
      to: user.email,
      subject: 'Réinitialisation de votre mot de passe Yumco',
      body: `<h1>Bonjour ${user.first_name},</h1><p>Votre nouveau mot de passe temporaire : <strong>${newPassword}</strong></p>`,
    });
    await prisma.user.update({ where: { id: user.id }, data: { hashed_password: await hashPassword(newPassword) } });
  } catch (error) {
    throw badGateway(`Password reset failed because email could not be sent: ${(error as Error).message}`);
  }
  res.json({ message: 'Password reset and email sent successfully' });
});
