// The labs the radar follows, read from watchlist.json. See README.md for how
// to add one.

import type { Model, SourceName } from "./model.ts";

export type Lab = {
  /** The name shown in alerts, e.g. "Moonshot AI". */
  lab: string;
  /** Hugging Face orgs, as in huggingface.co/<org>. */
  huggingface: string[];
  /** OpenRouter model ID prefixes, as in openrouter.ai/<prefix>/<model>. */
  openrouter: string[];
  /** If set, only models whose ID contains one of these words (any case). */
  include: string[];
};

const FIELDS = new Set(["lab", "huggingface", "openrouter", "include"]);

export class Watchlist {
  readonly labs: readonly Lab[];

  constructor(labs: Lab[]) {
    this.labs = labs;
  }

  /** Reads and checks watchlist.json. Errors name the entry at fault. */
  static parse(json: unknown): Watchlist {
    if (!Array.isArray(json)) {
      throw new Error("The watch list must be a list of labs.");
    }
    const labs = json.map(parseLab);
    const names = new Set<string>();
    for (const { lab } of labs) {
      if (names.has(lab)) throw new Error(`"${lab}" is listed twice.`);
      names.add(lab);
    }
    return new Watchlist(labs);
  }

  /** The orgs or prefixes to scan on a source, each once. */
  owners(source: SourceName): string[] {
    return [...new Set(this.labs.flatMap((lab) => this.#owners(lab, source)))];
  }

  /** The labs a model belongs to: listed under one of their owners and matching their filter. */
  labsFor(source: SourceName, model: Model): Lab[] {
    const id = model.id.toLowerCase();
    return this.labs.filter(
      (lab) =>
        this.#owners(lab, source).includes(model.owner) &&
        (!lab.include.length || lab.include.some((word) => id.includes(word))),
    );
  }

  #owners(lab: Lab, source: SourceName): string[] {
    return source === "Hugging Face" ? lab.huggingface : lab.openrouter;
  }
}

/** One watch-list entry, checked. Entries are numbered from 1 in errors. */
const parseLab = (entry: unknown, index: number): Lab => {
  if (typeof entry !== "object" || entry === null || Array.isArray(entry)) {
    throw new Error(`Entry ${index + 1} must be an object.`);
  }
  const fields = entry as Record<string, unknown>;
  const { lab } = fields;
  if (typeof lab !== "string" || !lab.trim()) {
    throw new Error(`Entry ${index + 1} needs a "lab" name.`);
  }
  const unknown = Object.keys(fields).find((key) => !FIELDS.has(key));
  if (unknown) throw new Error(`${lab}: unknown field "${unknown}".`);

  const parsed: Lab = {
    lab,
    huggingface: nameList(fields.huggingface, `${lab}: "huggingface"`),
    // OpenRouter IDs and the include words are matched without regard to case.
    openrouter: nameList(fields.openrouter, `${lab}: "openrouter"`).map(
      (name) => name.toLowerCase(),
    ),
    include: nameList(fields.include, `${lab}: "include"`).map((word) =>
      word.toLowerCase(),
    ),
  };
  if (!parsed.huggingface.length && !parsed.openrouter.length) {
    throw new Error(
      `${lab}: list at least one "huggingface" org or "openrouter" prefix.`,
    );
  }
  return parsed;
};

/** A list of non-empty names with no spaces around them, or [] when left out. */
const nameList = (value: unknown, field: string): string[] => {
  if (value === undefined) return [];
  const valid =
    Array.isArray(value) &&
    value.every(
      (item) => typeof item === "string" && item && item.trim() === item,
    );
  if (!valid) throw new Error(`${field} must be a list of non-empty names.`);
  return value as string[];
};
