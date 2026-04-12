# Frontend Stripe Integration

Ce document explique comment le frontend Yumco doit consommer le backend Stripe pour:

- onboarder un restaurant sur `Stripe Connect Express`
- ouvrir le dashboard Express du restaurant
- encaisser une commande en ligne
- créer et gérer un abonnement Yumco
- afficher les factures d'abonnement

Base URL backend:

```text
https://YOUR_BACKEND_URL
```

Les endpoints proteges attendent:

```http
Authorization: Bearer <jwt>
```

## 1. Stripe Connect Restaurant

### 1.1 Lire le statut Connect

```http
GET /restaurants/{restaurant_id}/stripe/connect
```

Reponse:

```json
{
  "restaurant_id": 3,
  "stripe_account_id": "acct_...",
  "onboarding_completed": true,
  "charges_enabled": true,
  "payouts_enabled": true,
  "details_submitted": true
}
```

Usage UI:

- afficher `Compte Stripe connecte` si `onboarding_completed=true`
- afficher `Terminer l'onboarding` sinon

### 1.2 Creer le compte Connect

```http
POST /restaurants/{restaurant_id}/stripe/connect/account
```

Usage UI:

- peut etre appele automatiquement avant l'onboarding
- si le compte existe deja, le backend renvoie simplement l'etat a jour

### 1.3 Generer le lien d'onboarding

```http
POST /restaurants/{restaurant_id}/stripe/connect/onboarding
Content-Type: application/json
```

Body:

```json
{
  "return_url": "https://front.yumco.fr/stripe/return",
  "refresh_url": "https://front.yumco.fr/stripe/refresh"
}
```

Reponse:

```json
{
  "url": "https://connect.stripe.com/...",
  "expires_at": 1744480000
}
```

Usage UI:

- rediriger immediatement l'utilisateur vers `url`
- si l'utilisateur revient sur `return_url`, recharger `GET /stripe/connect`

### 1.4 Ouvrir le dashboard Express

```http
POST /restaurants/{restaurant_id}/stripe/connect/dashboard
```

Reponse:

```json
{
  "url": "https://connect.stripe.com/express/...",
  "expires_at": null
}
```

Usage UI:

- bouton `Gerer mes paiements`
- ouvrir `url` dans un nouvel onglet

## 2. Paiement d'une commande

### 2.1 Creer une session checkout pour une commande existante

```http
POST /restaurants/{restaurant_id}/orders/{order_id}/checkout-session
Content-Type: application/json
```

Body:

```json
{
  "success_url": "https://front.yumco.fr/checkout/success",
  "cancel_url": "https://front.yumco.fr/checkout/cancel"
}
```

Reponse:

```json
{
  "checkout_session_id": "cs_test_...",
  "checkout_url": "https://checkout.stripe.com/..."
}
```

Usage UI:

- rediriger le client vers `checkout_url`
- ne pas tenter de marquer la commande comme payee cote frontend
- laisser le webhook Stripe mettre a jour le backend

### 2.2 Etat de paiement attendu

Le backend peut retourner:

- `unpaid`
- `awaiting_payment`
- `paid`
- `refunded`

## 3. Abonnement Yumco

## 3.1 Lire l'etat de l'abonnement

```http
GET /restaurants/{restaurant_id}/subscription
```

Reponse:

```json
{
  "plan": "starter",
  "interval": "month",
  "subscription_status": "active",
  "has_tablet_rental": false,
  "has_printer_rental": false,
  "monthly_quota": 0,
  "usage_count": 0,
  "usage_remaining": 0,
  "monthly_token_quota": 0,
  "token_usage_count": 0,
  "token_usage_remaining": 0,
  "cycle_started_at": "2026-04-12T21:36:29.747707+02:00",
  "cycle_ends_at": "2026-05-12T21:36:29.747707+02:00",
  "is_ai_enabled": false,
  "is_quota_reached": false,
  "is_token_quota_reached": false,
  "upgrade_message": "Passez a l'offre Pro IA pour activer l'assistant IA."
}
```

Usage UI:

- afficher l'offre actuelle
- afficher la periodicite `month` ou `year`
- afficher les options materiel actives
- afficher les quotas IA

### 3.2 Creer le premier abonnement

Utiliser ce endpoint uniquement si le restaurant n'a pas encore d'abonnement Stripe actif.

```http
POST /restaurants/{restaurant_id}/subscription/checkout-session
Content-Type: application/json
```

Body:

```json
{
  "subscription_plan": "pro_ai",
  "subscription_interval": "month",
  "has_tablet_rental": true,
  "has_printer_rental": false,
  "success_url": "https://front.yumco.fr/billing/success",
  "cancel_url": "https://front.yumco.fr/billing/cancel"
}
```

Reponse:

