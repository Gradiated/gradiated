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
