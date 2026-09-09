export const ringState = (cursor: number, depth: number, accepted: number) => {
  const initial = Array.from(
    { length: 16 },
    (_, slot) => (slot - cursor + 16) % 16,
  );
  const backup = Array.from({ length: depth }, (_, i) => ({
    slot: (cursor + i) % 16,
    token: i,
  }));
  const proposed = [...initial];
  backup.forEach(({ slot }, i) => {
    proposed[slot] = 16 + i;
  });
  const committed = [...proposed];
  backup.slice(accepted).forEach(({ slot, token }) => {
    committed[slot] = token;
  });
  return {
    initial,
    backup,
    proposed,
    committed,
    nextCursor: (cursor + accepted) % 16,
  };
};

export const visibleKeys = (query: number) =>
  Array.from({ length: 16 }, (_, i) => query + 1 + i);

export const paddingState = (keys: number, query: number, padded: boolean) => {
  const bucket = Math.ceil(keys / 64) * 64;
  const extent = padded ? bucket : keys;
  return {
    extent,
    extra: extent - keys,
    columns: Array.from({ length: 64 }, (_, i) => {
      const index = bucket - 64 + i;
      const kind =
        index >= extent
          ? "absent"
          : index >= keys
            ? "padding"
            : index > query
              ? "future"
              : "visible";
      return { index, kind };
    }),
  };
};

export const activationPayload = (rows: number) => ({
  activationKiB: (rows * 5376 * 2) / 1024,
  metadataBytes: rows * 4,
});
