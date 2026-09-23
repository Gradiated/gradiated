import { eq } from "drizzle-orm";
import { z } from "zod";

import type { ControlDatabase } from "../db/client.js";
import { waitlistSignups } from "../db/schema/waitlist.js";

export const COMPANY_SIZES = [
  "1-10",
  "11-50",
  "51-200",
  "201-500",
  "501-1000",
  "1001-5000",
  "5001+",
] as const;

export const waitlistSignupSchema = z.strictObject({
  email: z.string().trim().toLowerCase().email().max(320),
  companySize: z.enum(COMPANY_SIZES),
  monthlyTokenSpendUsd: z.string().trim().min(1).max(100),
  motivation: z.string().trim().min(1).max(4000),
});

export type WaitlistSignupInput = z.infer<typeof waitlistSignupSchema>;

export interface WaitlistService {
  join(value: unknown): Promise<{ created: boolean; email: string }>;
}

// The welcome email goes only to a first signup, so the insert and the update
// are separate steps rather than one upsert.
export const createWaitlistService = (
  database: ControlDatabase,
): WaitlistService => ({
  async join(value) {
    const input = waitlistSignupSchema.parse(value);

    const [inserted] = await database
      .insert(waitlistSignups)
      .values(input)
      .onConflictDoNothing({ target: waitlistSignups.email })
      .returning({ id: waitlistSignups.id });
    if (inserted) return { created: true, email: input.email };

    await database
      .update(waitlistSignups)
      .set({
        companySize: input.companySize,
        monthlyTokenSpendUsd: input.monthlyTokenSpendUsd,
        motivation: input.motivation,
        updatedAt: new Date(),
      })
      .where(eq(waitlistSignups.email, input.email));

    return { created: false, email: input.email };
  },
});
