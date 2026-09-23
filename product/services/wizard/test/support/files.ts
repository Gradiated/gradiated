import { mkdir, readdir, readFile, writeFile } from "node:fs/promises";
import { dirname } from "node:path";

export const seed = async (path: string, content: string): Promise<void> => {
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, content);
};

export const readJson = async (path: string): Promise<unknown> =>
  JSON.parse(await readFile(path, "utf8"));

export const listBackups = async (directory: string): Promise<string[]> => {
  const entries = await readdir(directory).catch(() => []);

  return entries.filter((entry) => entry.includes(".bak."));
};
