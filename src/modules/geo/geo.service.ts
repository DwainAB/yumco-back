/**
 * Géocodage et distances avec Nominatim (OpenStreetMap) (geo_service.py).
 */
import { pyRound } from '../../lib/python.js';

const NOMINATIM_URL = 'https://nominatim.openstreetmap.org';
const USER_AGENT = 'YumCoRestaurantApp/1.0';

/** Adresse introuvable : la commande est alors acceptée sans calcul de distance. */
export class AddressNotFoundError extends Error {
  constructor(query: string) {
    super(`Adresse introuvable : ${query}`);
    this.name = 'AddressNotFoundError';
  }
}

export interface AddressFields {
  street?: string | null;
  city?: string | null;
  postal_code?: string | null;
  country?: string | null;
}

export interface GeoPoint {
  lat: number;
  lng: number;
  place_name: string;
}

const toRadians = (degrees: number) => (degrees * Math.PI) / 180;

/** Distance en km entre deux points GPS (formule de Haversine). */
export const haversine = (lat1: number, lon1: number, lat2: number, lon2: number): number => {
  const R = 6371;
  const dLat = toRadians(lat2 - lat1);
  const dLon = toRadians(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRadians(lat1)) * Math.cos(toRadians(lat2)) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
};

const COUNTRY_ALIASES: Record<string, string> = {
  fr: 'fr',
  france: 'fr',
  be: 'be',
  belgique: 'be',
  belgium: 'be',
  es: 'es',
  espagne: 'es',
  spain: 'es',
  it: 'it',
  italie: 'it',
  italy: 'it',
  de: 'de',
  allemagne: 'de',
  germany: 'de',
  pt: 'pt',
  portugal: 'pt',
  uk: 'gb',
  gb: 'gb',
  'royaume-uni': 'gb',
  'united kingdom': 'gb',
};

const normalizeCountryCode = (country: string | null | undefined): string | null => {
  if (!country) return null;
  const normalized = country.trim().toLowerCase();
  if (COUNTRY_ALIASES[normalized]) return COUNTRY_ALIASES[normalized];
  if (normalized.length === 2 && /^[a-z]+$/.test(normalized)) return normalized;
  return null;
};

type Params = Record<string, string>;

const queryParams = (q: string): Params => ({ q, format: 'json', limit: '1', addressdetails: '1' });

/** Requêtes à essayer dans l'ordre : adresse structurée, puis texte de plus en plus large. */
const geocodeCandidates = (address: string | AddressFields): Params[] => {
  if (typeof address === 'string') return [queryParams(address)];

  const street = String(address.street ?? '').trim();
  const city = String(address.city ?? '').trim();
  const postalCode = String(address.postal_code ?? '').trim();
  const country = String(address.country ?? '').trim();
  const countryCode = normalizeCountryCode(country);

  const candidates: Params[] = [];
  const structured: Params = { format: 'json', limit: '1', addressdetails: '1' };
  if (street) structured.street = street;
  if (city) structured.city = city;
  if (postalCode) structured.postalcode = postalCode;
  if (country) structured.country = country;
  if (countryCode) structured.countrycodes = countryCode;
  if (street || city || postalCode || country) candidates.push(structured);

  const cityLine = `${postalCode} ${city}`.trim();
  const queries = [
    [street, cityLine, country].filter(Boolean).join(', '),
    [cityLine, country].filter(Boolean).join(', '),
    [city, country].filter(Boolean).join(', '),
  ];
  for (const query of queries) {
    if (!query) continue;
    const params = queryParams(query);
    if (countryCode) params.countrycodes = countryCode;
    candidates.push(params);
  }

  const seen = new Set<string>();
  return candidates.filter((params) => {
    const signature = JSON.stringify(Object.entries(params).sort(([a], [b]) => a.localeCompare(b)));
    if (seen.has(signature)) return false;
    seen.add(signature);
    return true;
  });
};

type NominatimPlace = {
  place_id: number | string;
  lat: string;
  lon: string;
  display_name: string;
  name?: string;
  type?: string;
  address?: Record<string, string>;
};

const nominatimSearch = async (params: Params): Promise<NominatimPlace[]> => {
  const response = await fetch(`${NOMINATIM_URL}/search?${new URLSearchParams(params)}`, {
    headers: { 'User-Agent': USER_AGENT },
    signal: AbortSignal.timeout(10_000),
  });
  return (await response.json()) as NominatimPlace[];
};

const describe = (address: string | AddressFields) =>
  typeof address === 'string' ? address : [address.street, address.postal_code, address.city, address.country].filter(Boolean).join(', ');

/** Géocode une adresse (texte ou champs séparés) → {lat, lng, place_name}. */
export const geocodeAddress = async (address: string | AddressFields): Promise<GeoPoint> => {
  for (const params of geocodeCandidates(address)) {
    const data = await nominatimSearch(params);
    if (data.length) return { lat: Number(data[0].lat), lng: Number(data[0].lon), place_name: data[0].display_name };
  }
  throw new AddressNotFoundError(describe(address));
};

const CITY_TYPES = new Set(['city', 'town', 'village', 'suburb']);

/** Villes et villages dans un rayon autour d'un point (find_cities_within_radius). */
export const findCitiesWithinRadius = async (lat: number, lng: number, radiusKm: number) => {
  const radiusDeg = radiusKm / 111;
  const data = await nominatimSearch({
    q: 'ville',
    format: 'json',
    limit: '20',
    addressdetails: '1',
    viewbox: `${lng - radiusDeg},${lat - radiusDeg},${lng + radiusDeg},${lat + radiusDeg}`,
    bounded: '1',
  });

  const cities: { id: number | string; name: string; postal_code: string; lat: number; lng: number; distance_km: number }[] = [];
  for (const place of data) {
    if (!place.type || !CITY_TYPES.has(place.type)) continue;
    const placeLat = Number(place.lat);
    const placeLng = Number(place.lon);
    const distance = haversine(lat, lng, placeLat, placeLng);
    if (distance > radiusKm) continue;

    const address = place.address ?? {};
    const postalCode = address.postcode ?? '';
    if (!postalCode) continue;

    let name: string;
    if (place.type === 'suburb' && address.city) name = `${address.city} - ${place.name}`;
    else name = address.city || address.town || address.village || place.name || '';

    cities.push({ id: place.place_id, name, postal_code: postalCode, lat: placeLat, lng: placeLng, distance_km: pyRound(distance, 1) });
  }
  return cities.sort((a, b) => a.distance_km - b.distance_km);
};

/** Villes livrables autour du restaurant ; la ville du restaurant est toujours incluse. */
export const getDeliveryCities = async (restaurantAddress: Required<{ [K in keyof AddressFields]: string }>, radiusKm: number) => {
  const fullAddress = `${restaurantAddress.street}, ${restaurantAddress.postal_code} ${restaurantAddress.city}, ${restaurantAddress.country}`;
  const coordinates = await geocodeAddress(fullAddress);
  const cities: Awaited<ReturnType<typeof findCitiesWithinRadius>> = await findCitiesWithinRadius(coordinates.lat, coordinates.lng, radiusKm);

  const restaurantCityPresent = cities.some(
    (city) => city.name.toLowerCase() === restaurantAddress.city.toLowerCase() && city.postal_code === restaurantAddress.postal_code,
  );
  if (!restaurantCityPresent) {
    cities.unshift({
      id: 'restaurant_city',
      name: restaurantAddress.city,
      postal_code: restaurantAddress.postal_code,
      lat: coordinates.lat,
      lng: coordinates.lng,
      distance_km: 0,
    });
  }
  return { coordinates, cities };
};
