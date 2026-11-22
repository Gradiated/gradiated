type ScenePosition = { index: number; top: number };

export const selectScrollScene = (
  positions: readonly ScenePosition[],
  line: number,
  active: number,
) => {
  let selected = 0;

  for (const { index, top } of positions) {
    const threshold = line + (index <= active ? 12 : -12);
    if (top <= threshold) selected = index;
  }

  return selected;
};
