# Migration du backend Yumco : Python (FastAPI) → Node.js (TypeScript + Prisma)

Le backend Python d'origine (`../back-yumco`) n'est pas modifié. Ce dossier contient sa copie en Node.js :
même API, même base de données, mêmes variables d'environnement. Seuls le langage et l'organisation du code changent.

## État d'avancement (24/10/2026)

| Étape | État |
|---|---|
| 1. Projet, schéma Prisma (identique à la base Railway), socle | Fait |
| 2. Domaines simples | Fait |
| 3. Commandes, tarification, livraison, e-mails, tickets, exports, relances d'avis | Fait |
| 4. Stripe Connect et paiement en ligne | Fait (non testé en conditions réelles) |
| 5. HubRise | Fait (non testé en conditions réelles) |
| 6. Statistiques, recommandations, assistant IA | Fait (IA non testée en conditions réelles) |
| 7. Tests et parité | Fait : 243 tests ; parité 187/189 en lecture, 71/73 en écriture, 27/28 tables identiques (écarts voulus, voir README) |
| 8. Mise en ligne et bascule | À faire, avec ton accord |

Restent à tester avec des clés de test ou à la main : paiement Stripe de bout en bout, envoi et retour HubRise,
e-mails Brevo réels, assistant IA (OpenAI), envoi d'images Cloudinary.

---

## 1. Principes

1. **Contrat d'API identique** : mêmes routes, mêmes méthodes, mêmes codes HTTP, mêmes noms de champs (snake_case),
   mêmes messages d'erreur (`{"detail": "..."}`). La plateforme, le dashboard et l'application mobile ne doivent rien changer,
   à part l'URL du backend au moment de la bascule.
2. **Même base PostgreSQL** (Railway). Aucune modification de structure pendant la migration : le schéma Prisma est
   lu depuis la base (`prisma db pull`, lecture seule).
3. **Même `.env`** : les mêmes variables que `app/core/config.py`, avec les mêmes valeurs par défaut.
4. **Compatibilité totale des comptes** : mêmes jetons JWT (HS256, `sub` = email) et mêmes mots de passe bcrypt.
   Un jeton créé par le backend Python reste valable sur le backend Node, et inversement.
5. **Les deux backends peuvent tourner en même temps** sur la même base pendant la bascule.

## 2. Stack

