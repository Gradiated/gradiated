import { parse } from "yaml";
import { z } from "zod";
import { countryCodeOf, placeKey } from "./team-geo";
import type { PlaceCoordinates } from "./team-geo";
import { mediaName } from "./team-media";
import type { TeamMedia, TeamPicture, TeamPortrait } from "./team-media";

/* One folder per person in content/team/, holding their profile and their
   images. The folder's name is the profile's URL (/team/<folder>/); the front
   matter is validated here so a typo fails the build with the file's name
   instead of shipping a broken page. content/team/README.md is the guide
   people edit from. */

const url = z.string().regex(/^https:\/\/\S+$/, "Use a full https:// link");

const schema = z
  .object({
    name: z.string().trim().min(1),
    role: z.string().trim().min(1),
    /** One or two sentences, shown on cards and at the top of the profile. */
    summary: z.string().trim().min(1).optional(),
    /**
     * Where the person is based, to the city. Leave out to stay off the map.
     * City and country are all that is needed: the flag and the pin are
     * worked out from them. The other three override that when it is wrong.
     */
    location: z
      .object({
        city: z.string().trim().min(1),
        /** As it should read on the page: "UK", "India". */
        country: z.string().trim().min(1),
        countryCode: z
          .string()
          .regex(/^[A-Z]{2}$/)
          .optional(),
        latitude: z.number().min(-90).max(90).optional(),
        longitude: z.number().min(-180).max(180).optional(),
      })
      .strict()
      .refine(
        (value) =>
          (value.latitude === undefined) === (value.longitude === undefined),
        "Give latitude and longitude together, or neither",
      )
      .optional(),
    /**
     * Captions for gallery pictures, by file name. The pictures themselves
     * are whatever is in images/gallery/; nothing is listed here to make one
     * appear.
     */
    captions: z.record(z.string(), z.string().trim().min(1)).default({}),
    links: z
      .object({
        github: url.optional(),
        linkedin: url.optional(),
        x: url.optional(),
        website: url.optional(),
      })
      .strict()
      .default({}),
    /** Position in the directory. People without one follow, by name. */
    order: z.number().int().positive().optional(),
  })
  .strict();

export type TeamMember = z.infer<typeof schema> & {
  /** The Markdown under the front matter: the person's own words. */
  body: string;
  /** The pictures in the person's images/gallery/ folder. */
  gallery: Array<TeamPicture & { caption?: string; name: string }>;
  path: string;
  /** The picture in images/profile/, once they have added one. */
  photo?: TeamPortrait;
  slug: string;
};

/* A person is a folder: content/team/ada-lovelace/ holds their profile (the
   one Markdown file in it) and their images. The folder's name is the URL. */
const slugOf = (file: string): string => {
  const slug = file.split("/").at(-2) ?? "";
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug))
    throw new Error(
      `${file}: name the folder in lowercase with hyphens, like ada-lovelace/`,
    );

  return slug;
};

export const parseTeamMember = (source: string, file: string): TeamMember => {
  const match = source.match(/^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/);
  if (!match) throw new Error(`${file}: profile YAML front matter is required`);
  const slug = slugOf(file);

  try {
    return {
      ...schema.parse(parse(match[1])),
      body: source.slice(match[0].length).trim(),
      gallery: [],
      path: `/team/${slug}/`,
      slug,
    };
  } catch (error) {
    throw new Error(`${file}: invalid profile front matter`, { cause: error });
  }
};

/** Fills in the flag's code and the pin's coordinates a profile left out. */
const located = (
  member: TeamMember,
  places: Record<string, PlaceCoordinates>,
): TeamMember => {
  const { location } = member;
  if (!location) return member;
  const found = places[placeKey(location.city, location.country)];

  return {
    ...member,
    location: {
      ...location,
      countryCode: location.countryCode ?? countryCodeOf(location.country),
      latitude: location.latitude ?? found?.latitude,
      longitude: location.longitude ?? found?.longitude,
    },
  };
};

/** Attaches the person's portrait and gallery from their images folder. */
const pictured = (member: TeamMember, media: TeamMedia): TeamMember => {
  const images = media[member.slug];
  if (!images) return member;

  const captions = new Map(
    Object.entries(member.captions).map(([file, caption]) => [
      mediaName(file),
      caption,
    ]),
  );

  return {
    ...member,
    gallery: Object.entries(images.gallery).map(([name, picture]) => ({
      ...picture,
      caption: captions.get(name),
      name,
    })),
    photo: images.profile,
  };
};