```json
{
  "checkout_session_id": "cs_test_...",
  "checkout_url": "https://checkout.stripe.com/..."
}
```

Usage UI:

- rediriger vers `checkout_url`
- sur page success, recharger `GET /subscription`

### 3.3 Mettre a jour un abonnement existant

```http
PUT /restaurants/{restaurant_id}/subscription/stripe
Content-Type: application/json
```

Body:

```json
{
  "subscription_plan": "business_ai",
  "subscription_interval": "year",
  "has_tablet_rental": true,
  "has_printer_rental": true
}
```

Reponse:

- `RestaurantResponse` complet avec les nouveaux champs de subscription

Usage UI:

- appeler cet endpoint depuis l'ecran `Changer mon offre`
- apres succes, recharger `GET /subscription`

### 3.4 Annuler l'abonnement

Annulation a la fin de periode:

```http
DELETE /restaurants/{restaurant_id}/subscription/stripe?at_period_end=true
```

Annulation immediate:

```http
DELETE /restaurants/{restaurant_id}/subscription/stripe?at_period_end=false
```

Reponse:

- `RestaurantResponse`

Usage UI:

- proposer `Annuler a la fin de la periode`
- eviter l'annulation immediate sauf action explicite

### 3.5 Resynchroniser depuis Stripe

```http
POST /restaurants/{restaurant_id}/subscription/stripe/sync
```

Usage UI:

- bouton admin ou fallback si l'UI semble desynchronisee

### 3.6 Lister les factures

```http
GET /restaurants/{restaurant_id}/subscription/invoices
```

Reponse:

```json
[
  {
    "id": "in_...",
    "status": "paid",
    "currency": "eur",
    "total": 4900,
    "hosted_invoice_url": "https://invoice.stripe.com/...",
    "invoice_pdf": "https://pay.stripe.com/invoice/...",
    "created": 1744480000
  }
]
```

Usage UI:

- afficher une liste de factures
- `total` est en centimes
- utiliser `hosted_invoice_url` pour voir la facture
- utiliser `invoice_pdf` pour telecharger le PDF

### 3.7 Portail client Stripe

Ce endpoint peut rester en fallback si certaines actions carte/facturation ne sont pas encore gerees dans Yumco.

```http
POST /restaurants/{restaurant_id}/subscription/customer-portal
Content-Type: application/json
```

Body:

```json
{
  "return_url": "https://front.yumco.fr/settings/billing"
}
```

## 4. Champs utiles cote frontend

`RestaurantResponse` contient maintenant:

```json
{
  "subscription_plan": "starter",
  "subscription_interval": "month",
  "subscription_status": "active",
  "stripe_customer_id": "cus_...",
  "stripe_subscription_id": "sub_...",
  "has_tablet_rental": false,
  "has_printer_rental": false
}
```

## 5. Flux UI recommandes

### 5.1 Ecran paiements restaurant

- charger `GET /stripe/connect`
- si non connecte: bouton `Connecter Stripe`
- clic sur le bouton:
  - `POST /stripe/connect/account`
  - puis `POST /stripe/connect/onboarding`
  - redirection vers Stripe
- si connecte: bouton `Gerer mes paiements`
  - `POST /stripe/connect/dashboard`

### 5.2 Ecran abonnement Yumco

- charger `GET /subscription`
- si pas de `stripe_subscription_id`:
  - afficher CTA `Choisir mon offre`
  - appeler `POST /subscription/checkout-session`
- si abonnement existant:
  - afficher plan, intervalle, options, statut
  - bouton `Modifier mon abonnement`
  - appeler `PUT /subscription/stripe`
  - bouton `Voir mes factures`
  - appeler `GET /subscription/invoices`
  - bouton `Annuler`
  - appeler `DELETE /subscription/stripe?at_period_end=true`

### 5.3 Ecran commande client

- le front cree ou recupere une commande
- le front appelle `POST /orders/{order_id}/checkout-session`
- le client est redirige vers Stripe Checkout
- sur retour success, le front recharge la commande depuis le backend

## 6. Erreurs a gerer cote frontend

Exemples frequents:

- `400 Restaurant already has an active Stripe subscription`
- `400 Restaurant does not have an existing Stripe subscription`
- `400 Restaurant Stripe account is not ready to accept payments`
- `503 Stripe is not configured on the server`

Recommandation UI:

- afficher le `detail` du backend si present
- prevoir un bouton `Reessayer`
- pour les ecrans abonnement, proposer `Actualiser` qui relance `GET /subscription`

## 7. Notes importantes

- les paiements commandes passent par `Stripe Connect Express`
- les abonnements Yumco passent par `Stripe Billing`
- le frontend ne doit pas deduire seul l'etat final du paiement ou de l'abonnement
- le webhook Stripe reste la source de synchronisation la plus fiable
