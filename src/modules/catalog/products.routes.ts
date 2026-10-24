/**
 * Catégories, produits et recommandations (routes/product.py).
 */
import { Router } from 'express';
import { badRequest, notFound } from '../../lib/http-error.js';
import { intParams, validateRequest } from '../../lib/validation.js';
import { restaurantMember } from '../../middleware/auth.js';
import { uploadImage } from '../uploads/cloudinary.service.js';
import { multipart, uploadedFile } from '../uploads/uploads.routes.js';
import { CategoryCreate, CategoryUpdate, ProductCreateForm, ProductUpdateForm, RecommendationRequest } from './catalog.schemas.js';
import { toCategoryResponse, toProductResponse } from './catalog.serializers.js';
import {
  createCategory,
  createProduct,
  deleteCategory,
  deleteProduct,
  getCategories,
  getCategory,
  getProduct,
  getProducts,
  updateCategory,
  updateProduct,
  type ProductData,
} from './products.service.js';
import { getProductRecommendations, UnknownProductsError } from './recommendations.service.js';

export const productsRouter = Router();

const restaurantParams = intParams('restaurant_id');
const categoryParams = intParams('restaurant_id', 'category_id');
const productParams = intParams('restaurant_id', 'product_id');

const findCategory = async (restaurantId: number, categoryId: number) => {
  const category = await getCategory(categoryId);
  if (!category || category.restaurant_id !== restaurantId) throw notFound('Category not found');
  return category;
};

const findProduct = async (restaurantId: number, productId: number) => {
  const product = await getProduct(productId);
  if (!product || product.restaurant_id !== restaurantId) throw notFound('Product not found');
  return product;
};

productsRouter.get('/restaurants/:restaurant_id/categories', async (req, res) => {
  const { params } = validateRequest(req, { params: restaurantParams });
  res.json((await getCategories(params.restaurant_id)).map(toCategoryResponse));
});

productsRouter.post('/restaurants/:restaurant_id/categories', ...restaurantMember, async (req, res) => {
  const { params, body } = validateRequest(req, { params: restaurantParams, body: CategoryCreate });
  res.status(201).json(toCategoryResponse(await createCategory(params.restaurant_id, body.name, body.kind)));
});

productsRouter.put('/restaurants/:restaurant_id/categories/:category_id', ...restaurantMember, async (req, res) => {
  const { params, body } = validateRequest(req, { params: categoryParams, body: CategoryUpdate });
  const category = await findCategory(params.restaurant_id, params.category_id);
  res.json(toCategoryResponse(await updateCategory(category.id, body)));
});

productsRouter.delete('/restaurants/:restaurant_id/categories/:category_id', ...restaurantMember, async (req, res) => {
  const { params } = validateRequest(req, { params: categoryParams });
  const category = await findCategory(params.restaurant_id, params.category_id);
  await deleteCategory(category.id);
  res.status(204).end();
});

productsRouter.get('/restaurants/:restaurant_id/products', async (req, res) => {
  const { params } = validateRequest(req, { params: restaurantParams });
  res.json((await getProducts(params.restaurant_id)).map(toProductResponse));
});

productsRouter.post('/restaurants/:restaurant_id/products/recommendations', async (req, res) => {
  const { params, body } = validateRequest(req, { params: restaurantParams, body: RecommendationRequest });
  try {
    res.json(await getProductRecommendations(params.restaurant_id, body));
  } catch (error) {
    if (error instanceof UnknownProductsError) throw badRequest(error.message);
    throw error;
  }
});

productsRouter.get('/restaurants/:restaurant_id/products/:product_id', async (req, res) => {
  const { params } = validateRequest(req, { params: productParams });
  res.json(toProductResponse(await findProduct(params.restaurant_id, params.product_id)));
});

productsRouter.post('/restaurants/:restaurant_id/products', ...restaurantMember, multipart, async (req, res) => {
  const { params, form } = validateRequest(req, { params: restaurantParams, form: ProductCreateForm });
  const image = uploadedFile(req, 'image');
  const data: ProductData = {
    name: form.name,
    price: form.price,
    description: form.description ?? null,
    category_id: form.category_id ?? null,
    is_available: form.is_available,
    available_online: form.available_online,
    available_onsite: form.available_onsite,
    group: form.group ?? null,
    allergens: form.allergens,
    image_url: image ? await uploadImage(image.buffer) : null,
  };
  res.status(201).json(toProductResponse(await createProduct(params.restaurant_id, data)));
});

productsRouter.put('/restaurants/:restaurant_id/products/:product_id', ...restaurantMember, multipart, async (req, res) => {
  const { params, form } = validateRequest(req, { params: productParams, form: ProductUpdateForm });
  const product = await findProduct(params.restaurant_id, params.product_id);
  // Seuls les champs envoyés sont modifiés.
  const changes: Partial<ProductData> = Object.fromEntries(Object.entries(form).filter(([, value]) => value !== undefined));
  const image = uploadedFile(req, 'image');
  if (image) changes.image_url = await uploadImage(image.buffer);
  res.json(toProductResponse(await updateProduct(product.id, changes)));
});

productsRouter.delete('/restaurants/:restaurant_id/products/:product_id', ...restaurantMember, async (req, res) => {
  const { params } = validateRequest(req, { params: productParams });
  const product = await findProduct(params.restaurant_id, params.product_id);
  await deleteProduct(product.id);
  res.status(204).end();
});
