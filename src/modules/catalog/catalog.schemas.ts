/**
 * Validation des entrées du catalogue (schemas/category.py, product.py, menu.py, all_you_can_eat.py, recommendation.py).
 */
import { Prisma } from '../../generated/prisma/client.js';
import { ge, le, py, valueError, z } from '../../lib/validation.js';

/* ---------- Catégories ---------- */

const CATEGORY_KINDS = ['main', 'starter', 'drink', 'side', 'dessert', 'other'];
const SORTED_KINDS = [...CATEGORY_KINDS].sort().join(', ');

const categoryKind = () =>
  py.str().transform((value, ctx) => {
    const normalized = value.trim().toLowerCase();
    if (!CATEGORY_KINDS.includes(normalized)) {
      valueError(ctx, `kind must be one of: ${SORTED_KINDS}`, [], value);
      return z.NEVER;
    }
    return normalized;
  });

export const CategoryCreate = z.object({ name: py.str(), kind: categoryKind().default('other') });
export const CategoryUpdate = z.object({ name: py.str().nullable().optional(), kind: categoryKind().nullable().optional() });

/* ---------- Produits (formulaires multipart) ---------- */

/** Liste répétable d'un formulaire (allergens=a&allergens=b). */
const formList = () => z.preprocess((value) => (Array.isArray(value) ? value : [value]), z.array(py.str()));

export const ProductCreateForm = z.object({
  name: py.str(),
  price: py.decimal(),
  description: py.str().optional(),
  category_id: py.int().optional(),
  is_available: py.bool().default(true),
  available_online: py.bool().default(true),
  available_onsite: py.bool().default(true),
  group: py.str().optional(),
  allergens: formList().default([]),
});
export type ProductCreateForm = z.output<typeof ProductCreateForm>;

export const ProductUpdateForm = z.object({
  name: py.str().optional(),
  price: py.decimal().optional(),
  description: py.str().optional(),
  category_id: py.int().optional(),
  is_available: py.bool().optional(),
  available_online: py.bool().optional(),
  available_onsite: py.bool().optional(),
  group: py.str().optional(),
  allergens: formList().optional(),
});
export type ProductUpdateForm = z.output<typeof ProductUpdateForm>;

/* ---------- Menus ---------- */

const zero = () => new Prisma.Decimal(0);

export const MenuOptionCreate = z.object({
  name: py.str().nullable().optional(),
  additional_price: py.decimal().default(zero),
  display_order: py.int().default(0),
  product_id: py.int().nullable().optional(),
});
export type MenuOptionCreate = z.output<typeof MenuOptionCreate>;

export const MenuCategoryCreate = z.object({
  name: py.str(),
  max_options: py.int().default(1),
  is_required: py.bool().default(true),
  display_order: py.int().default(0),
  options: z.array(MenuOptionCreate).default([]),
});
export type MenuCategoryCreate = z.output<typeof MenuCategoryCreate>;

export const MenuCreate = z.object({
  name: py.str(),
  price: py.decimal(),
  is_available: py.bool().default(true),
  available_online: py.bool().default(true),
  available_onsite: py.bool().default(true),
  image_url: py.str().nullable().optional(),
  categories: z.array(MenuCategoryCreate).default([]),
});
export type MenuCreate = z.output<typeof MenuCreate>;

export const MenuUpdate = z.object({
  name: py.str().nullable().optional(),
  price: py.decimal().nullable().optional(),
  is_available: py.bool().nullable().optional(),
  available_online: py.bool().nullable().optional(),
  available_onsite: py.bool().nullable().optional(),
  image_url: py.str().nullable().optional(),
  categories: z.array(MenuCategoryCreate).nullable().optional(),
});
export type MenuUpdate = z.output<typeof MenuUpdate>;

/* ---------- Buffet à volonté ---------- */

export const AllYouCanEatCreate = z.object({ name: py.str(), price: py.decimal() });
export const AllYouCanEatUpdate = z.object({ name: py.str().nullable().optional(), price: py.decimal().nullable().optional() });

/* ---------- Recommandations ---------- */

export const RecommendationRequest = z.object({
  items: z.array(z.object({ product_id: py.int(), quantity: py.int().superRefine(ge(1)).default(1) })),
  limit: py.int().superRefine(ge(1)).superRefine(le(10)).default(3),
});
export type RecommendationRequest = z.output<typeof RecommendationRequest>;
