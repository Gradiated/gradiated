CREATE TABLE "waitlist_signups" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"email" text NOT NULL,
	"company_size" text NOT NULL,
	"monthly_token_spend_usd" text NOT NULL,
	"motivation" text NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "waitlist_signups_email_check" CHECK (length("waitlist_signups"."email") between 3 and 320),
	CONSTRAINT "waitlist_signups_motivation_check" CHECK (length("waitlist_signups"."motivation") between 1 and 4000)
);
--> statement-breakpoint
CREATE UNIQUE INDEX "waitlist_signups_email_unique" ON "waitlist_signups" USING btree ("email");