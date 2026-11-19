// Runs at the start of `pnpm build` and when the dev server starts (plain
// `node`, using its built-in type stripping).
//
// A profile in content/team/ gives a city and a country. This looks up each
// city's coordinates once, with Open-Meteo's geocoding API (public, no key),
// and keeps them in src/team-places.generated.json, which is committed. A
// build therefore only needs the network for a city nobody has listed before.
//
// Only the city and country are sent, never a person's name.
//
// A city that cannot be found fails the build and names the file, because it
// is almost always a typo. To place somewhere the lookup gets wrong, give
// `latitude` and `longitude` in the profile; those are used as written.

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

type Wanted = { city: string; country: string; file: string; key: string };

const wanted = async (): Promise<Wanted[]> => {
  const places: Wanted[] = [];

  for (const profile of await profiles()) {
    const location = profile.front.location as
      { city?: unknown; country?: unknown; latitude?: unknown } | undefined;
    if (!location?.city || !location?.country) continue;
    // Coordinates written in the profile are used as they are.
    if (location.latitude !== undefined) continue;

    const key = placeKey(String(location.city), String(location.country));
    if (places.some((place) => place.key === key)) continue;

    places.push({
      city: String(location.city).trim(),
      country: String(location.country).trim(),
      file: profile.label,
      key,
    });
  }

  return places;
};

const lookUp = async (place: Wanted): Promise<PlaceCoordinates> => {
  const code = countryCodeOf(place.country);
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
    if (known[place.key]) {
      next[place.key] = known[place.key];
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
