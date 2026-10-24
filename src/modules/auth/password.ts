/**
 * Mots de passe (passlib + bcrypt en Python) : mêmes hachages `$2b$`, coût 12.
 */
import { randomInt } from 'node:crypto';
import bcrypt from 'bcryptjs';

const BCRYPT_ROUNDS = 12;
const PASSWORD_CHARACTERS = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%';

export const hashPassword = (password: string) => bcrypt.hash(password, BCRYPT_ROUNDS);

export const verifyPassword = async (password: string, hashed: string) => {
  try {
    return await bcrypt.compare(password, hashed);
  } catch {
    return false;
  }
};

/** Mot de passe temporaire envoyé par e-mail (generate_password). */
export const generatePassword = (length = 12) =>
  Array.from({ length }, () => PASSWORD_CHARACTERS[randomInt(PASSWORD_CHARACTERS.length)]).join('');
