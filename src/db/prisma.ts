/**
 * Accès à la base (équivalent de app/db/database.py) : un client Prisma partagé par toute l'application.
 */
import { PrismaPg } from '@prisma/adapter-pg';
import { Prisma, PrismaClient } from '../generated/prisma/client.js';
import { env } from '../config/env.js';

/**
 * Tables dont `updated_at` est mis à jour à chaque modification (onupdate=func.now() en SQLAlchemy).
 * À la création, la colonne garde sa valeur par défaut en base (NULL ou now()), comme en Python.
 */
const TOUCHED_ON_UPDATE = new Set<string>([
  'AiConversation',
  'AllYouCanEat',
  'Customer',
  'HubriseConnection',
  'HubriseOrderLog',
  'Menu',
  'MenuCategory',
  'MenuOption',
  'ReviewFollowup',
  'Table',
  'UserDevice',
]);

type WithData = { data?: Record<string, unknown> };

const touch = <T extends WithData>(model: string, args: T): T => {
  if (!TOUCHED_ON_UPDATE.has(model) || !args.data || 'updated_at' in args.data) return args;
  return { ...args, data: { ...args.data, updated_at: new Date() } };
};

const touchUpdatedAt = Prisma.defineExtension({
  name: 'touch-updated-at',
  query: {
    $allModels: {
      update({ model, args, query }) {
        return query(touch(model, args as WithData) as typeof args);
      },
      updateMany({ model, args, query }) {
        return query(touch(model, args as WithData) as typeof args);
      },
    },
  },
});

/**
 * Connexions en UTC : l'adaptateur Prisma lit les colonnes `timestamptz` comme si la session était en UTC
 * (il remplace le décalage par +00:00). Sans cette option, une base réglée sur Europe/Paris décalerait toutes les dates.
 */
const createClient = () =>
  new PrismaClient({ adapter: new PrismaPg({ connectionString: env.DATABASE_URL, options: '-c timezone=UTC' }) }).$extends(touchUpdatedAt);

export const prisma = createClient();

export type Db = typeof prisma;
/** Client utilisable dans une transaction interactive. */
export type Tx = Parameters<Parameters<Db['$transaction']>[0]>[0];
/** Le client principal ou un client de transaction. */
export type DbClient = Db | Tx;

export { Prisma };
