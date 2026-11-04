export type ReportRow = Record<string, string | number | null>;

const cell = (value: string): string | number | null => {
  const trimmed = value.trim();
  if (trimmed === "") return null;

  const number = Number(trimmed);
  return Number.isFinite(number) && /^-?[\d.,e+-]+$/i.test(trimmed)
    ? number
    : value;
};

// RFC 4180: quoted fields may contain commas, quotes ("") and newlines.
const parseCsv = (text: string): ReportRow[] => {
  const records: string[][] = [];
  let record: string[] = [];
  let field = "";
  let quoted = false;

  for (let index = 0; index < text.length; index++) {
    const char = text[index];
    if (quoted) {
      if (char === '"' && text[index + 1] === '"') {
        field += '"';
        index++;
      } else if (char === '"') quoted = false;
      else field += char;
    } else if (char === '"') quoted = true;
    else if (char === ",") {
      record.push(field);
      field = "";
    } else if (char === "\n" || char === "\r") {
      if (char === "\r" && text[index + 1] === "\n") index++;
      record.push(field);
      records.push(record);
      record = [];
      field = "";
    } else field += char;
  }
  if (field !== "" || record.length) {
    record.push(field);
    records.push(record);
  }

  const [header, ...rows] = records.filter((row) =>
    row.some((value) => value.trim() !== ""),
  );
  if (!header) return [];

  return rows.map((row) =>
    Object.fromEntries(
      header.map((name, column) => [name.trim(), cell(row[column] ?? "")]),
    ),
  );
};

const objectRows = (value: unknown): ReportRow[] => {
  if (!Array.isArray(value)) throw new Error("Expected an array of objects.");

  return value.map((item) => {
    if (!item || typeof item !== "object" || Array.isArray(item))
      throw new Error("Expected an array of objects.");

    return Object.fromEntries(
      Object.entries(item).map(([key, entry]) => [
        key,
        typeof entry === "number" || typeof entry === "string"
          ? entry
          : entry === null || entry === undefined
            ? null
            : JSON.stringify(entry),
      ]),
    );
  });
};

export const parseReportData = (name: string, text: string): ReportRow[] => {
  if (/\.csv$/i.test(name)) return parseCsv(text);
  if (/\.jsonl$/i.test(name))
    return objectRows(
      text
        .split("\n")
        .filter((line) => line.trim())
        .map((line) => JSON.parse(line) as unknown),
    );
  if (/\.json$/i.test(name)) return objectRows(JSON.parse(text) as unknown);

  throw new Error("Report data must be a .csv, .json or .jsonl file.");
};
