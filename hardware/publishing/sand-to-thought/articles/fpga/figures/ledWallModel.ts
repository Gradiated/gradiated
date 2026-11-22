const picture = [
  "0000000000000000",
  "0001100000000000",
  "0011110000000000",
  "0001100000100000",
  "0000000001110000",
  "0000010011111000",
  "0000111111111100",
  "0011111111111110",
];

export const videoFrame = (frame: number) =>
  picture.map((row, y) =>
    [...row].map((_, x) => Number(row[(x + (y < 4 ? frame % 2 : 0)) % 16])),
  );

export const videoTile = (pixels: number[][], tile: number) =>
  pixels.map((row) => row.slice(tile * 4, tile * 4 + 4));

export const videoStep = (step: number) => ({
  phase: step % 4,
  incoming: Math.floor(step / 4),
  displayed: step < 3 ? null : Math.floor((step - 3) / 4),
});
