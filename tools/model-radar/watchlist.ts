// The labs the radar follows, read from watchlist.json. See README.md for how
// to add one.

import type { Model, SourceName } from "./model.ts";

export type Lab = {
  lab: string;
  /** Hugging Face orgs, as in huggingface.co/<org>. */
  huggingface: string[];
  /** OpenRouter model ID prefixes, as in openrouter.ai/<prefix>/<model>. */
  openrouter: string[];
  /** If set, only models whose ID contains one of these words (any case). */
  include: string[];
};

const KEYS = new Set(["lab", "huggingface", "openrouter", "include"]);

const strings = (value: unknown, where: string): string[] => {
  if (value === undefined) return [];
  if (
    !Array.isArray(value) ||
    !value.every(
      (item) => typeof item === "string" && item.trim() === item && item,
    )
  ) {
    throw new Error(`${where} must be a list of non-empty names.`);
  }
  return value;
};

export class Watchlist {
  readonly labs: readonly Lab[];

  constructor(labs: Lab[]) {
    this.labs = labs;
  }

  /** Parses and checks watchlist.json, naming the entry at fault. */
  static parse(json: unknown): Watchlist {
    if (!Array.isArray(json))
      throw new Error("The watch list must be a list of labs.");
    const names = new Set<string>();
    const labs = json.map((entry: unknown, index): Lab => {
      if (typeof entry !== "object" || entry === null || Array.isArray(entry)) {
        throw new Error(`Entry ${index + 1} must be an object.`);
      }
      const fields = entry as Record<string, unknown>;
      const { lab } = fields;
      if (typeof lab !== "string" || !lab.trim()) {
        throw new Error(`Entry ${index + 1} needs a "lab" name.`);
      }
      if (names.has(lab)) throw new Error(`"${lab}" is listed twice.`);
      names.add(lab);
      const unknown = Object.keys(fields).filter((key) => !KEYS.has(key));
      if (unknown.length)
        throw new Error(`${lab}: unknown field "${unknown[0]}".`);
      const parsed = {
        lab,
        huggingface: strings(fields.huggingface, `${lab}: "huggingface"`),
        openrouter: strings(fields.openrouter, `${lab}: "openrouter"`).map(
          (p) => p.toLowerCase(),
        ),
        include: strings(fields.include, `${lab}: "include"`).map((w) =>
          w.toLowerCase(),
        ),
      };
      if (!parsed.huggingface.length && !parsed.openrouter.length) {
        throw new Error(
          `${lab}: list at least one "huggingface" org or "openrouter" prefix.`,
        );
      }
      return parsed;
    });
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
