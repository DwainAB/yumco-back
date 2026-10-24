/**
 * Produits et catégories (product_service.py).
 */
import { prisma } from '../../db/prisma.js';
import type { Prisma } from '../../generated/prisma/client.js';
import { productInclude } from './catalog.serializers.js';

export const getProducts = (restaurantId: number) =>
  prisma.product.findMany({ where: { restaurant_id: restaurantId, is_deleted: false }, include: productInclude, orderBy: { id: 'asc' } });

export const getProduct = (productId: number) =>
  prisma.product.findFirst({ where: { id: productId, is_deleted: false }, include: productInclude });

export interface ProductData {
  name: string;
  price: Prisma.Decimal;
  description: string | null;
  image_url: string | null;
  category_id: number | null;
  is_available: boolean;
  available_online: boolean;
  available_onsite: boolean;
  group: string | null;
  allergens: string[];
}

export const createProduct = (restaurantId: number, data: ProductData) =>
  prisma.product.create({ data: { ...data, restaurant_id: restaurantId, is_deleted: false }, include: productInclude });

export const updateProduct = (productId: number, changes: Partial<ProductData>) =>
  prisma.product.update({ where: { id: productId }, data: changes, include: productInclude });

/** Suppression « douce » : le produit reste en base pour l'historique des commandes. */
export const deleteProduct = (productId: number) => prisma.product.update({ where: { id: productId }, data: { is_deleted: true } });

export const getCategories = (restaurantId: number) =>
  prisma.category.findMany({ where: { restaurant_id: restaurantId }, orderBy: { id: 'asc' } });

export const getCategory = (categoryId: number) => prisma.category.findFirst({ where: { id: categoryId } });

export const createCategory = (restaurantId: number, name: string, kind: string) =>
  prisma.category.create({ data: { name, kind, restaurant_id: restaurantId } });

export const updateCategory = (categoryId: number, changes: { name?: string | null; kind?: string | null }) =>
  prisma.category.update({ where: { id: categoryId }, data: changes as Prisma.CategoryUpdateInput });

export const deleteCategory = (categoryId: number) => prisma.category.delete({ where: { id: categoryId } });
