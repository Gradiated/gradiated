import { sql } from "drizzle-orm";
import {
  check,
  pgTable,
  text,
  timestamp,
  uniqueIndex,
  uuid,
} from "drizzle-orm/pg-core";

// Public waitlist signups from the website. Deliberately unconnected to the
// auth tables: a signup is a lead, not an account, and beta invitations are
// minted from this list by hand rather than by a foreign key.
export const waitlistSignups = pgTable(
  "waitlist_signups",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    email: text("email").notNull(),
    companySize: text("company_size").notNull(),
    monthlyTokenSpendUsd: text("monthly_token_spend_usd").notNull(),
    motivation: text("motivation").notNull(),
    createdAt: timestamp("created_at", { withTimezone: true, mode: "date" })
      .defaultNow()
      .notNull(),
    updatedAt: timestamp("updated_at", { withTimezone: true, mode: "date" })
      .defaultNow()
      .notNull(),
  },
  (t) => [
    uniqueIndex("waitlist_signups_email_unique").on(t.email),
    check(
      "waitlist_signups_email_check",
      sql`length(${t.email}) between 3 and 320`,
    ),
    check(
      "waitlist_signups_motivation_check",
      sql`length(${t.motivation}) between 1 and 4000`,
    ),
  ],
);
