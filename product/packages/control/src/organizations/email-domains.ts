import freeEmailDomains from "free-email-domains";
import { z } from "zod";

const personalDomains = new Set<string>([...freeEmailDomains, "hey.com"]);

export const companyEmailDomain = (user: {
  email: string;
  emailVerified: boolean;
}): string | null => {
  if (!user.emailVerified || !z.email().safeParse(user.email).success)
    return null;

  const domain = user.email.split("@").at(-1)?.toLowerCase();
  if (!domain || !domain.includes(".") || personalDomains.has(domain))
    return null;

  return domain;
};
