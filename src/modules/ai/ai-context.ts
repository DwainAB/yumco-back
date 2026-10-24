/**
 * Contexte du restaurant transmis à l'assistant IA (partie « contexte » de ai_service.py) :
 * carte, style culinaire, saison, localisation, manques de la carte et statistiques.
 */
import { DateTime } from 'luxon';
import { prisma } from '../../db/prisma.js';
import type { Address, Restaurant } from '../../generated/prisma/client.js';
import { getCustomerAnalytics } from '../analytics/customer-analytics.service.js';
import { getOrderAnalytics } from '../analytics/order-analytics.service.js';
import { getPerformanceAnalytics } from '../analytics/performance-analytics.service.js';
import { getRevenueAnalytics } from '../analytics/revenue-analytics.service.js';

/* ---------- Expressions régulières « à la Python » ---------- */

const WORD = String.raw`[\p{L}\p{N}_]`;

/** Traduit le \b de Python (Unicode : « é » est une lettre) en équivalent JavaScript. */
export const pyRegex = (pattern: string, flags = '') =>
  new RegExp(pattern.replaceAll(String.raw`\b`, `(?:(?<=${WORD})(?!${WORD})|(?<!${WORD})(?=${WORD}))`), `${flags}u`);

/* ---------- Données de référence ---------- */

const SOUTHERN_HEMISPHERE_COUNTRIES = new Set([
  'australia',
  'new zealand',
  'argentina',
  'chile',
  'south africa',
  'uruguay',
  'paraguay',
  'bolivia',
  'brazil',
]);

const FRENCH_COASTAL_DEPARTMENTS: Record<string, string> = {
  '06': 'mediterranean',
  '11': 'mediterranean',
  '13': 'mediterranean',
  '17': 'atlantic',
  '22': 'channel_atlantic',
  '29': 'atlantic',
  '2A': 'mediterranean',
  '2B': 'mediterranean',
  '30': 'mediterranean',
  '33': 'atlantic',
  '34': 'mediterranean',
  '35': 'channel_atlantic',
  '40': 'atlantic',
  '44': 'atlantic',
  '50': 'channel',
  '56': 'atlantic',
  '59': 'channel',
  '62': 'channel',
  '64': 'atlantic',
  '66': 'mediterranean',
  '76': 'channel',
  '80': 'channel',
  '83': 'mediterranean',
  '85': 'atlantic',
};

const FRENCH_MOUNTAIN_DEPARTMENTS = new Set([
  '01', '04', '05', '06', '09', '15', '25', '26', '31', '38', '39', '42', '43',
  '48', '63', '64', '65', '66', '67', '68', '73', '74', '88', '90',
]);

const STYLE_KEYWORDS: [string, string[]][] = [
  ['asiatique', ['nouille', 'nouilles', 'nems', 'riz', 'wok', 'sushi', 'maki', 'ramen', 'pho', 'crevette', 'saumon', 'tempura', 'gyoza', 'bo bun', 'bo-bun', 'thaï', 'thai', 'curry', 'yakitori', 'bao', 'dim sum']],
  ['italien', ['pizza', 'pasta', 'pates', 'pâtes', 'risotto', 'gnocchi', 'lasagne', 'carbo', 'carbonara', 'mozza', 'parmesan', 'tiramisu', 'focaccia']],
  ['burger', ['burger', 'cheeseburger', 'bacon', 'fries', 'frites', 'smash', 'tenders', 'nuggets']],
  ['grill', ['grill', 'entrecote', 'entrecôte', 'brochette', 'cote', 'côte', 'barbecue', 'bbq', 'steak', 'poulet roti']],
  ['boulangerie_patisserie', ['croissant', 'pain', 'baguette', 'viennoiserie', 'tarte', 'eclair', 'éclair', 'patisserie', 'pâtisserie', 'flan', 'millefeuille']],
  ['cafe_brunch', ['brunch', 'cafe', 'café', 'latte', 'cappuccino', 'avocado', 'toast', 'pancake', 'granola', 'oeufs', 'œufs']],
  ['mediterraneen', ['mezze', 'houmous', 'hummus', 'falafel', 'shawarma', 'kebab', 'taboule', 'taboulé', 'grillade', 'couscous']],
];