export const buildTeam = (
  sources: Record<string, string>,
  places: Record<string, PlaceCoordinates> = {},
  media: TeamMedia = {},
): TeamMember[] => {
  const names = new Set<string>();
  const slugs = new Set<string>();

  return (
    Object.entries(sources)
      // The template folder (_template/) is not a person.
      .filter(([file]) => !/\/_[^/]*\/[^/]+$/.test(file))
      .map(([file, source]) => {
        const member = parseTeamMember(source, file);
        if (slugs.has(member.slug))
          throw new Error(
            `${file}: keep one Markdown file in each person's folder`,
          );
        slugs.add(member.slug);
        if (names.has(member.name))
          throw new Error(
            `${file}: another profile is already "${member.name}"`,
          );
        names.add(member.name);

        return pictured(located(member, places), media);
      })
      .sort(
        (a, b) =>
          (a.order ?? Infinity) - (b.order ?? Infinity) ||
          a.name.localeCompare(b.name),
      )
  );
};

export type TeamPlace = {
  city: string;
  country: string;
  key: string;
  latitude: number;
  longitude: number;
  members: TeamMember[];
};

/** People grouped by the city they are based in, largest group first. */
export const placesOf = (members: TeamMember[]): TeamPlace[] => {
  const places = new Map<string, TeamPlace>();

  for (const member of members) {
    if (!member.location) continue;
    const { city, country, latitude, longitude } = member.location;
    // No coordinates yet: on the page, but not on the map.
    if (latitude === undefined || longitude === undefined) continue;
    const key = placeKey(city, country);
    const place = places.get(key);
    if (place) place.members.push(member);
    else
      places.set(key, {
        city,
        country,
        key,
        latitude,
        longitude,
        members: [member],
      });
  }

  return [...places.values()].sort(
    (a, b) => b.members.length - a.members.length || a.key.localeCompare(b.key),
  );
};

export type ProfileSection = {
  id: string;
  markdown: string;
  title: string;
};

const idOf = (title: string): string =>
  title
    .toLowerCase()
    .replace(/['’]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");

/**
 * A profile's sections are the `##` headings its author wrote: the page's
 * contents list and its layout both come from the file, so adding a section
 * is adding a heading. Anything above the first heading is the bio.
 */
export const sectionsOf = (
  body: string,
  /** Titles (lowercase) to keep even when empty: the page fills them in, and
   *  their place in the file is their place on the page. */
  keepEmpty: string[] = [],
): ProfileSection[] => {
  const sections: ProfileSection[] = [];
  let current: { lines: string[]; title: string } = {
    lines: [],
    title: "Bio",
  };
  let fenced = false;
  const close = () => {
    const markdown = current.lines.join("\n").trim();
    if (!markdown && !keepEmpty.includes(current.title.toLowerCase())) return;
    const base = idOf(current.title) || "section";
    const taken = sections.filter((section) =>
      section.id.startsWith(base),
    ).length;
    sections.push({
      id: taken ? `${base}-${taken + 1}` : base,
      markdown,
      title: current.title,
    });
  };

  // Comments are the template's hints to the author, never content: a
  // heading with only a hint under it is still an empty section.
  const text = body.replace(/<!--[\s\S]*?-->/g, "");

  for (const line of text.split(/\r?\n/)) {
    if (/^(?:```|~~~)/.test(line)) fenced = !fenced;
    const heading = fenced ? null : /^##\s+(.+?)\s*#*$/.exec(line);
    if (heading) {
      close();
      current = { lines: [], title: heading[1] };
    } else current.lines.push(line);
  }
  close();

  return sections;
};

export type ExternalPost = { note?: string; title: string; url: string };

/**
 * The writing a person lists under their Posts heading, as a Markdown list of
 * links:
 *
 *   - [Title](https://example.com/post) — an optional note
 *
 * Each such line becomes a post. Anything else under the heading is returned
 * as `rest` and shown as ordinary text.
 */
export const postsIn = (
  markdown: string,
): { posts: ExternalPost[]; rest: string } => {
  const posts: ExternalPost[] = [];
  const rest: string[] = [];

  for (const line of markdown.split(/\r?\n/)) {
    const item = /^\s*[-*+]\s+\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)(.*)$/.exec(
      line,
    );
    if (!item) {
      rest.push(line);
      continue;
    }

    const note = item[3].replace(/^[\s—–:,.-]+/, "").trim();
    posts.push({
      title: item[1].trim(),
      url: item[2],
      note: note || undefined,
    });
  }

  return { posts, rest: rest.join("\n").trim() };
};
