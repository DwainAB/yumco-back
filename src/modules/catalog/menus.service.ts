/**
 * Menus, leurs catégories et leurs options (menu_service.py).
 */
import { prisma, type Tx } from '../../db/prisma.js';
import type { Prisma } from '../../generated/prisma/client.js';
import { badRequest } from '../../lib/http-error.js';
import { menuInclude } from './catalog.serializers.js';
import type { MenuCategoryCreate, MenuCreate, MenuOptionCreate, MenuUpdate } from './catalog.schemas.js';

/** Nom de l'option : celui fourni, sinon celui du produit lié. */
const resolveOptionName = async (tx: Tx, option: MenuOptionCreate) => {
  if (option.name) return option.name;
  if (option.product_id) {
    const product = await tx.product.findFirst({ where: { id: option.product_id } });
    if (product) return product.name;
  }
  throw badRequest('Option must have a name or a valid product_id');
};

const createCategories = async (tx: Tx, menuId: number, categories: MenuCategoryCreate[]) => {
  for (const category of categories) {
    const created = await tx.menuCategory.create({
      data: {
        menu_id: menuId,
        name: category.name,
        max_options: category.max_options,
        is_required: category.is_required,
        display_order: category.display_order,
      },
    });
    for (const option of category.options) {
      await tx.menuOption.create({
        data: {
          category_id: created.id,
          name: await resolveOptionName(tx, option),
          additional_price: option.additional_price,
          display_order: option.display_order,
          product_id: option.product_id ?? null,
        },
      });
    }
  }
};

export const getMenus = (restaurantId: number) =>
  prisma.menu.findMany({ where: { restaurant_id: restaurantId }, include: menuInclude, orderBy: { id: 'asc' } });

export const getMenu = (menuId: number) => prisma.menu.findFirst({ where: { id: menuId }, include: menuInclude });

/** Création en une transaction (en Python, une option invalide laissait un menu à moitié créé). */
export const createMenu = async (restaurantId: number, data: MenuCreate) => {
  const menuId = await prisma.$transaction(async (tx) => {
    const menu = await tx.menu.create({
      data: {
        restaurant_id: restaurantId,
        name: data.name,
        price: data.price,
        is_available: data.is_available,
        available_online: data.available_online,
        available_onsite: data.available_onsite,
        image_url: data.image_url ?? null,
      },
    });
    await createCategories(tx, menu.id, data.categories);
    return menu.id;
  });
  return prisma.menu.findUniqueOrThrow({ where: { id: menuId }, include: menuInclude });
};

/** Les catégories envoyées remplacent toutes les catégories existantes. */
export const updateMenu = async (menuId: number, data: MenuUpdate) => {
  await prisma.$transaction(async (tx) => {
    const { categories, ...fields } = data;
    const changes = Object.fromEntries(Object.entries(fields).filter(([, value]) => value !== undefined));
    if (Object.keys(changes).length) await tx.menu.update({ where: { id: menuId }, data: changes as Prisma.MenuUpdateInput });
    if (categories != null) {
      await tx.menuCategory.deleteMany({ where: { menu_id: menuId } });
      await createCategories(tx, menuId, categories);
    }
  });
  return prisma.menu.findUniqueOrThrow({ where: { id: menuId }, include: menuInclude });
};

export const deleteMenu = (menuId: number) => prisma.menu.delete({ where: { id: menuId } });
