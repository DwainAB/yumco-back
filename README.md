# Yumco API (Node.js + Prisma)

Portage en Node.js du backend FastAPI `../back-yumco`. Même API, même base PostgreSQL, mêmes variables d'environnement.
Le détail de la migration (correspondance fichier par fichier, choix techniques) est dans [PLAN_MIGRATION.md](PLAN_MIGRATION.md).

## Prérequis

- Node.js 24 ou plus récent
- PostgreSQL (la base Yumco ; pour les tests, un serveur local)

## Installation

```bash
npm install
cp ../back-yumco/.env .env   # même fichier que le backend Python
npm run db:generate          # génère le client Prisma (src/generated, non versionné)
```

Variables propres au backend Node, en plus de celles du Python :

| Variable | Défaut | Rôle |
|---|---|---|
| `PORT` | `8000` | Port HTTP (Railway le fournit) |
| `NODE_ENV` | `development` | `production` en ligne (logs JSON) |
| `LOG_LEVEL` | `info` | Niveau des logs |
| `STRICT_RESTAURANT_ACCESS` | `true` | Corrections de sécurité (voir plus bas). `false` : comportement exact du Python |
| `COCKPIT_API_KEY` | — | Clé partagée avec le cockpit (questionnaire, module `onboarding`). Absente : routes du cockpit en 503 |
| `ONBOARDING_FORM_URL` | — | Page publique du questionnaire ; son origine est autorisée en CORS |
| `ONBOARDING_LINK_DAYS` | `30` | Validité d'un lien de questionnaire |
| `PLATFORM_BASE_URL` | `https://platform.yumco.fr` | Lien de la page de commande dans l'e-mail de bienvenue |
| `APP_IOS_URL` / `APP_ANDROID_URL` | — / Google Play | Liens de l'application dans l'e-mail de bienvenue |

Les tables `onboarding_invitations` et `restaurant_sites` sont créées par `prisma/sql/001_onboarding.sql` (ajout seul, à appliquer une fois).

## Commandes

| Commande | Rôle |
|---|---|
| `npm run dev` | Serveur de développement, rechargé à chaque modification |
| `npm run build` | Génère le client Prisma et compile dans `dist/` |
| `npm start` | Lance la version compilée |
| `npm run typecheck` | Vérification TypeScript |
| `npm test` | Tests (Vitest) |

## Base de données

Le schéma `prisma/schema.prisma` décrit la base existante telle qu'elle est (lu avec `prisma db pull`).
Comparé à la base Railway, il ne présente **aucune différence** (`prisma migrate diff` est vide).

- **Ne pas lancer `prisma migrate` sur la base de production** tant que la bascule n'est pas décidée : les tables sont encore
  gérées par Alembic côté Python. La procédure de bascule est décrite dans PLAN_MIGRATION.md §6.
- Les connexions sont ouvertes en UTC (`-c timezone=UTC`) : l'adaptateur PostgreSQL de Prisma suppose une session en UTC
  pour lire les dates avec fuseau.

## Tests

```bash
npm test
```

Les tests utilisent une base locale dédiée, recréée à chaque lancement à partir du schéma Prisma. Elle est définie dans
`.env.test` (non versionné) :

```
DATABASE_URL=postgresql://utilisateur:motdepasse@localhost:5432/yumco_test_node
SECRET_KEY=test-secret-key
...
```

Le nom de la base doit contenir « test » (garde-fou). Les e-mails, notifications et le géocodage sont simulés.

Contenu : les 78 tests du backend Python portés un par un, plus des tests sur les corrections de sécurité, chaque route de
l'application (aucune erreur 500), le CORS, et les règles de compatibilité (validation Pydantic, arrondis Python, formats JSON).

## Compatibilité avec le backend Python

Vérifiée en faisant tourner les deux backends sur une copie locale de la base Railway :

- **Lecture** : 189 requêtes comparées (toutes les routes de lecture, erreurs de validation et d'authentification) →
  187 réponses identiques, les 2 autres sont des écarts voulus.
- **Écriture** : un scénario de 73 étapes (commandes, articles, statuts, codes promo, restaurant complet, catalogue, tables,
  réservations, annonces, comptes) joué sur deux copies identiques de la base → 71 réponses identiques, et après le scénario
  **27 tables sur 28 identiques** ligne à ligne (la 28e diffère à cause d'un écart voulu).
- Un jeton JWT émis par le backend Python est accepté par le backend Node, et inversement. Les mots de passe sont compatibles.

Écarts voulus :

| Situation | Python | Node |
|---|---|---|
| Listes sans tri explicite (`/admin/users`, lignes d'une commande…) | ordre physique des lignes en base | tri par identifiant |
| `GET /restaurants/{id}/subscription` | 404 (route supprimée le 01/05/2026) | remise en place, lecture seule |
| Date invalide dans `/orders/slots?date=` | 500 | 422 |
| Date sans fuseau et date avec fuseau dans un même code promo | 500 | accepté (UTC) |
| Précision des dates | microseconde | milliseconde |
| Tâches de fond (e-mail, notification, HubRise) | la première en erreur bloque les suivantes | indépendantes |
| Tickets PDF | heure en UTC | heure du restaurant |
| Création d'un restaurant ou d'un menu | plusieurs enregistrements séparés | une transaction |
| Envoi à HubRise sans message d'erreur | plantage, commande bloquée en `pending` | erreur enregistrée |

## Sécurité (`STRICT_RESTAURANT_ACCESS=true`)

Corrections décrites dans PLAN_MIGRATION.md §8 : un compte n'accède qu'aux restaurants auxquels il est rattaché (sauf admin),
seul un admin change la formule, les quotas IA ou l'identifiant Stripe d'un restaurant, `/admin/users/{id}`, `/test-email` et
le test de recherche web IA ne sont plus publics, les commandes refusent les produits d'un autre restaurant et les quantités
négatives, et le webhook Stripe refuse les événements non signés. Les routes publiques de la plateforme ne changent pas.

L'application mobile renvoie le restaurant complet à chaque modification : une valeur réservée aux admins renvoyée à
l'identique est acceptée, seule une valeur modifiée est refusée.

## Déploiement sur Railway

1. Créer un nouveau service à partir de ce dossier (le backend Python reste en place).
2. Variables : les mêmes que le service Python (`DATABASE_URL`, `SECRET_KEY`, Brevo, Stripe, Cloudinary, OpenAI, HubRise…),
   plus `NODE_ENV=production`.
3. Commande de build : `npm ci && npm run build` (les dépendances de développement sont nécessaires au build :
   `prisma` et `typescript`). Commande de démarrage : `npm start`.
4. Vérifier `GET /` sur l'URL du nouveau service, puis tester les parcours avec l'application avant de changer l'URL de l'API
   dans la plateforme, le dashboard et l'application mobile.
5. Webhooks à repointer au moment de la bascule : Stripe (`/stripe/webhooks`) et HubRise (`/integrations/hubrise/webhook`,
   variable `HUBRISE_WEBHOOK_URL`), ainsi que `HUBRISE_REDIRECT_URI`.

## Non repris du backend Python

- La documentation interactive de FastAPI (`/docs`, `/openapi.json`).
- Les messages d'erreur JSON exacts de `json.loads` (le type d'erreur et sa position sont repris, pas le texte).
