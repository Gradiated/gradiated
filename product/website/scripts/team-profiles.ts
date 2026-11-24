// The profiles in content/team/, for the sync scripts. Each person is a
// folder; their profile is the one Markdown file in it.

import { readFile, readdir } from "node:fs/promises";
import { parse } from "yaml";

export const TEAM = new URL("../content/team/", import.meta.url);

export type ProfileFile = {
  /** The folder, with a trailing slash. */
  folder: URL;
  front: Record<string, unknown>;
  /** "content/team/ada-lovelace/ada-lovelace.md", for messages. */
  label: string;
  slug: string;
};

export const profiles = async (): Promise<ProfileFile[]> => {
  const found: ProfileFile[] = [];
  const entries = await readdir(TEAM, { withFileTypes: true });

  for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
    // _template is the folder people copy, not a person.
    if (!entry.isDirectory() || /^[_.]/.test(entry.name)) continue;

    const folder = new URL(`${entry.name}/`, TEAM);
    const [file] = (await readdir(folder)).filter((name) => /\.md$/.test(name));
    if (!file) continue;

    const source = await readFile(new URL(file, folder), "utf8");
    const match = source.match(/^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/);

    found.push({
      folder,
      front: (match ? parse(match[1]) : {}) ?? {},
      label: `content/team/${entry.name}/${file}`,
      slug: entry.name,
    });
  }

  return found;
};
