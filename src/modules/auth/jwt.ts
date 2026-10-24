/**
 * Jetons d'accès (python-jose en Python) : HS256, `sub` = e-mail, `exp` en secondes.
 * Les jetons émis par le backend Python restent valables ici, et inversement.
 */
import { SignJWT, jwtVerify } from 'jose';
import { env } from '../../config/env.js';

const secret = new TextEncoder().encode(env.SECRET_KEY);

export const createAccessToken = (subject: string) =>
  new SignJWT({ sub: subject })
    .setProtectedHeader({ alg: env.ALGORITHM, typ: 'JWT' })
    .setExpirationTime(Math.floor(Date.now() / 1000) + env.ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    .sign(secret);

/** Contenu du jeton, ou null s'il est invalide ou expiré. */
export const decodeAccessToken = async (token: string): Promise<Record<string, unknown> | null> => {
  try {
    const { payload } = await jwtVerify(token, secret, { algorithms: [env.ALGORITHM] });
    return payload as Record<string, unknown>;
  } catch {
    return null;
  }
};
