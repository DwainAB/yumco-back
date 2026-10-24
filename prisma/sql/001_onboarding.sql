-- Questionnaire du cockpit : liens d'invitation et fiche site des restaurants (24/10/2026).
-- Ajout seul : aucune table existante n'est modifiée. Généré par prisma migrate diff contre la base Railway.
BEGIN;

-- CreateTable
CREATE TABLE "onboarding_invitations" (
    "id" SERIAL NOT NULL,
    "token_hash" VARCHAR(64) NOT NULL,
    "subscription_plan" VARCHAR NOT NULL,
    "recipient_email" VARCHAR,
    "status" VARCHAR NOT NULL DEFAULT 'pending',
    "answers" JSONB,
    "upload_count" INTEGER NOT NULL DEFAULT 0,
    "restaurant_id" INTEGER,
    "expires_at" TIMESTAMPTZ(6) NOT NULL,
    "submitted_at" TIMESTAMPTZ(6),
    "imported_at" TIMESTAMPTZ(6),
    "created_at" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "onboarding_invitations_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "restaurant_sites" (
    "id" SERIAL NOT NULL,
    "restaurant_id" INTEGER NOT NULL,
    "invitation_id" INTEGER,
    "status" VARCHAR NOT NULL DEFAULT 'design',
    "cuisine_type" VARCHAR,
    "custom_requests" TEXT,
    "logo_url" VARCHAR,
    "images" JSONB NOT NULL DEFAULT '[]',
    "brand_colors" JSONB NOT NULL DEFAULT '[]',
    "brand_font" VARCHAR,
    "wants_online_payment" BOOLEAN NOT NULL DEFAULT false,
    "manager_first_name" VARCHAR NOT NULL,
    "manager_last_name" VARCHAR NOT NULL,
    "manager_email" VARCHAR NOT NULL,
    "manager_phone" VARCHAR,
    "site_url" VARCHAR,
    "repo_url" VARCHAR,
    "owner_user_id" INTEGER,
    "credentials_sent_at" TIMESTAMPTZ(6),
    "created_at" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "restaurant_sites_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "onboarding_invitations_token_hash_key" ON "onboarding_invitations"("token_hash");

-- CreateIndex
CREATE INDEX "ix_onboarding_invitations_status" ON "onboarding_invitations"("status");

-- CreateIndex
CREATE UNIQUE INDEX "restaurant_sites_restaurant_id_key" ON "restaurant_sites"("restaurant_id");

-- CreateIndex
CREATE UNIQUE INDEX "restaurant_sites_invitation_id_key" ON "restaurant_sites"("invitation_id");

-- AddForeignKey
ALTER TABLE "onboarding_invitations" ADD CONSTRAINT "onboarding_invitations_restaurant_id_fkey" FOREIGN KEY ("restaurant_id") REFERENCES "restaurants"("id") ON DELETE SET NULL ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE "restaurant_sites" ADD CONSTRAINT "restaurant_sites_restaurant_id_fkey" FOREIGN KEY ("restaurant_id") REFERENCES "restaurants"("id") ON DELETE CASCADE ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE "restaurant_sites" ADD CONSTRAINT "restaurant_sites_invitation_id_fkey" FOREIGN KEY ("invitation_id") REFERENCES "onboarding_invitations"("id") ON DELETE SET NULL ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE "restaurant_sites" ADD CONSTRAINT "restaurant_sites_owner_user_id_fkey" FOREIGN KEY ("owner_user_id") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE NO ACTION;


COMMIT;
