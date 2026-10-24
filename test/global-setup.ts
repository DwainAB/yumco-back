/**
 * Prépare la base de test : recréée à chaque lancement à partir du schéma Prisma (équivalent du
 * Base.metadata.create_all de tests/integration/conftest.py).
 */
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import pg from 'pg';

const readTestEnv = () => {
  if (!existsSync('.env.test')) throw new Error('Fichier .env.test manquant (voir README)');
  const entries = readFileSync('.env.test', 'utf8')
    .split('\n')
    .filter((line) => line.trim() && !line.trim().startsWith('#') && line.includes('='))
    .map((line) => [line.slice(0, line.indexOf('=')).trim(), line.slice(line.indexOf('=') + 1).trim()]);
  return Object.fromEntries(entries) as Record<string, string>;
};

export default async function setup() {
  const databaseUrl = readTestEnv().DATABASE_URL;
  const url = new URL(databaseUrl);
  const database = url.pathname.slice(1);
  if (!database.includes('test')) throw new Error(`Refus : la base de test doit contenir « test » dans son nom (${database})`);

  const admin = new pg.Client({ connectionString: databaseUrl.replace(/\/[^/]+$/, '/postgres') });
  await admin.connect();
  await admin.query(`DROP DATABASE IF EXISTS "${database}" WITH (FORCE)`);
  await admin.query(`CREATE DATABASE "${database}"`);
  await admin.end();

  const schemaSql = execFileSync('npx', ['prisma', 'migrate', 'diff', '--from-empty', '--to-schema', 'prisma/schema.prisma', '--script'], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'ignore'],
  });
  const client = new pg.Client({ connectionString: databaseUrl });
  await client.connect();
  await client.query(schemaSql);
  await client.end();
}
