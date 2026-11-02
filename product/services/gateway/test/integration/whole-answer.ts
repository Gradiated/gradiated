const normalizedWholeAnswer = (value: string): string => {
  let answer = value.trim().replace(/\.$/, "").trim();
  const wrapper = ["**", "__", "`"].find(
    (delimiter) =>
      answer.length > delimiter.length * 2 &&
      answer.startsWith(delimiter) &&
      answer.endsWith(delimiter),
  );
  if (wrapper)
    answer = answer
      .slice(wrapper.length, -wrapper.length)
      .trim()
      .replace(/\.$/, "")
      .trim();

  return answer.toLowerCase();
};

export const matchesWholeAnswer = (
  value: string,
  expected: string,
): boolean => {
  const answer = normalizedWholeAnswer(value);
  const target = expected.trim().toLowerCase();
  if (answer === target) return true;

  return (
    /^\d+$/.test(target) &&
    /^\d{1,3}(,\d{3})+$/.test(answer) &&
    answer.replaceAll(",", "") === target
  );
};
