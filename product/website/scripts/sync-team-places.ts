// Coordinates are cached in src/team-places.generated.json, so a build only
// needs the network for a new city. Only city and country are sent.

import { readFile, writeFile } from "node:fs/promises";
import { profiles } from "./team-profiles.ts";
import { countryCodeOf, placeKey } from "../src/team-geo.ts";
import type { PlaceCoordinates } from "../src/team-geo.ts";

declare const process: {
  env: Record<string, string | undefined>;
  exit(code: number): never;
};

const OUTPUT = new URL("../src/team-places.generated.json", import.meta.url);
const OPTIONAL = process.env.TEAM_PLACES_OPTIONAL === "1";

type Wanted = {
  city: string;
  country: string;
  /** The profile's own `countryCode`, which wins over the name. */
  countryCode?: string;
  file: string;
  key: string;
};

const wanted = async (): Promise<Wanted[]> => {
  const places: Wanted[] = [];

  for (const profile of await profiles()) {
    const location = profile.front.location as
      | {
          city?: unknown;
          country?: unknown;
          countryCode?: unknown;
          latitude?: unknown;
        }
      | undefined;
    if (!location?.city || !location?.country) continue;
    // Coordinates written in the profile are used as they are.
    if (location.latitude !== undefined) continue;

    const key = placeKey(String(location.city), String(location.country));
    if (places.some((place) => place.key === key)) continue;

    places.push({
      city: String(location.city).trim(),
      country: String(location.country).trim(),
      ...(typeof location.countryCode === "string" &&
      location.countryCode.trim()
        ? { countryCode: location.countryCode.trim().toUpperCase() }
        : {}),
      file: profile.label,
      key,
    });
  }

  return places;
};

const lookUp = async (place: Wanted): Promise<PlaceCoordinates> => {
  const code = place.countryCode ?? countryCodeOf(place.country);
  if (!code) {
    throw new Error(
      `${place.file}: "${place.country}" is not a country name this recognises. Add its two-letter code as \`countryCode\`.`,
    );
  }

  const url = new URL("https://geocoding-api.open-meteo.com/v1/search");
  url.search = new URLSearchParams({
    name: place.city,
    count: "20",
    language: "en",
    format: "json",
    countryCode: code,
  }).toString();

  const response = await fetch(url, { signal: AbortSignal.timeout(8000) });
  if (!response.ok) throw new Error(`Geocoding answered ${response.status}`);

  const body = (await response.json()) as {
    results?: Array<{
      country_code?: string;
      latitude: number;
      longitude: number;
      population?: number;
    }>;
  };
  // Of the places with this name in this country, the largest.
  const [best] = (body.results ?? [])
    .filter((result) => result.country_code === code)
    .sort((a, b) => (b.population ?? 0) - (a.population ?? 0));
  if (!best) {
    throw new Error(
      `${place.file}: no city called "${place.city}" was found in ${place.country}. Check the spelling, or give \`latitude\` and \`longitude\` in the profile.`,
    );
  }

  return {
    countryCode: code,
    latitude: Number(best.latitude.toFixed(4)),
    longitude: Number(best.longitude.toFixed(4)),
  };
};

const main = async (): Promise<void> => {
  const known = JSON.parse(await readFile(OUTPUT, "utf8")) as Record<
    string,
    PlaceCoordinates
  >;
  const places = await wanted();
  const next: Record<string, PlaceCoordinates> = {};
  const failures: string[] = [];

  for (const place of places) {
    // Reused only if it was found in the country now asked for: correcting
    // just a profile's countryCode must move its pin.
    const code = place.countryCode ?? countryCodeOf(place.country);
    const cached = known[place.key];
    if (
      cached &&
      (cached.countryCode ?? countryCodeOf(place.country)) === code
    ) {
      next[place.key] = cached;
      continue;
    }

    try {
      next[place.key] = await lookUp(place);
      console.log(`Placed ${place.key}.`);
    } catch (error) {
      failures.push(error instanceof Error ? error.message : String(error));
    }
  }

  const sorted = Object.fromEntries(
    Object.entries(next).sort(([a], [b]) => a.localeCompare(b)),
  );
  const output = `${JSON.stringify(sorted, null, 2)}\n`;
  if (output !== `${JSON.stringify(known, null, 2)}\n`) {
    await writeFile(OUTPUT, output);
  }

  if (failures.length === 0) return;

  const message = `Team places: ${failures.join("\n")}`;
  if (OPTIONAL) {
    console.warn(`${message}\nThose people are left off the map for now.`);
    return;
  }

  console.error(message);
  process.exit(1);
};

await main();
