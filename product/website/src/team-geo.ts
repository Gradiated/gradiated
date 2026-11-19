/* Turning the "city" and "country" a person writes into a flag and a pin.
   The flag's code is worked out here from the country's name; the pin's
   coordinates are looked up once by scripts/sync-team-places.ts and kept in
   src/team-places.generated.json. */

const ALIASES: Record<string, string> = {
  uk: "GB",
  "great britain": "GB",
  britain: "GB",
  england: "GB",
  scotland: "GB",
  wales: "GB",
  "northern ireland": "GB",
  us: "US",
  usa: "US",
  america: "US",
  uae: "AE",
  holland: "NL",
  "south korea": "KR",
  korea: "KR",
  russia: "RU",
  turkey: "TR",
  "czech republic": "CZ",
};

const tidy = (value: string): string =>
  value
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[.]/g, "")
    .replace(/^the\s+/i, "")
    .trim()
    .toLowerCase();

let byName: Map<string, string> | undefined;

const names = (): Map<string, string> => {
  if (byName) return byName;

  byName = new Map();
  const english = new Intl.DisplayNames(["en"], { type: "region" });
  for (let a = 65; a <= 90; a += 1) {
    for (let b = 65; b <= 90; b += 1) {
      const code = String.fromCharCode(a, b);
      const name = english.of(code);
      // An unassigned code comes back as itself.
      if (name && name !== code) byName.set(tidy(name), code);
    }
  }

  return byName;
};

/** "UK" -> "GB", "India" -> "IN". Undefined when the name is not a country. */
export const countryCodeOf = (country: string): string | undefined => {
  const name = tidy(country);
  if (/^[a-z]{2}$/.test(name) && !ALIASES[name]) {
    const code = name.toUpperCase();
    if ([...names().values()].includes(code)) return code;
  }

  return ALIASES[name] ?? names().get(name);
};

/** What a city is filed under in team-places.generated.json. */
export const placeKey = (city: string, country: string): string =>
  `${city.trim()}, ${country.trim()}`;

export type PlaceCoordinates = { latitude: number; longitude: number };
