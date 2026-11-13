const MAX_ROWS = 10_000;
const MAX_COLUMNS = 100;
const limitError = () =>
  new Error("Report data is limited to 10,000 rows and 100 columns.");

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
  const rows: ReportRow[] = [];
  let names: string[] | undefined;
  let record: string[] = [];
  let field = "";
  let quoted = false;
  let closedQuote = false;

  const pushField = () => {
    if (record.length >= MAX_COLUMNS) throw limitError();

    record.push(field);
    field = "";
    closedQuote = false;
  };
  const finishRecord = () => {
    if (!record.length && !field.trim()) {
      field = "";
      closedQuote = false;
      return;
    }

    pushField();
    if (record.some((value) => value.trim() !== "")) {
      if (!names) {
        names = record.map((name, column) =>
          (column === 0 ? name.replace(/^\uFEFF/, "") : name).trim(),
        );
        if (names.some((name) => !name) || new Set(names).size !== names.length)
          throw new Error("CSV headers must be nonempty and unique.");
      } else {
        if (rows.length >= MAX_ROWS) throw limitError();
        if (record.length !== names.length)
          throw new Error("CSV row does not match its headers.");

        rows.push(
          Object.fromEntries(
            names.map((name, column) => [name, cell(record[column]!)]),
          ),
        );
      }
    }
    record = [];
  };

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
      pushField();
    } else if (char === "\n" || char === "\r") {
      if (char === "\r" && text[index + 1] === "\n") index++;
      finishRecord();
    } else {
      if (closedQuote) throw new Error("Invalid CSV quoting.");
      field += char;
    }
  }
  if (quoted) throw new Error("Unterminated CSV field.");

  if (field !== "" || record.length || closedQuote) finishRecord();

  return rows;
};

const objectRows = (value: unknown): ReportRow[] => {
  if (!Array.isArray(value)) throw new Error("Expected an array of objects.");
  if (value.length > MAX_ROWS) throw limitError();

  return value.map((item) => {
    if (!item || typeof item !== "object" || Array.isArray(item))
      throw new Error("Expected an array of objects.");

    const entries = Object.entries(item);
    if (entries.length > MAX_COLUMNS) throw limitError();

    return Object.fromEntries(
      entries.map(([key, entry]) => [
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

const parseJsonLines = (text: string): ReportRow[] => {
  const values: unknown[] = [];
  for (const [line] of text.matchAll(/[^\n]+/g)) {
    if (!line.trim()) continue;
    if (values.length >= MAX_ROWS) throw limitError();

    values.push(JSON.parse(line) as unknown);
  }

  return objectRows(values);
};

export const parseReportData = (name: string, text: string): ReportRow[] => {
  if (/\.csv$/i.test(name)) return parseCsv(text);
  if (/\.jsonl$/i.test(name)) return parseJsonLines(text);
  if (/\.json$/i.test(name)) return objectRows(JSON.parse(text) as unknown);

  throw new Error("Report data must be a .csv, .json or .jsonl file.");
};
