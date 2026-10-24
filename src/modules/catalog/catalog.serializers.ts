/**
 * Réponses du catalogue (CategoryResponse, ProductResponse, MenuResponse, AllYouCanEatResponse).
 */
import type { AllYouCanEat, Category, Prisma } from '../../generated/prisma/client.js';
import { datetime, decimalString } from '../../lib/serialize.js';

export const toCategoryResponse = (category: Category) => ({
  id: category.id,
  name: category.name,
  kind: category.kind,
  restaurant_id: category.restaurant_id,
  created_at: datetime(category.created_at!),
});

export const productInclude = { category: true } as const satisfies Prisma.ProductInclude;
export type ProductWithCategory = Prisma.ProductGetPayload<{ include: typeof productInclude }>;

export const toProductResponse = (product: ProductWithCategory) => ({
  id: product.id,
  name: product.name,
  description: product.description,
  price: decimalString(product.price),
  image_url: product.image_url,
  category: product.category ? { id: product.category.id, name: product.category.name } : null,
  restaurant_id: product.restaurant_id,
  is_available: product.is_available ?? true,
  available_online: product.available_online ?? true,
  available_onsite: product.available_onsite ?? true,
  group: product.group,
  allergens: (product.allergens ?? []) as string[],
  created_at: datetime(product.created_at!),
});

export const menuInclude = {
  categories: { orderBy: { id: 'asc' }, include: { options: { orderBy: { id: 'asc' } } } },
} as const satisfies Prisma.MenuInclude;
export type MenuWithCategories = Prisma.MenuGetPayload<{ include: typeof menuInclude }>;

export const toMenuResponse = (menu: MenuWithCategories) => ({
  id: menu.id,
  restaurant_id: menu.restaurant_id,
  name: menu.name,
  price: decimalString(menu.price),
  is_available: menu.is_available ?? true,
  available_online: menu.available_online ?? true,
  available_onsite: menu.available_onsite ?? true,
  image_url: menu.image_url,
  created_at: datetime(menu.created_at!),
  categories: menu.categories.map((category) => ({
    id: category.id,
    name: category.name,
    max_options: category.max_options ?? 1,
    is_required: category.is_required ?? true,
    display_order: category.display_order ?? 0,
    options: category.options.map((option) => ({
      id: option.id,
      name: option.name,
      additional_price: decimalString(option.additional_price ?? 0),
      display_order: option.display_order ?? 0,
      product_id: option.product_id,
    })),
  })),
});

export const toAllYouCanEatResponse = (offer: AllYouCanEat) => ({
  id: offer.id,
  restaurant_id: offer.restaurant_id,
  name: offer.name,
  price: decimalString(offer.price),
  created_at: datetime(offer.created_at!),
});
