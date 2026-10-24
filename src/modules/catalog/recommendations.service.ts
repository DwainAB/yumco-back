/**
 * Suggestions de produits à ajouter au panier (recommendation_service.py) : catégories manquantes,
 * produits souvent achetés ensemble et produits populaires.
 */
import { prisma } from '../../db/prisma.js';
import { pyRound } from '../../lib/python.js';
import { decimalString } from '../../lib/serialize.js';
import type { RecommendationRequest } from './catalog.schemas.js';

type Reason =
  | 'missing_starter'
  | 'missing_drink'
  | 'missing_side'
  | 'missing_dessert'
  | 'frequently_bought_together'
  | 'popular_in_restaurant';

const REASON_CONTENT: Record<Reason, { title: string; message: string }> = {
  missing_starter: { title: 'Ajoute une entree', message: 'Cette entree complete bien les plats deja ajoutes au panier.' },
  missing_drink: { title: 'Ajoute une boisson', message: 'Une boisson est souvent ajoutee avec ce type de commande.' },
  missing_side: { title: 'Ajoute un accompagnement', message: 'Un accompagnement peut completer ce plat principal.' },
  missing_dessert: { title: 'Ajoute un dessert', message: 'Un dessert est une bonne suggestion pour completer la commande.' },
  frequently_bought_together: {
    title: 'Souvent commande avec ce panier',
    message: 'Ce produit est souvent achete avec les articles deja selectionnes.',
  },
  popular_in_restaurant: { title: 'Produit populaire', message: 'Ce produit est souvent choisi par les clients du restaurant.' },
};

const MAX_STARTER_SUGGESTION_MAIN_COUNT = 2;
const MAX_DESSERT_SUGGESTION_MAIN_COUNT = 3;
const MAX_TOTAL_ITEMS_FOR_EXTRA_SUGGESTIONS = 6;

type CategoryReason = [kind: string, reason: Reason, weight: number];

const missingCategoryReasons = (presentKinds: Set<string>): CategoryReason[] => {
  if (!presentKinds.has('main')) return [];
  const reasons: CategoryReason[] = [];
  if (!presentKinds.has('starter')) reasons.push(['starter', 'missing_starter', 0.25]);
  if (!presentKinds.has('drink')) reasons.push(['drink', 'missing_drink', 0.45]);
  if (!presentKinds.has('side')) reasons.push(['side', 'missing_side', 0.3]);
  if (!presentKinds.has('dessert')) reasons.push(['dessert', 'missing_dessert', 0.2]);
  return reasons;
};

const quantityBasedReasons = (quantities: Map<string, number>): CategoryReason[] => {
  const mainCount = quantities.get('main') ?? 0;
  if (mainCount <= 0) return [];
  const reasons: CategoryReason[] = [];
  if ((quantities.get('starter') ?? 0) === 0) reasons.push(['starter', 'missing_starter', 0.25]);
  const drinkCount = quantities.get('drink') ?? 0;
  if (drinkCount < mainCount) reasons.push(['drink', 'missing_drink', pyRound(0.45 * ((mainCount - drinkCount) / mainCount), 4)]);
  const sideCount = quantities.get('side') ?? 0;
  if (sideCount < mainCount) reasons.push(['side', 'missing_side', pyRound(0.3 * ((mainCount - sideCount) / mainCount), 4)]);
  if ((quantities.get('dessert') ?? 0) === 0) reasons.push(['dessert', 'missing_dessert', 0.2]);
  return reasons;
};

