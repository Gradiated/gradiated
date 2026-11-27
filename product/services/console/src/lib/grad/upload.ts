import { sha256 } from "@noble/hashes/sha2.js";
import { bytesToHex } from "@noble/hashes/utils.js";

export const MAX_IMPORT_BYTES = 5 * 1024 ** 3;

export const IMPORT_FILE_TYPES = ".jsonl,.json,.parquet,.gz";

// Streams the file through the hash: Web Crypto would need the whole file
// (up to 5 GiB) in memory at once.
export const sha256Hex = async (file: Blob) => {
  const hash = sha256.create();
  const reader = file.stream().getReader();

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    hash.update(value);
  }

  return bytesToHex(hash.digest());
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
