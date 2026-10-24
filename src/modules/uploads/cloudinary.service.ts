/**
 * Envoi d'images vers Cloudinary (cloudinary_service.py).
 */
import { v2 as cloudinary, type UploadApiResponse } from 'cloudinary';
import { env } from '../../config/env.js';

cloudinary.config({
  cloud_name: env.CLOUDINARY_CLOUD_NAME,
  api_key: env.CLOUDINARY_API_KEY,
  api_secret: env.CLOUDINARY_API_SECRET,
  secure: true,
});

/** Envoie l'image dans le dossier Cloudinary `folder` (yumco/products par défaut) et renvoie son URL https. */
export const uploadImage = (file: Buffer, folder = 'yumco/products'): Promise<string> =>
  new Promise((resolve, reject) => {
    const stream = cloudinary.uploader.upload_stream({ folder }, (error, result?: UploadApiResponse) => {
      if (error || !result) reject(error ?? new Error('Cloudinary upload failed'));
      else resolve(result.secure_url);
    });
    stream.end(file);
  });

export const deleteImage = (publicId: string) => cloudinary.uploader.destroy(publicId);