const COUNTRY_ISO_CODES: Record<string, string> = {
  fr: 'FR',
  france: 'FR',
  be: 'BE',
  belgique: 'BE',
  belgium: 'BE',
  es: 'ES',
  espagne: 'ES',
  spain: 'ES',
  it: 'IT',
  italie: 'IT',
  italy: 'IT',
  de: 'DE',
  allemagne: 'DE',
  germany: 'DE',
  pt: 'PT',
  portugal: 'PT',
  uk: 'GB',
  gb: 'GB',
  'royaume-uni': 'GB',
  'united kingdom': 'GB',
  us: 'US',
  usa: 'US',
  'united states': 'US',
  'etats-unis': 'US',
};

/* ---------- Saison et localisation ---------- */

/** Heure locale du restaurant (heure du serveur si le fuseau est inconnu). */
export const localNow = (timezone: string | null) => {
  const zoned = timezone ? DateTime.now().setZone(timezone) : null;
  return zoned?.isValid ? zoned : DateTime.now();
};

const seasonHint = (country: string | null | undefined, now: DateTime) => {
  if (!country) return null;
  const southern = SOUTHERN_HEMISPHERE_COUNTRIES.has(country.trim().toLowerCase());
  const month = now.month;
  if ([12, 1, 2].includes(month)) return southern ? 'summer' : 'winter';
  if ([3, 4, 5].includes(month)) return southern ? 'autumn' : 'spring';
  if ([6, 7, 8].includes(month)) return southern ? 'winter' : 'summer';
  return southern ? 'spring' : 'autumn';
};

const normalizeCountry = (country: string | null | undefined) => (country ? country.trim().toLowerCase() : null);

export const toIsoCountryCode = (country: string | null | undefined) => {
  const normalized = normalizeCountry(country);
  return normalized ? (COUNTRY_ISO_CODES[normalized] ?? null) : null;
};

const departmentCode = (postalCode: string | null | undefined, country: string | null | undefined) => {
  if (!postalCode) return null;
  const compact = postalCode.replaceAll(' ', '').toUpperCase();
  const normalizedCountry = normalizeCountry(country);
  if (normalizedCountry !== 'fr' && normalizedCountry !== 'france') return compact.length >= 3 ? compact.slice(0, 3) : compact;
  if (compact.startsWith('2A') || compact.startsWith('2B')) return compact.slice(0, 2);
  return compact.length >= 2 ? compact.slice(0, 2) : compact;
};

const geographicProfile = (address: Address | null) => {
  if (!address) {
    return {
      country_normalized: null,
      department_code: null,
      is_coastal_likely: false,
      coast_type: null,
      is_mountain_area_likely: false,
      location_profile: 'unknown',
      local_product_biases: [] as string[],
    };
  }
  const country = (address.country ?? '').trim();
  const city = (address.city ?? '').trim();
  const postalCode = (address.postal_code ?? '').trim();
  const normalizedCountry = normalizeCountry(country);
  const department = departmentCode(postalCode, country);

  let coastType: string | null = null;
  let isMountain = false;
  if ((normalizedCountry === 'fr' || normalizedCountry === 'france') && department) {
    coastType = FRENCH_COASTAL_DEPARTMENTS[department] ?? null;
    isMountain = FRENCH_MOUNTAIN_DEPARTMENTS.has(department);
  }
  const isCoastal = coastType !== null;

  const biases: string[] = [];
  let profile = 'inland';
  if (isCoastal) {
    profile = 'coastal';
    biases.push(
      'seafood can be more credible if it already fits the menu style',
      'fresh fish suggestions are more plausible when aligned with the existing offer',
    );
  } else if (isMountain) {
    profile = 'mountain';
    biases.push(
      'comfort food and seasonal hearty dishes can be more credible if they fit the menu',
      'regional sourcing logic may lean toward local meats, cheeses or mountain produce',
    );
  }
  if (city) biases.push(`city context: ${city}`);

  return {
    country_normalized: normalizedCountry || null,
    department_code: department,
    is_coastal_likely: isCoastal,
    coast_type: coastType,
    is_mountain_area_likely: isMountain,
    location_profile: profile,
    local_product_biases: biases,
  };
};

/* ---------- Carte ---------- */

