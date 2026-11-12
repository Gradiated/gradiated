// One radar run: scan each source, keep the models not seen before, send them
// as alerts grouped by lab, then remember everything seen.

import type { Alert, Model, Notifier, Source } from "./model.ts";
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
    const {
      sources,
      watchlist,
      store,
      notifiers,
      log,
      save = true,
    } = this.#options;
    const seen = await store.load();
    // Scopes a failed source would have covered keep their old IDs.
    const next: Seen = { ...seen };
    const alerts: Alert[] = [];
    const failures: RadarResult["failures"] = [];

    for (const source of sources) {
      let scans;
      try {
        scans = await source.scan();
      } catch (error) {
        log(`${source.name}: scan failed: ${(error as Error).message}`);
        failures.push({ source: source.name, error });
        continue;
      }

      const byLab = new Map<string, Model[]>();
      for (const { scope, models } of scans) {
        const before = seen[scope];
        next[scope] = [
          ...new Set([...(before ?? []), ...models.map((m) => m.id)]),
        ];
        if (!before) {
          // A new org or prefix: record what is already there without alerting.
          const count =
            models.length === 1 ? "1 model" : `${models.length} models`;
          log(
            `${source.name}: started watching ${scope} (${count}, no alerts).`,
          );
          continue;
        }
        const known = new Set(before);
        for (const model of models.filter((m) => !known.has(m.id))) {
          for (const { lab } of watchlist.labsFor(source.name, model)) {
            byLab.set(lab, [...(byLab.get(lab) ?? []), model]);
          }
        }
      }
      for (const [lab, models] of byLab)
        alerts.push({ source: source.name, lab, models });
    }

    log(
      `${alerts.reduce((n, a) => n + a.models.length, 0)} new models in ${alerts.length} alerts.`,
    );
    if (alerts.length) {
      // Before saving: if sending fails, the next run sends these again.
      for (const notifier of notifiers) await notifier.send(alerts);
    }
    if (save) await store.save(next);
    return { alerts, failures };
  }
}
