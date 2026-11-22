export const MEMORY_TRANSFER_DURATION = 1.2;

export const createMemoryDemo = (initialWords = [3, 6, 0, 0]) => {
  const words = [...initialWords];
  let address = 0;
  let action = "Read";
  let output = words[0];
  let pending = null;

  const choose = (nextAction, nextAddress) => {
    if (
      !["Read", "Write"].includes(nextAction) ||
      !Number.isInteger(nextAddress) ||
      nextAddress < 0 ||
      nextAddress >= words.length
    )
      throw new RangeError("Choose a valid memory action and address");

    address = nextAddress;
    action = nextAction;
    pending = { value: action === "Write" ? 9 : words[address] };
  };

  const frame = (elapsed = 0) => {
    let transfer = null;
    const progress = Math.max(
      0,
      Math.min(1, elapsed / MEMORY_TRANSFER_DURATION),
    );
    if (pending && progress === 1) {
      if (action === "Write") words[address] = pending.value;
      output = words[address];
      pending = null;
    } else if (pending) {
      transfer = { kind: action, value: pending.value, progress };
    }

    return {
      address,
      action,
      input: 9,
      output,
      words: [...words],
      transfer,
      busy: pending !== null,
      we: action === "Write" ? 1 : 0,
    };
  };

  return { choose, frame };
};

export const ADDER_MEMORY_DURATION = 4.4;

export const createAdderMemoryDemo = (initialWords = [3, 6, 0, 0]) => {
  const words = [...initialWords];
  const writeStart = 0.8;
  const writeEnd = writeStart + MEMORY_TRANSFER_DURATION;
  const readStart = writeEnd + 0.6;
  const readEnd = readStart + MEMORY_TRANSFER_DURATION;
  const frame = (elapsed = 0) => {
    const written = elapsed >= writeEnd;
    const reading = elapsed >= readStart && elapsed < readEnd;
    const writing = elapsed >= writeStart && !written;
    const contents = words.map((word, row) =>
      written && row === 1 ? 9 : word,
    );
    const transfer =
      writing || reading
        ? {
            kind: writing ? "Write" : "Read",
            value: 9,
            progress:
              (elapsed - (writing ? writeStart : readStart)) /
              MEMORY_TRANSFER_DURATION,
          }
        : null;

    return {
      address: 1,
      action: written ? "Read" : "Write",
      input: 9,
      output: written ? 9 : words[1],
      words: contents,
      transfer,
      busy: elapsed < readEnd,
      we: writing ? 1 : 0,
    };
  };

  return { frame };
};

export const REGISTER_MODEL = (() => {
  const PERIOD = 18;
  const TRANSFER_DURATION = 0.9;
  const transfers = [
    { start: 3, from: 3, to: 12 },
    { start: 6, from: 12, to: 9 },
    { start: 12, from: 9, to: 6 },
    { start: 14.5, from: 6, to: 3 },
  ];
  const frame = (elapsed) => {
    const time = Math.max(0, elapsed) % PERIOD;
    const input =
      time < 1 ? 3 : time < 6 ? 12 : time < 10 ? 9 : time < 14.5 ? 6 : 3;
    const we = (time >= 3 && time < 9) || time >= 12 ? 1 : 0;
    let output = 3;
    let transfer = null;
    for (const event of transfers) {
      if (time >= event.start + TRANSFER_DURATION) output = event.to;
      else if (time >= event.start) {
        transfer = {
          ...event,
          progress: (time - event.start) / TRANSFER_DURATION,
        };
        break;
      }
    }
    const changes = [
      { start: 1, from: 3, to: 12 },
      { start: 6, from: 12, to: 9 },
      { start: 10, from: 9, to: 6 },
      { start: 14.5, from: 6, to: 3 },
    ];
    const change = changes.findLast((event) => time >= event.start);
    const inputChange = change ? { ...change, age: time - change.start } : null;
    return { time, input, we, output, transfer, inputChange };
  };
  return { PERIOD, TRANSFER_DURATION, frame };
})();

export const createLatchModel = (events, period = 40) => {
  const build = (initialQ, initialD = 0) => {
    let d = initialD,
      we = 1,
      q = initialQ,
      transfer = null,
      changedAt = null;
    const stages = [{ time: 0, d: 0, we: 1 }, ...events].map((event) => {
      if (event.d !== undefined && event.d !== d) {
        d = event.d;
        changedAt = event.time;
      }
      if (event.we !== undefined) we = event.we;
      if (!we) transfer = null;
      else if (q !== d) {
        transfer = { start: event.time, from: q, to: d, duration: 0.6 };
        q = d;
      }
      return { time: event.time, d, we, q, transfer, changedAt };
    });
    stages.forEach((stage, i) => {
      const moving = stage.transfer;
      if (!moving || moving.start !== stage.time) return;
      const next = stages
        .slice(i + 1)
        .find((later) => later.transfer !== moving);
      moving.duration = Math.min(
        0.6,
        ((next?.time ?? period) - moving.start) * 0.8,
      );
    });
    return stages;
  };
  const first = build(0);
  const repeated = build(first[first.length - 1].q, first[first.length - 1].d);
  const frame = (elapsed) => {
    const time = Math.max(0, elapsed) % period;
    const stages = elapsed < period ? first : repeated;
    const stage = stages.findLast((entry) => entry.time <= time);
    const transfer = stage.transfer;
    const progress = transfer ? (time - transfer.start) / transfer.duration : 1;
    const moving = transfer && progress < 1;
    return {
      time,
      d: stage.d,
      we: stage.we,
      q: moving ? transfer.from : stage.q,
      dataAge: stage.changedAt === null ? null : time - stage.changedAt,
      transfer: moving ? { ...transfer, progress } : null,
    };
  };
  return { period, frame };
};

export const dataChangePulse = (age) =>
  age === null || age < 0 || age >= 0.65 ? 0 : Math.sin((Math.PI * age) / 0.65);