| Besoin | Python | Node.js |
|---|---|---|
| Langage | Python 3.13 | Node 24, TypeScript (strict) |
| Serveur HTTP | FastAPI + Uvicorn | Express 5 |
| Validation | Pydantic v2 | Zod 4 (règles de Pydantic reproduites : conversions, `exclude_unset`, erreurs 422) |
| ORM / base | SQLAlchemy + Alembic | Prisma 7 (adaptateur `pg`) |
| Calculs d'argent | `Decimal` | `decimal.js` (même arrondi `ROUND_HALF_UP`) |
| Fuseaux horaires | `zoneinfo` | Luxon |
| JWT | python-jose | jose |
| Mots de passe | passlib + bcrypt | bcryptjs (hachages `$2b$` compatibles) |
| Paiement | stripe 13.0.1 (API `2025-09-30.clover`) | stripe 19.0.0 (**même version d'API**) |
| Images | cloudinary | cloudinary |
| PDF | reportlab | pdfkit |
| Envoi de fichiers | python-multipart | multer |
| Logs | `print` | pino (logs structurés) |
| Tests | pytest + TestClient | Vitest + Supertest |

## 3. Organisation du code

Le Python range le code par type de fichier (`routes/`, `services/`, `schemas/`, `models/`).
Le Node le range **par domaine métier** : tout ce qui concerne les commandes est dans `src/modules/orders/`, etc.

```
back-yumco-node/
├── prisma/
│   └── schema.prisma            ← lu depuis la base (remplace app/models/*)
├── prisma.config.ts
├── src/
│   ├── server.ts                ← démarrage (uvicorn main:app)
│   ├── app.ts                   ← main.py : CORS, routeurs, /, /test-email
│   ├── config/env.ts            ← app/core/config.py
│   ├── db/prisma.ts             ← app/db/database.py
│   ├── lib/                     ← outils communs
│   │   ├── http-error.ts        ← HTTPException
│   │   ├── validation.ts        ← équivalents Pydantic + format des erreurs 422
│   │   ├── serialize.ts         ← formats JSON (Decimal en texte, dates ISO…)
│   │   ├── money.ts             ← _money(), arrondis
│   │   ├── python.ts            ← round() de Python, etc.
│   │   ├── time.ts              ← fuseaux horaires
│   │   ├── background.ts        ← BackgroundTasks
│   │   └── logger.ts
│   ├── middleware/
│   │   ├── auth.ts              ← get_current_user, require_admin, check_permission
│   │   └── errors.ts            ← erreurs 404 / 422 / 500
│   └── modules/
│       ├── auth/                ← auth, utilisateurs, appareils
│       ├── restaurants/         ← restaurants, adresse, config, horaires, tranches de livraison
│       ├── subscriptions/       ← quotas IA et formules
│       ├── admin/
│       ├── catalog/             ← catégories, produits, menus, buffet à volonté, recommandations
│       ├── uploads/             ← Cloudinary
│       ├── tables/
│       ├── reservations/
│       ├── customers/
│       ├── orders/              ← commandes, tarification, créneaux, e-mails, tickets, exports
│       ├── promo-codes/
│       ├── announcements/
│       ├── analytics/           ← chiffre d'affaires, commandes, clients, performance
│       ├── ai/                  ← assistant IA (OpenAI) et conversations
│       ├── stripe/              ← Stripe Connect, paiement en ligne, webhook
│       ├── hubrise/             ← connexion, synchronisation, webhook
│       ├── review-followups/    ← relances avis Google (route interne)
│       ├── notifications/       ← notifications Expo
│       ├── email/               ← Brevo
│       └── geo/                 ← Nominatim (géocodage, distances)
└── test/                        ← tests portés depuis tests/
```

Dans chaque module : `*.routes.ts` (routes), `*.service.ts` (logique), `*.schemas.ts` (validation des entrées),
`*.serializers.ts` (forme des réponses, équivalent des `response_model`).

## 4. Correspondance fichier par fichier

### Socle

| Python | Node.js | Notes |
|---|---|---|
| `main.py` | `src/app.ts`, `src/server.ts` | Même ordre d'enregistrement des routes (il compte : `/customers/analytics` avant `/customers/{id}`). |
| `app/core/config.py` | `src/config/env.ts` | Mêmes variables, mêmes défauts, `CORS_ALLOWED_ORIGINS` en liste JSON ou séparée par des virgules. |
| `app/core/security.py` | `src/modules/auth/password.ts`, `jwt.ts`, `src/middleware/auth.ts` | Mêmes réponses 401 (`Not authenticated`, `Could not validate credentials`). |
| `app/db/database.py` | `src/db/prisma.ts` | Un seul client Prisma pour toute l'application. |
| `app/models/*.py` (28 fichiers) | `prisma/schema.prisma` | Modèles nommés en PascalCase, champs gardés en snake_case comme en base et dans l'API. |
| `alembic/` | (inchangé) | Voir §6. |

### Routes → modules

| Python | Node.js |
|---|---|
| `routes/auth.py` | `modules/auth/auth.routes.ts` |
| `routes/restaurant.py` | `modules/restaurants/restaurants.routes.ts` |
| `routes/admin.py` | `modules/admin/admin.routes.ts` |
| `routes/product.py` | `modules/catalog/products.routes.ts` |
| `routes/menu.py` | `modules/catalog/menus.routes.ts` |
| `routes/all_you_can_eat.py` | `modules/catalog/all-you-can-eat.routes.ts` |
| `routes/upload.py` | `modules/uploads/uploads.routes.ts` |
| `routes/table.py` | `modules/tables/tables.routes.ts` |
| `routes/reservation.py` | `modules/reservations/reservations.routes.ts` |
| `routes/customer.py` | `modules/customers/customers.routes.ts` |
| `routes/order.py` | `modules/orders/orders.routes.ts` |
| `routes/revenue.py`, `performance.py`, `customer_analytics.py` | `modules/analytics/analytics.routes.ts` |
| `routes/ai.py` | `modules/ai/ai.routes.ts` |
| `routes/stripe_connect.py` | `modules/stripe/stripe.routes.ts` |
| `routes/hubrise.py` | `modules/hubrise/hubrise.routes.ts` |
| `routes/promo_code.py` | `modules/promo-codes/promo-codes.routes.ts` |
| `routes/announcement.py` | `modules/announcements/announcements.routes.ts` |
| `routes/internal.py` | `modules/review-followups/internal.routes.ts` |

### Services

| Python | Node.js |
|---|---|
| `user_service.py` | `modules/auth/users.service.ts` |
| `restaurant_service.py` | `modules/restaurants/restaurants.service.ts` |
| `subscription_service.py` | `modules/subscriptions/subscriptions.service.ts` |
| `product_service.py` | `modules/catalog/products.service.ts` |
| `menu_service.py` | `modules/catalog/menus.service.ts` |
| `recommendation_service.py` | `modules/catalog/recommendations.service.ts` |
| `cloudinary_service.py` | `modules/uploads/cloudinary.service.ts` |
| `order_service.py` | `modules/orders/orders.service.ts` + `pricing.service.ts` |
| `order_email_service.py` | `modules/orders/order-emails.service.ts` |
| `receipt_service.py` | `modules/orders/receipts.service.ts` |
| `order_export_service.py` | `modules/orders/exports.service.ts` |
| `promo_code_service.py` | `modules/promo-codes/promo-codes.service.ts` |
| `announcement_service.py` | `modules/announcements/announcements.service.ts` |
| `order_analytics_service.py` | `modules/analytics/order-analytics.service.ts` |
| `revenue_analytics_service.py` | `modules/analytics/revenue-analytics.service.ts` |
| `customer_analytics_service.py` | `modules/analytics/customer-analytics.service.ts` |
| `performance_analytics_service.py` | `modules/analytics/performance-analytics.service.ts` |
| `ai_service.py` | `modules/ai/ai.service.ts` + `ai-context.ts` + `ai-prompt.ts` |
| `ai_conversation_service.py` | `modules/ai/conversations.service.ts` |
| `stripe_connect_service.py` | `modules/stripe/stripe-connect.service.ts` |
| `hubrise_service.py` | `modules/hubrise/hubrise.service.ts` + `hubrise-payloads.ts` |
| `review_followup_service.py` | `modules/review-followups/review-followups.service.ts` |
| `notification_service.py` | `modules/notifications/push.service.ts` |
| `email_service.py` | `modules/email/email.service.ts` |
| `geo_service.py` | `modules/geo/geo.service.ts` |

### Schémas Pydantic → validation Zod et serializers

| Python (`app/schemas/`) | Node.js |
|---|---|
| `user.py` | `modules/auth/users.schemas.ts`, `users.serializers.ts` |
| `restaurant.py`, `restaurant_config.py`, `address.py`, `delivery_tiers.py`, `opening_hours.py` | `modules/restaurants/restaurants.schemas.ts`, `restaurants.serializers.ts` |
| `product.py`, `category.py`, `menu.py`, `all_you_can_eat.py`, `recommendation.py` | `modules/catalog/*.schemas.ts`, `catalog.serializers.ts` |
| `table.py` | `modules/tables/tables.schemas.ts` |
| `reservation.py` | `modules/reservations/reservations.schemas.ts` |
| `customer.py` | `modules/customers/customers.schemas.ts` |
| `order.py` | `modules/orders/orders.schemas.ts`, `orders.serializers.ts` |
| `promo_code.py` | `modules/promo-codes/promo-codes.schemas.ts` |
| `announcement.py` | `modules/announcements/announcements.schemas.ts` |
| `ai.py`, `ai_conversation.py` | `modules/ai/ai.schemas.ts` |
| `stripe_connect.py` | `modules/stripe/stripe.schemas.ts` |
| `hubrise.py` | `modules/hubrise/hubrise.schemas.ts` |
| `*_analytics.py` | types TypeScript dans `modules/analytics/` |

### Tests

| Python (`tests/`) | Node.js (`test/`) |
|---|---|
| `integration/conftest.py` | `test/setup.ts` : base de test créée depuis le schéma Prisma, nettoyée entre les tests |
| `integration/test_*.py` (78 tests) | `test/integration/*.test.ts`, même scénario test par test |
| `test_routes_smoke.py` | `test/routes-smoke.test.ts` : chaque route répond sans erreur 500 |

## 5. Points de compatibilité à respecter

- **Montants** : FastAPI renvoie les champs `Decimal` en **texte** (`"price": "12.50"`) et les champs `float` en nombre
  (`"amount_total": 12.5`). Les serializers reproduisent exactement cette différence, champ par champ.
- **Dates** : ISO 8601 en UTC (`2026-05-15T14:28:08.123Z`). Les dates en heure locale (créneaux, statistiques clients)
  gardent leur décalage (`+02:00`). Différence connue : Node a une précision à la milliseconde, Python à la microseconde.
- **Erreurs** : `{"detail": "..."}` avec les mêmes textes et codes. Les erreurs de validation renvoient 422 et une liste
  `detail` au format FastAPI (`type`, `loc`, `msg`, `input`).
- **Slash final** : `/restaurants` et `/restaurants/` répondent tous les deux, comme `/upload` et `/upload/`.
- **Mises à jour partielles** : un champ absent n'est pas modifié, un champ envoyé à `null` est mis à `null`
  (équivalent de `model_dump(exclude_unset=True)`).
- **Formulaires** (produits) : un champ vide vaut « non envoyé », les booléens acceptent `true/false/1/0/yes/no/on/off`,
  `allergens` peut être répété.
- **Tâches de fond** (e-mails, notifications, HubRise) : lancées après l'envoi de la réponse, dans le même ordre.
- **Commandes en attente de paiement** (`pending_online_orders.payload_json`) : même format JSON, pour qu'une commande
  commencée sur un backend puisse être terminée par l'autre pendant la bascule.
- **Valeurs par défaut** : SQLAlchemy ajoute des valeurs par défaut côté Python (`is_deleted = false`, `status = 'pending'`…)
  que la base ne connaît pas. Elles sont reproduites dans le code Node, sans toucher à la base.
- **`updated_at`** : renseigné à chaque modification, comme `onupdate=func.now()`.

## 6. Base de données et migrations

1. `prisma db pull` lit la structure de la base Railway (lecture seule) et génère `prisma/schema.prisma`.
2. Le schéma est ensuite renommé proprement (modèles en PascalCase avec `@@map`, relations nommées).
3. **Aucune migration n'est appliquée pendant la migration du code.**
4. Le jour de la bascule (avec ton accord) : on crée une migration « de départ » qui décrit la base actuelle et on la
   marque comme déjà appliquée (`prisma migrate resolve`). Cela crée la table `_prisma_migrations` dans la base.
   À partir de là, toutes les évolutions passent par Prisma et Alembic n'est plus utilisé.
5. Les nouvelles tables du cockpit (fiche site du restaurant, invitations du gérant) seront la première migration Prisma.

## 7. Bugs du Python corrigés au passage (sans effet sur les applications)

1. **Tâches de fond en chaîne** : si l'e-mail de confirmation échoue, la notification et l'envoi à HubRise ne partent pas
   (Starlette s'arrête à la première tâche en erreur). En Node, chaque tâche est indépendante.
2. **HubRise** : `sync_order_to_hubrise` plante (`response` non défini) quand HubRise renvoie une erreur sans message ;
   la commande reste bloquée en `pending`.
3. **Création de restaurant** en plusieurs enregistrements : une erreur au milieu laisse un restaurant à moitié créé.
   En Node, tout est fait dans une seule transaction.
4. **Tickets PDF** : l'heure affichée est en UTC (décalage de 1 à 2 h en France). En Node, elle est à l'heure du restaurant.
5. **Statistiques clients** : l'expression `\\D` ne retire pas les caractères non numériques des téléphones ; un même client
   écrit `06 12…` et `0612…` compte deux fois.
6. **Export PDF** : la police n'est pas remise après un saut de page.

## 8. Failles de sécurité trouvées (à valider)

Tant qu'il n'y a pas de clients, c'est le bon moment pour les corriger. Les corrections sont regroupées dans un seul
contrôle d'accès, désactivable par une variable d'environnement si une application en dépend.

1. **Accès entre restaurants** : la plupart des routes vérifient seulement qu'on est connecté, pas qu'on appartient au
   restaurant. N'importe quel compte peut lire ou modifier les commandes, clients (données personnelles), produits,
   tables, réservations… d'un autre restaurant. `PUT /restaurants/{id}` permet même de changer sa formule ou ses quotas IA.
   → Correction : il faut être admin ou rattaché au restaurant.
2. `GET /restaurants/{id}/users` liste les comptes de n'importe quel restaurant.
3. `GET /admin/users/{id}` n'est pas réservé aux admins.
4. `POST /restaurants/{id}/ai/debug/web-search` ne demande aucune connexion : n'importe qui peut consommer le crédit OpenAI.
5. `GET /test-email` est public : n'importe qui peut envoyer des e-mails via le compte Brevo.
6. **Commandes** : les produits, menus et options ne sont pas vérifiés par restaurant, et une quantité négative est
   acceptée (total négatif).
7. **Webhook Stripe** : sans `STRIPE_WEBHOOK_SECRET`, les événements non signés sont acceptés (on peut marquer une commande
   comme payée). → Refuser en production.
8. **Changement de rôle** (`PUT /auth/users/{id}`) : la permission est vérifiée sur le premier rôle de l'utilisateur
   connecté, quel que soit le restaurant.

## 9. Point à trancher

- Le dashboard appelle `GET /restaurants/{id}/subscription`, supprimé du backend le 01/05/2026 (commit `9569317`,
  « fix : address platform »). Aujourd'hui il reçoit une 404. Le service (`get_subscription_usage`) existe toujours.
  → Proposition : remettre cette route en lecture seule.

## 10. Vérification

1. Tests portés depuis `tests/` sur une base de test locale.
2. **Test de parité** : les deux backends tournent en local sur la même base, un script appelle chaque route en lecture
   sur les deux et compare les réponses JSON.
3. Test manuel des parcours sensibles en mode test : commande en ligne avec paiement Stripe, synchronisation HubRise.

## 11. Étapes

1. Mise en place du projet, lecture du schéma de la base, socle (config, Prisma, erreurs, validation, authentification).
2. Domaines simples : utilisateurs, restaurants, catalogue, tables, réservations, clients, annonces, codes promo.
3. Commandes : tarification, livraison, créneaux, e-mails, tickets PDF, exports CSV/PDF, relances d'avis.
4. Stripe Connect et paiement en ligne.
5. HubRise.
6. Statistiques, recommandations, assistant IA.
7. Tests, test de parité.
8. Mise en ligne sur Railway en parallèle de l'ancien backend, puis bascule de l'URL dans les applications
   (avec ton accord).
