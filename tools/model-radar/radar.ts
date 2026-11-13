// One radar run: scan each source, keep the models not seen before, send them
// as alerts grouped by lab, then remember everything seen.

import type { Alert, Model, Notifier, Scan, Source } from "./model.ts";
import type { Seen, SeenStore } from "./seen-store.ts";
import type { Watchlist } from "./watchlist.ts";

export type RadarOptions = {
  sources: Source[];
  watchlist: Watchlist;
  store: SeenStore;
  notifiers: Notifier[];
  log: (line: string) => void;
  /** Whether to save what was seen. Dry runs don't. Defaults to true. */
  save?: boolean;
};

export type RadarResult = {
  alerts: Alert[];
  /** Sources whose scan failed; the others still ran. */
  failures: { source: string; error: unknown }[];
};

export class Radar {
  readonly #options: RadarOptions;

  constructor(options: RadarOptions) {
    this.#options = options;
  }

  async run(): Promise<RadarResult> {
    const { sources, store, notifiers, log, save = true } = this.#options;
    const seen = await store.load();
    // Starts as a copy, so a source that fails keeps the IDs it had.
    const next: Seen = { ...seen };
    const alerts: Alert[] = [];
    const failures: RadarResult["failures"] = [];

    for (const source of sources) {
      let scans: Scan[];
      try {
        scans = await source.scan();
      } catch (error) {
        log(`${source.name}: scan failed: ${(error as Error).message}`);
        failures.push({ source: source.name, error });
        continue;
      }
      const unseen = this.#unseen(source, scans, seen, next);
      const watched = unseen.filter(
        (model) => this.#labs(source, model).length,
      );
      const described = await this.#describe(source, watched);
      alerts.push(...this.#groupByLab(source, described));
    }

    const count = alerts.reduce((sum, alert) => sum + alert.models.length, 0);
    log(`${count} new models in ${alerts.length} alerts.`);
    // Send before saving: if sending fails, the next run sends these again.
    if (alerts.length) {
      for (const notifier of notifiers) await notifier.send(alerts);
    }
    if (save) await store.save(next);
    return { alerts, failures };
  }

  /**
   * The models in these scans that weren't seen before, recording every ID in
   * `next`. An org or prefix seen for the first time is only recorded, so
   * adding a lab doesn't post everything it has ever published.
   */
  #unseen(source: Source, scans: Scan[], seen: Seen, next: Seen): Model[] {
    const unseen: Model[] = [];
    for (const { scope, models } of scans) {
      const before = seen[scope];
      const ids = models.map((model) => model.id);
      next[scope] = [...new Set([...(before ?? []), ...ids])];
      if (!before) {
        const count =
          models.length === 1 ? "1 model" : `${models.length} models`;
        this.#options.log(
          `${source.name}: started watching ${scope} (${count}, no alerts).`,
        );
        continue;
      }
      const known = new Set(before);
      unseen.push(...models.filter((model) => !known.has(model.id)));
    }
    return unseen;
  }

  /** The source's extra details for these models, or the models as they are if that fails. */
  async #describe(source: Source, models: Model[]): Promise<Model[]> {
    if (!source.describe || !models.length) return models;
    try {
      return await source.describe(models);
    } catch (error) {
      this.#options.log(
        `${source.name}: could not add details: ${(error as Error).message}`,
      );
      return models;
    }
  }

  /** One alert per lab, listing that lab's new models. */
  #groupByLab(source: Source, models: Model[]): Alert[] {
    const byLab = new Map<string, Model[]>();
    for (const model of models) {
      for (const { lab } of this.#labs(source, model)) {
        byLab.set(lab, [...(byLab.get(lab) ?? []), model]);
      }
    }
    return [...byLab].map(([lab, labModels]) => ({
      source: source.name,
      lab,
      models: labModels,
    }));
  }

  /** The watch-list labs a model belongs to (none if a lab's filter leaves it out). */
  #labs(source: Source, model: Model) {
    return this.#options.watchlist.labsFor(source.name, model);
  }
}
