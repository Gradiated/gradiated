const MAX_ROWS = 10_000;
const MAX_COLUMNS = 100;

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
  let closedQuote = false;

  for (let index = 0; index < text.length; index++) {
    const char = text[index];
    if (quoted) {
      if (char === '"' && text[index + 1] === '"') {
        field += '"';
        index++;
      } else if (char === '"') {
        quoted = false;
        closedQuote = true;
      } else field += char;
    } else if (char === '"') {
      if (field !== "" || closedQuote) throw new Error("Invalid CSV quoting.");
      quoted = true;
    } else if (char === ",") {
      record.push(field);
      field = "";
      closedQuote = false;
    } else if (char === "\n" || char === "\r") {
      if (char === "\r" && text[index + 1] === "\n") index++;
      record.push(field);
      records.push(record);
      record = [];
      field = "";
      closedQuote = false;
    } else {
      if (closedQuote) throw new Error("Invalid CSV quoting.");
      field += char;
    }
  }
  if (quoted) throw new Error("Unterminated CSV field.");

  if (field !== "" || record.length || closedQuote) {
    record.push(field);
    records.push(record);
  }

  const [header, ...rows] = records.filter((row) =>
    row.some((value) => value.trim() !== ""),
  );
  if (!header) return [];

  const names = header.map((name, index) =>
    (index === 0 ? name.replace(/^\uFEFF/, "") : name).trim(),
  );
  if (names.some((name) => !name) || new Set(names).size !== names.length)
    throw new Error("CSV headers must be nonempty and unique.");

  return rows.map((row) => {
    if (row.length !== names.length)
      throw new Error("CSV row does not match its headers.");

    return Object.fromEntries(
      names.map((name, column) => [name, cell(row[column]!)]),
    );
  });
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
  let rows: ReportRow[];
  if (/\.csv$/i.test(name)) rows = parseCsv(text);
  else if (/\.jsonl$/i.test(name))
    rows = objectRows(
      text
        .split("\n")
        .filter((line) => line.trim())
        .map((line) => JSON.parse(line) as unknown),
    );
  else if (/\.json$/i.test(name))
    rows = objectRows(JSON.parse(text) as unknown);
  else throw new Error("Report data must be a .csv, .json or .jsonl file.");

  if (
    rows.length > MAX_ROWS ||
    rows.some((row) => Object.keys(row).length > MAX_COLUMNS)
  )
    throw new Error("Report data is limited to 10,000 rows and 100 columns.");

  return rows;
};
