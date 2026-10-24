/**
 * Envoi d'une image (routes/upload.py).
 */
import type { Request } from 'express';
import { Router } from 'express';
import multer from 'multer';
import { authenticate } from '../../middleware/auth.js';
import { RequestValidationError } from '../../lib/validation.js';
import { uploadImage } from './cloudinary.service.js';

/** Formulaires multipart : fichiers gardés en mémoire, champs inattendus ignorés comme avec FastAPI. */
export const multipart = multer({ storage: multer.memoryStorage() }).any();

/** Fichier envoyé sous ce nom de champ, s'il y en a un. */
export const uploadedFile = (req: Request, field: string) =>
  (Array.isArray(req.files) ? req.files : []).find((file) => file.fieldname === field && file.size > 0) ?? null;

export const uploadsRouter = Router();

uploadsRouter.post('/upload', authenticate, multipart, async (req, res) => {
  const file = uploadedFile(req, 'file');
  if (!file) throw new RequestValidationError([{ type: 'missing', loc: ['body', 'file'], msg: 'Field required', input: null }]);
  res.json({ url: await uploadImage(file.buffer) });
});
