/**
 * Configuration (équivalent de app/core/config.py) : mêmes variables, mêmes valeurs par défaut,
 * pour que le fichier .env du backend Python fonctionne tel quel.
 */
import { existsSync } from 'node:fs';
import * as z from 'zod';

if (process.env.NODE_ENV !== 'test' && existsSync('.env')) process.loadEnvFile('.env');

const DEFAULT_CORS_ALLOWED_ORIGINS = [
  'https://dashboard.yumco.fr',
  'https://platform.yumco.fr',
  'http://localhost:3000',
  'http://localhost:5173',
  'http://127.0.0.1:3000',
];

/** Variable facultative : une valeur vide équivaut à une variable absente. */
const optional = () =>
  z
    .string()
    .optional()
    .transform((value) => (value ? value : null));

const integer = () => z.coerce.number().int();

/** Liste JSON (`["a","b"]`) ou séparée par des virgules, comme parse_cors_allowed_origins. */
const originList = z
  .string()
  .optional()
  .transform((value, ctx) => {
    if (value === undefined) return DEFAULT_CORS_ALLOWED_ORIGINS;
    const stripped = value.trim();
    if (!stripped) return [];
    if (stripped.startsWith('[')) {
      try {
        return z.array(z.string()).parse(JSON.parse(stripped));
      } catch {
        ctx.addIssue({ code: 'custom', message: 'CORS_ALLOWED_ORIGINS must be a JSON list of strings' });
        return z.NEVER;
      }
    }
    return stripped
      .split(',')
      .map((origin) => origin.trim())
      .filter(Boolean);
  });

const EnvSchema = z.object({
  DATABASE_URL: z.string(),
  SECRET_KEY: z.string(),
  ALGORITHM: z.enum(['HS256', 'HS384', 'HS512']),
  ACCESS_TOKEN_EXPIRE_MINUTES: integer(),
  REFRESH_TOKEN_EXPIRE_DAYS: integer(),
  MAIL_USERNAME: z.string(),
  MAIL_PASSWORD: z.string(),
  MAIL_FROM: z.string(),
  MAIL_PORT: integer(),
  MAIL_SERVER: z.string(),
  CLOUDINARY_CLOUD_NAME: z.string(),
  CLOUDINARY_API_KEY: z.string(),
  CLOUDINARY_API_SECRET: z.string(),
  OPENAI_API_KEY: optional(),
  OPENAI_MODEL: z.string().default('gpt-5.4-mini'),
  OPENAI_WEB_SEARCH_MODEL: z.string().default('gpt-4.1-mini'),
  APP_BASE_URL: optional(),
  FRONTEND_BASE_URL: optional(),
  CORS_ALLOWED_ORIGINS: originList,
  STRIPE_SECRET_KEY: optional(),
  STRIPE_WEBHOOK_SECRET: optional(),
  STRIPE_PRICE_STARTER_MONTHLY: optional(),
  STRIPE_PRICE_STARTER_YEARLY: optional(),
  STRIPE_PRICE_PRO_AI_MONTHLY: optional(),
  STRIPE_PRICE_PRO_AI_YEARLY: optional(),
  STRIPE_PRICE_BUSINESS_AI_MONTHLY: optional(),
  STRIPE_PRICE_BUSINESS_AI_YEARLY: optional(),
  STRIPE_PRICE_TABLET_RENTAL_MONTHLY: optional(),
  STRIPE_PRICE_TABLET_RENTAL_YEARLY: optional(),
  STRIPE_PRICE_PRINTER_RENTAL_MONTHLY: optional(),
  STRIPE_PRICE_PRINTER_RENTAL_YEARLY: optional(),
  BREVO_API_KEY: optional(),
  REVIEW_FOLLOWUPS_CRON_SECRET: optional(),
  HUBRISE_CLIENT_ID: optional(),
  HUBRISE_CLIENT_SECRET: optional(),
  HUBRISE_REDIRECT_URI: z.string().default('http://192.168.1.45:8000/integrations/hubrise/callback'),
  HUBRISE_RESULT_REDIRECT_URI: optional(),
  HUBRISE_WEBHOOK_URL: optional(),

  /* Propres au backend Node */
  PORT: integer().default(8000),
  NODE_ENV: z.enum(['development', 'production', 'test']).default('development'),
  LOG_LEVEL: z.enum(['fatal', 'error', 'warn', 'info', 'debug', 'trace', 'silent']).default('info'),
  /**
   * Contrôle d'accès par restaurant (corrections de sécurité, voir PLAN_MIGRATION.md §8).
   * `false` : comportement exact du backend Python.
   */
  STRICT_RESTAURANT_ACCESS: z
    .enum(['true', 'false', '1', '0'])
    .default('true')
    .transform((value) => value === 'true' || value === '1'),

  /* Questionnaire du cockpit (module onboarding) */
  /** Clé partagée avec le cockpit (en-tête `x-cockpit-key`). Absente : les routes du cockpit répondent 503. */
  COCKPIT_API_KEY: optional(),
  /** Page publique du questionnaire : le lien envoyé est `<ONBOARDING_FORM_URL>?t=<jeton>`, et son origine est autorisée (CORS). */
  ONBOARDING_FORM_URL: optional(),
  /** Durée de validité d'un lien de questionnaire, en jours. */
  ONBOARDING_LINK_DAYS: integer().default(30),
  /** Plateforme de commande et de réservation (lien dans l'e-mail de bienvenue). */
  PLATFORM_BASE_URL: z.string().default('https://platform.yumco.fr'),
  APP_IOS_URL: optional(),
  APP_ANDROID_URL: z.string().default('https://play.google.com/store/apps/details?id=com.yumco.yumco'),
});

export type Env = z.infer<typeof EnvSchema>;

const parsed = EnvSchema.safeParse(process.env);
if (!parsed.success) {
  const fields = parsed.error.issues.map((issue) => `${issue.path.join('.')}: ${issue.message}`).join('\n  ');
  throw new Error(`Invalid environment configuration:\n  ${fields}`);
}

export const env: Env = parsed.data;
