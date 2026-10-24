/**
 * Menus (routes/menu.py).
 */
import { Router } from 'express';
import { notFound } from '../../lib/http-error.js';
import { intParams, validateRequest } from '../../lib/validation.js';
import { restaurantMember } from '../../middleware/auth.js';
import { MenuCreate, MenuUpdate } from './catalog.schemas.js';
import { toMenuResponse } from './catalog.serializers.js';
import { createMenu, deleteMenu, getMenu, getMenus, updateMenu } from './menus.service.js';

export const menusRouter = Router();

const restaurantParams = intParams('restaurant_id');
const menuParams = intParams('restaurant_id', 'menu_id');

const findMenu = async (restaurantId: number, menuId: number) => {
  const menu = await getMenu(menuId);
  if (!menu || menu.restaurant_id !== restaurantId) throw notFound('Menu not found');
  return menu;
};

menusRouter.get('/restaurants/:restaurant_id/menus', async (req, res) => {
  const { params } = validateRequest(req, { params: restaurantParams });
  res.json((await getMenus(params.restaurant_id)).map(toMenuResponse));
});

menusRouter.get('/restaurants/:restaurant_id/menus/:menu_id', async (req, res) => {
  const { params } = validateRequest(req, { params: menuParams });
  res.json(toMenuResponse(await findMenu(params.restaurant_id, params.menu_id)));
});

menusRouter.post('/restaurants/:restaurant_id/menus', ...restaurantMember, async (req, res) => {
  const { params, body } = validateRequest(req, { params: restaurantParams, body: MenuCreate });
  res.status(201).json(toMenuResponse(await createMenu(params.restaurant_id, body)));
});

menusRouter.put('/restaurants/:restaurant_id/menus/:menu_id', ...restaurantMember, async (req, res) => {
  const { params, body } = validateRequest(req, { params: menuParams, body: MenuUpdate });
  const menu = await findMenu(params.restaurant_id, params.menu_id);
  res.json(toMenuResponse(await updateMenu(menu.id, body)));
});

menusRouter.delete('/restaurants/:restaurant_id/menus/:menu_id', ...restaurantMember, async (req, res) => {
  const { params } = validateRequest(req, { params: menuParams });
  const menu = await findMenu(params.restaurant_id, params.menu_id);
  await deleteMenu(menu.id);
  res.status(204).end();
});
