export const MEMORY_MODEL = (() => {
  const PERIOD = 12;
  const frame = (elapsed, rows = 4, initialWords = [3, 6, 0, 0]) => {
    const time = Math.max(0, elapsed) % PERIOD;
    const target = rows === 2 ? 1 : 2;
    const words = [...initialWords];
    const input = 9;
    if (elapsed >= PERIOD || time >= 5) words[target] = input;
    const address = time < 2 ? 0 : time < 4 ? 1 : time < 10 ? target : rows - 1;
    const we = time >= 5 && time < 7 ? 1 : 0;
    const action = we ? "Write" : time >= 7 && time < 10 ? "Hold" : "Read";
    return { address, we, input, words, output: words[address], time, action };
  };
  return { PERIOD, frame };
})();

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
