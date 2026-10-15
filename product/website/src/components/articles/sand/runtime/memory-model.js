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
    return { time, input, we, output, transfer };
  };
  return { PERIOD, TRANSFER_DURATION, frame };
})();
