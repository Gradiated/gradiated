import { z } from "zod";

const email = z.email();

export const parseEmails = (value: string) => {
  const entries = [
    ...new Set(
      value
        .split(/[\s,;]+/)
        .map((entry) => entry.trim().toLowerCase())
        .filter(Boolean),
    ),
  ];

  return {
    emails: entries.filter((entry) => email.safeParse(entry).success),
    invalid: entries.filter((entry) => !email.safeParse(entry).success),
  };
};