/** Pas d'entrée ni de dessert sur une grosse commande, pas de boisson ou d'accompagnement en trop. */
const shouldExcludeCandidate = (kind: string | null, quantities: Map<string, number>, totalItems: number) => {
  const mainCount = quantities.get('main') ?? 0;
  if (kind === 'starter') {
    if ((quantities.get('starter') ?? 0) >= 1 || mainCount > MAX_STARTER_SUGGESTION_MAIN_COUNT || totalItems >= MAX_TOTAL_ITEMS_FOR_EXTRA_SUGGESTIONS) return true;
  }
  if (kind === 'dessert') {
    if ((quantities.get('dessert') ?? 0) >= 1 || mainCount > MAX_DESSERT_SUGGESTION_MAIN_COUNT || totalItems >= MAX_TOTAL_ITEMS_FOR_EXTRA_SUGGESTIONS) return true;
  }
  if (kind === 'side' && (quantities.get('side') ?? 0) >= mainCount && mainCount > 0) return true;
  if (kind === 'drink' && (quantities.get('drink') ?? 0) >= mainCount && mainCount > 0) return true;
  return false;
};

/** Lignes principales (hors options de menu) des commandes non annulées du restaurant. */
const rootItemsWhere = (restaurantId: number, excludeCancelled: boolean) => ({
  parent_order_item_id: null,
  product_id: { not: null },
  order: { restaurant_id: restaurantId, ...(excludeCancelled ? { status: { not: 'cancelled' } } : {}) },
});

const popularityCounts = async (restaurantId: number) => {
  const rows = await prisma.orderItem.groupBy({
    by: ['product_id'],
    where: rootItemsWhere(restaurantId, true),
    _count: { id: true },
  });
  return new Map(rows.filter((row) => row.product_id !== null).map((row) => [row.product_id as number, row._count.id]));
};

/** Pour chaque produit du panier : nombre de commandes (distinctes) qui le contiennent. */
const productOrderCounts = async (restaurantId: number, productIds: number[]) => {
  const rows = await prisma.orderItem.findMany({
    where: { ...rootItemsWhere(restaurantId, true), product_id: { in: productIds } },
    select: { product_id: true, order_id: true },
    distinct: ['product_id', 'order_id'],
  });
  const counts = new Map<number, number>();
  for (const row of rows) counts.set(row.product_id!, (counts.get(row.product_id!) ?? 0) + 1);
  return counts;
};

/** Force d'achat conjoint de chaque produit candidat avec les produits du panier. */
const copurchaseStrengths = async (restaurantId: number, basketIds: number[]) => {
  if (!basketIds.length) return new Map<number, number>();
  const basketOrderCounts = await productOrderCounts(restaurantId, basketIds);

  const basketRows = await prisma.orderItem.findMany({
    where: { ...rootItemsWhere(restaurantId, false), product_id: { in: basketIds } },
    select: { product_id: true, order_id: true },
  });
  const basketOrders = new Map<number, Set<number>>();
  for (const row of basketRows) {
    if (!basketOrders.has(row.product_id!)) basketOrders.set(row.product_id!, new Set());
    basketOrders.get(row.product_id!)!.add(row.order_id);
  }
  const matchingOrderIds = new Set([...basketOrders.values()].flatMap((ids) => [...ids]));
  if (!matchingOrderIds.size) return new Map<number, number>();

  const candidateRows = await prisma.orderItem.findMany({
    where: { ...rootItemsWhere(restaurantId, false), order_id: { in: [...matchingOrderIds] }, product_id: { notIn: basketIds, not: null } },
    select: { order_id: true, product_id: true },
  });
  const orderCandidates = new Map<number, Set<number>>();
  for (const row of candidateRows) {
    if (!orderCandidates.has(row.order_id)) orderCandidates.set(row.order_id, new Set());
    orderCandidates.get(row.order_id)!.add(row.product_id!);
  }

  const scores = new Map<number, number>();
  for (const [basketProductId, orderIds] of basketOrders) {
    const basketOrderCount = basketOrderCounts.get(basketProductId) ?? 0;
    if (basketOrderCount === 0) continue;
    const occurrences = new Map<number, number>();
    for (const orderId of orderIds) {
      for (const candidateId of orderCandidates.get(orderId) ?? []) occurrences.set(candidateId, (occurrences.get(candidateId) ?? 0) + 1);
    }
    for (const [candidateId, count] of occurrences) scores.set(candidateId, (scores.get(candidateId) ?? 0) + count / basketOrderCount);
  }
  return new Map([...scores].map(([candidateId, score]) => [candidateId, score / basketIds.length]));
};

