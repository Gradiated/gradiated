export const MEMORY_ACCESS_DURATION = 3.8;

export const createMemoryAccessModel = () => {
  const contents = new Map([
    [0, 3],
    [1, 6],
    [65535, 0],
  ]);
  let mar = 0;
  let mdr = 0;
  let transaction = null;
  const choose = (action) => {
    if (action !== "Read" && action !== "Write")
      throw Error("Unknown memory action.");
    transaction = { action, stored: contents.get(1) };
  };
  const frame = (time = 0) => {
    const t = Math.max(0, time);
    const read = transaction?.action === "Read";
    const write = transaction?.action === "Write";
    if (transaction && t >= 0.9) mar = 1;
    if (write && t >= 0.9) mdr = 9;
    if (write && t >= 2.8) contents.set(1, 9);
    if (read && t >= 3.1) mdr = transaction.stored;
    const busy = Boolean(transaction) && t < MEMORY_ACCESS_DURATION;
    return {
      action: transaction?.action ?? "Ready",
      address: mar,
      mar,
      mdr,
      output: mdr,
      words: [contents.get(0), contents.get(1), null, contents.get(65535)],
      time: t,
      busy,
      we: write && t >= 1.25 && t < 2.9 ? 1 : 0,
      selected: Boolean(transaction) && t >= 0.9,
      clock:
        Boolean(transaction) &&
        ((t >= 0.86 && t < 1.06) || (read && t >= 3.06 && t < 3.26)),
      transfer:
        transaction && t >= 1.6 && t < 2.8
          ? {
              kind: transaction.action,
              value: read ? transaction.stored : 9,
              progress: (t - 1.6) / 1.2,
            }
          : null,
    };
  };
  return { choose, frame };
};
