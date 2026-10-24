/** Livraison : tranches, frais, commandes livrées (tests/integration/test_delivery.py). */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, makeCategory, makeProduct, makeRestaurant, makeUser, prisma } from '../helpers.js';
import { AddressNotFoundError, geocodeAddress } from '../../src/modules/geo/geo.service.js';

let ctx: { restaurantId: number; productId: number };

beforeEach(async () => {
  const user = await makeUser({ email: 'owner_delivery@test.com' });
  const restaurant = await makeRestaurant(user.id);
  const category = await makeCategory(restaurant.id);
  const product = await makeProduct(restaurant.id, category.id, 'Pizza', 20.0);
  await prisma.restaurantConfig.update({ where: { restaurant_id: restaurant.id }, data: { pickup: true, max_delivery_km: 10 } });
  await prisma.deliveryTier.createMany({
    data: [
      { restaurant_id: restaurant.id, min_km: 0, max_km: 3, price: 2.5, min_order_amount: 0 },
      { restaurant_id: restaurant.id, min_km: 3, max_km: 7, price: 4.0, min_order_amount: 15 },
      { restaurant_id: restaurant.id, min_km: 7, max_km: 10, price: 6.0, min_order_amount: 25 },
    ],
  });
  ctx = { restaurantId: restaurant.id, productId: product.id };
});

afterEach(() => {
  vi.mocked(geocodeAddress).mockReset();
  vi.mocked(geocodeAddress).mockResolvedValue({ lat: 48.8566, lng: 2.3522, place_name: 'Paris' });
});

/** Le restaurant puis le client, comme dans resolve_delivery_quote. */
const mockPoints = (customerLat: number) =>
  vi.mocked(geocodeAddress)
    .mockResolvedValueOnce({ lat: 48.8566, lng: 2.3522, place_name: 'restaurant' })
    .mockResolvedValueOnce({ lat: customerLat, lng: 2.3522, place_name: 'client' });

const deliveryOrder = (postalCode: string) =>
  api()
    .post(`/restaurants/${ctx.restaurantId}/orders`)
    .send({
      type: 'delivery',
      items: [{ product_id: ctx.productId, quantity: 1 }],
      customer: { first_name: 'Jane', last_name: 'Doe', phone: '+33600000020' },
      address: { street: '10 Rue Test', city: 'Paris', postal_code: postalCode, country: 'FR' },
    });

describe('delivery', () => {
  it('applies the matching tier (1.5 km → 2.50)', async () => {
    mockPoints(48.8696);
    const res = await deliveryOrder('75002');
    expect(res.status).toBe(201);
    expect(res.body).toMatchObject({ type: 'delivery', delivery_fee: 2.5, items_subtotal: 20, amount_total: 22.5, delivery_distance_km: 1.45 });
  });

  it('a distant address costs more (5 km → 4.00)', async () => {
    mockPoints(48.9015);
    const res = await deliveryOrder('75018');
    expect(res.status).toBe(201);
    expect(res.body.delivery_fee).toBe(4);
  });

  it('quote for an eligible address', async () => {
    mockPoints(48.8696);
    const res = await api()
      .post(`/restaurants/${ctx.restaurantId}/delivery/quote`)
      .send({ address: { street: '10 Rue Test', city: 'Paris', postal_code: '75002', country: 'FR' }, items_subtotal: '20.00' });
    expect(res.status).toBe(200);
    expect(res.body).toMatchObject({ eligible: true, delivery_fee: 2.5, amount_total: 22.5, message: 'Livraison disponible' });
    expect(res.body.applied_tier).toEqual({ min_km: 0, max_km: 3, price: 2.5, min_order_amount: 0 });
  });

  it('quote out of the delivery zone', async () => {
    mockPoints(48.99);
    const res = await api()
      .post(`/restaurants/${ctx.restaurantId}/delivery/quote`)
      .send({ address: { street: '10 Rue Loin', city: 'Versailles', postal_code: '78000', country: 'FR' }, items_subtotal: '20.00' });
    expect(res.status).toBe(200);
    expect(res.body).toMatchObject({ eligible: false, message: 'Adresse hors zone de livraison' });
  });

  it('quote below the minimum order of the tier', async () => {
    mockPoints(48.9015);
    const res = await api()
      .post(`/restaurants/${ctx.restaurantId}/delivery/quote`)
      .send({ address: { street: '10 Rue Test', city: 'Paris', postal_code: '75018', country: 'FR' }, items_subtotal: '10.00' });
    expect(res.body).toMatchObject({
      eligible: false,
      shortfall_amount: 5,
      next_min_order_amount: 15,
      message: 'Livraison disponible a partir de 15.00 EUR pour votre zone',
    });
  });

  it('accepts the order when the address cannot be geocoded', async () => {
    vi.mocked(geocodeAddress).mockRejectedValue(new AddressNotFoundError('adresse libre'));
    const res = await api()
      .post(`/restaurants/${ctx.restaurantId}/orders`)
      .send({
        type: 'delivery',
        items: [{ product_id: ctx.productId, quantity: 1 }],
        customer: { first_name: 'Jane', last_name: 'Doe', phone: '+33600000022' },
        address: { street: 'Adresse tapée librement', city: 'Mitry-Mory', postal_code: '77290', country: 'France' },
      });
    expect(res.status).toBe(201);
    expect(res.body).toMatchObject({ type: 'delivery', delivery_fee: 0, delivery_distance_km: null, amount_total: 20 });
  });
});

describe('geocoding', () => {
  it('falls back to the next queries when the structured one finds nothing', async () => {
    const { geocodeAddress: realGeocode } = await vi.importActual<typeof import('../../src/modules/geo/geo.service.js')>('../../src/modules/geo/geo.service.js');
    const responses = [[], [{ lat: '48.9584', lon: '2.6044', display_name: 'Avenue La Martine, 77290 Mitry-Mory, France' }]];
    const fetchMock = vi.fn(async (_url: string | URL) => new Response(JSON.stringify(responses.shift())));
    vi.stubGlobal('fetch', fetchMock);
    try {
      const result = await realGeocode({ street: 'Avenue la martine', city: 'Mitry-Mory', postal_code: '77290', country: 'France' });
      expect(result.lat).toBeCloseTo(48.9584);
      expect(result.lng).toBeCloseTo(2.6044);
      expect(result.place_name).toContain('Mitry-Mory');
      const firstUrl = new URL(String(fetchMock.mock.calls[0][0]));
      expect(firstUrl.searchParams.get('postalcode')).toBe('77290');
      expect(firstUrl.searchParams.get('countrycodes')).toBe('fr');
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