const styleProfile = (categoryNames: string[], productNames: string[]) => {
  const corpus = [...categoryNames, ...productNames].join(' ').toLowerCase();
  const matches = STYLE_KEYWORDS.map(([style, keywords]) => ({ style, score: keywords.filter((keyword) => corpus.includes(keyword)).length }))
    .filter((match) => match.score > 0)
    .sort((a, b) => b.score - a.score);
  return { primary_style: matches[0]?.style ?? 'generaliste', matched_styles: matches.slice(0, 3) };
};

type CatalogCategory = { category_name: string; kind: string; products: { name: string; price: number; description: string | null }[]; product_count: number };

const catalogContext = async (restaurantId: number) => {
  // Tri fait par PostgreSQL pour garder l'ordre alphabétique de la base.
  const rows = await prisma.$queryRaw<{ category_name: string; category_kind: string; product_name: string; product_price: unknown; product_description: string | null }[]>`
    SELECT c.name AS category_name, c.kind AS category_kind, p.name AS product_name, p.price AS product_price, p.description AS product_description
    FROM categories c JOIN products p ON p.category_id = c.id
    WHERE c.restaurant_id = ${restaurantId} AND p.restaurant_id = ${restaurantId} AND p.is_deleted IS false AND p.is_available IS true
    ORDER BY c.name ASC, p.name ASC`;

  const grouped = new Map<string, { kind: string; products: CatalogCategory['products'] }>();
  const productNames: string[] = [];
  const categoryNames: string[] = [];
  for (const row of rows) {
    productNames.push(row.product_name);
    if (!categoryNames.includes(row.category_name)) categoryNames.push(row.category_name);
    if (!grouped.has(row.category_name)) grouped.set(row.category_name, { kind: row.category_kind, products: [] });
    grouped.get(row.category_name)!.products.push({ name: row.product_name, price: Number(row.product_price), description: row.product_description });
  }

  const categories: CatalogCategory[] = [...grouped].map(([name, data]) => ({
    category_name: name,
    kind: data.kind,
    products: data.products,
    product_count: data.products.length,
  }));
  return {
    categories,
    category_count: categories.length,
    product_count: productNames.length,
    all_category_names: categoryNames,
    all_product_names: productNames,
    style_profile: styleProfile(categoryNames, productNames),
  };
};

/** Ce qui manque à la carte (boissons, desserts…) autour des plats principaux. */
const menuGapAnalysis = (catalog: { categories: CatalogCategory[] }) => {
  const kindsPresent = new Set(catalog.categories.filter((c) => c.kind != null).map((c) => String(c.kind).trim().toLowerCase()));
  const productCountsByKind: Record<string, number> = {};
  for (const category of catalog.categories) {
    const kind = String(category.kind || 'other').trim().toLowerCase();
    productCountsByKind[kind] = (productCountsByKind[kind] ?? 0) + (category.product_count || 0);
  }
  const hasMain = kindsPresent.has('main');
  return {
    kinds_present: [...kindsPresent].sort(),
    missing_kinds: ['starter', 'drink', 'side', 'dessert'].filter((kind) => !kindsPresent.has(kind)),
    product_counts_by_kind: productCountsByKind,
    expansion_priorities: hasMain ? ['drink', 'dessert', 'side', 'starter'].filter((kind) => !kindsPresent.has(kind)) : [],
  };
};

export const buildRestaurantContext = async (restaurant: Restaurant & { address: Address | null }) => {
  const now = localNow(restaurant.timezone);
  const { address } = restaurant;
  const catalog = await catalogContext(restaurant.id);
  return {
    restaurant: {
      id: restaurant.id,
      name: restaurant.name,
      timezone: restaurant.timezone,
      street: address?.street ?? null,
      city: address?.city ?? null,
      country: address?.country ?? null,
      postal_code: address?.postal_code ?? null,
      season_hint: seasonHint(address?.country, now),
      current_month: now.setLocale('en').toFormat('LLLL'),
      geography: geographicProfile(address),
    },
    catalog,
    menu_gap_analysis: menuGapAnalysis(catalog),
    analytics: {
      revenue: await getRevenueAnalytics(restaurant.id),
      orders: await getOrderAnalytics(restaurant.id),
      customers: await getCustomerAnalytics(restaurant.id),
      performance: await getPerformanceAnalytics(restaurant.id),
    },
  };
};