export class UnknownProductsError extends Error {}

export const getProductRecommendations = async (restaurantId: number, payload: RecommendationRequest) => {
  const basketQuantities = new Map<number, number>();
  for (const item of payload.items) basketQuantities.set(item.product_id, (basketQuantities.get(item.product_id) ?? 0) + item.quantity);
  const basketIds = [...basketQuantities.keys()];

  const basketProducts = await prisma.product.findMany({
    where: { restaurant_id: restaurantId, is_deleted: false, id: { in: basketIds } },
    select: { id: true, category: { select: { kind: true } } },
  });
  if (basketProducts.length !== basketIds.length) {
    const existing = new Set(basketProducts.map((product) => product.id));
    const missing = basketIds.filter((id) => !existing.has(id));
    throw new UnknownProductsError(`Unknown product ids for restaurant ${restaurantId}: [${missing.join(', ')}]`);
  }

  const presentKinds = new Set<string>();
  const quantities = new Map<string, number>();
  for (const product of basketProducts) {
    const kind = product.category?.kind;
    if (kind == null) continue;
    presentKinds.add(kind);
    quantities.set(kind, (quantities.get(kind) ?? 0) + (basketQuantities.get(product.id) ?? 0));
  }
  const totalItems = [...basketQuantities.values()].reduce((sum, quantity) => sum + quantity, 0);

  let categoryReasons = quantityBasedReasons(quantities);
  if (!categoryReasons.length) categoryReasons = missingCategoryReasons(presentKinds);

  const candidates = await prisma.product.findMany({
    where: { restaurant_id: restaurantId, is_deleted: false, is_available: true, available_online: true, id: { notIn: basketIds } },
    select: { id: true, name: true, price: true, image_url: true, category_id: true, category: { select: { name: true, kind: true } } },
    orderBy: { id: 'asc' },
  });

  const popularity = await popularityCounts(restaurantId);
  const copurchase = await copurchaseStrengths(restaurantId, basketIds);
  const maxPopularity = Math.max(0, ...popularity.values());
  const maxCopurchase = Math.max(0, ...copurchase.values());

  const scored = [];
  for (const candidate of candidates) {
    const kind = candidate.category?.kind ?? null;
    if (shouldExcludeCandidate(kind, quantities, totalItems)) continue;

    let score = 0;
    const reasons: [Reason, number][] = [];
    for (const [missingKind, reason, weight] of categoryReasons) {
      if (kind === missingKind) {
        score += weight;
        reasons.push([reason, weight]);
      }
    }
    const strength = copurchase.get(candidate.id) ?? 0;
    if (maxCopurchase && strength) {
      const weight = 0.35 * (strength / maxCopurchase);
      score += weight;
      reasons.push(['frequently_bought_together', weight]);
    }
    const popularityCount = popularity.get(candidate.id) ?? 0;
    if (maxPopularity && popularityCount) {
      const weight = 0.2 * (popularityCount / maxPopularity);
      score += weight;
      reasons.push(['popular_in_restaurant', weight]);
    }
    if (score <= 0) continue;

    // max() de Python : en cas d'égalité, la première raison l'emporte.
    const primary = reasons.reduce((best, current) => (current[1] > best[1] ? current : best))[0];
    scored.push({
      product_id: candidate.id,
      name: candidate.name,
      price: decimalString(candidate.price),
      image_url: candidate.image_url,
      category_id: candidate.category_id,
      category_name: candidate.category?.name ?? null,
      score: pyRound(score, 4),
      reason: primary,
      title: REASON_CONTENT[primary].title,
      message: REASON_CONTENT[primary].message,
    });
  }

  scored.sort((a, b) => b.score - a.score || (a.name.toLowerCase() < b.name.toLowerCase() ? -1 : a.name.toLowerCase() > b.name.toLowerCase() ? 1 : 0));
  return { recommendations: scored.slice(0, payload.limit) };
};
