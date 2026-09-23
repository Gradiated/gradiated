const mailboxKey = (email: string) => email.trim().toLowerCase();

export const createTestMailbox = () => {
  const messages = new Map<string, string>();

  return {
    send: (email: string, value: string): void => {
      messages.set(mailboxKey(email), value);
    },
    take: (email: string): string | null => {
      const key = mailboxKey(email);
      const value = messages.get(key) ?? null;
      messages.delete(key);

      return value;
    },
  };
};
