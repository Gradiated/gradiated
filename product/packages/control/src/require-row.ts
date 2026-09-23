export const requireRow = <Row>(rows: Row[], message: string): Row => {
  const [row] = rows;
  if (!row) throw new Error(message);

  return row;
};
