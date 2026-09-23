import { randomBytes } from "node:crypto";
import {
  chmod,
  copyFile,
  mkdir,
  readFile,
  realpath,
  rename,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import { dirname } from "node:path";
import { WizardError } from "./errors.js";
import { isRecord } from "./guards.js";

export interface BlockMarkers {
  start: string;
  end: string;
}

const isMissingFile = (error: unknown): boolean =>
  error instanceof Error && "code" in error && error.code === "ENOENT";

export const readTextIfExists = async (
  path: string,
): Promise<string | null> => {
  try {
    return await readFile(path, "utf8");
  } catch (error) {
    if (isMissingFile(error)) return null;

    throw new WizardError(`Could not read ${path}.`, { cause: error });
  }
};

export const readJsonObject = async (
  path: string,
): Promise<Record<string, unknown> | null> => {
  const text = await readTextIfExists(path);
  if (text === null) return null;

  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    throw new WizardError(`${path} is not valid JSON. Fix or move it.`, {
      cause: error,
    });
  }

  if (!isRecord(parsed)) {
    throw new WizardError(`${path} does not contain a JSON object.`);
  }

  return parsed;
};

export const formatJson = (value: unknown): string =>
  `${JSON.stringify(value, null, 2)}\n`;

export const backupFile = (path: string): Promise<void> =>
  copyFile(
    path,
    `${path}.bak.${new Date().toISOString().replace(/[-:.]/g, "")}`,
  );

const replaceFile = async (
  path: string,
  content: string,
  mode: number | undefined,
): Promise<void> => {
  const temporary = `${path}.${randomBytes(6).toString("hex")}.tmp`;

  try {
    await writeFile(temporary, content, { mode, flag: "wx" });
    if (mode !== undefined) await chmod(temporary, mode);
    await rename(temporary, path);
  } catch (error) {
    await rm(temporary, { force: true });
    throw error;
  }
};

export interface WriteOptions {
  mode?: number;
  backup?: boolean;
}

// The content goes to a sibling file that already has its final mode and then
// replaces the target, so a failed write never truncates the target and a key
// never sits in a file with looser permissions. Symlinked targets, such as
// dotfiles managed from a repository, are written through to the real file.
export const writeIfChanged = async (
  path: string,
  content: string,
  options: WriteOptions = {},
): Promise<boolean> => {
  const existing = await readTextIfExists(path);
  if (existing === content) return false;

  if (existing === null) {
    await mkdir(dirname(path), { recursive: true });
    await replaceFile(path, content, options.mode);

    return true;
  }

  if (options.backup === true) await backupFile(path);

  const target = await realpath(path);
  const mode = options.mode ?? (await stat(target)).mode & 0o7777;
  await replaceFile(target, content, mode);

  return true;
};

export const hasManagedBlock = (text: string, markers: BlockMarkers): boolean =>
  text.includes(markers.start);

export const removeManagedBlock = (
  text: string,
  markers: BlockMarkers,
): string => {
  const start = text.indexOf(markers.start);
  if (start === -1) return text;

  const end = text.indexOf(markers.end, start);
  if (end === -1) {
    throw new WizardError(
      `Found "${markers.start}" without "${markers.end}". Remove the incomplete Gradiated block and run the wizard again.`,
    );
  }

  let before = text.slice(0, start);
  let after = text.slice(end + markers.end.length);
  if (after.startsWith("\n")) after = after.slice(1);

  if (before.endsWith("\n\n")) {
    before = before.slice(0, -1);
  } else if (before.length === 0 && after.startsWith("\n")) {
    after = after.slice(1);
  }

  return before + after;
};

export const appendManagedBlock = (
  text: string,
  block: string,
  markers: BlockMarkers,
): string => {
  const base = removeManagedBlock(text, markers);
  if (base.length === 0) return `${block}\n`;

  return `${base}${base.endsWith("\n") ? "" : "\n"}\n${block}\n`;
};

export const prependManagedBlock = (
  text: string,
  block: string,
  markers: BlockMarkers,
): string => {
  const base = removeManagedBlock(text, markers);

  return base.length === 0 ? `${block}\n` : `${block}\n\n${base}`;
};
