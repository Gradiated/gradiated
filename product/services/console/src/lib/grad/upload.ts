export const MAX_IMPORT_BYTES = 5 * 1024 ** 3;

export const IMPORT_FILE_TYPES = ".jsonl,.json,.parquet,.gz";

export const sha256Hex = async (file: Blob) => {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    await file.arrayBuffer(),
  );

  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
};

// Browsers set Content-Length from the body and refuse to send it themselves.
const BROWSER_SET_HEADERS = new Set(["content-length", "host"]);

export const uploadHeaders = (headers: Record<string, string>) =>
  Object.fromEntries(
    Object.entries(headers).filter(
      ([name]) => !BROWSER_SET_HEADERS.has(name.toLowerCase()),
    ),
  );

export const uploadTarget = (url: string, apiBaseUrl: string) =>
  new URL(url, `${apiBaseUrl.replace(/\/+$/, "")}/`).toString();

export const datasetNameFromFile = (fileName: string) =>
  fileName
    .toLowerCase()
    .replace(/(\.jsonl|\.json|\.parquet)?(\.gz)?$/, "")
    .replace(/[^a-z0-9._-]+/g, "-")
    .replace(/^[^a-z0-9]+/, "")
    .slice(0, 64) || "dataset";

export const DATASET_NAME_PATTERN = /^[a-z0-9][a-z0-9._-]{0,63}$/;
