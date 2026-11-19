// Runs at the start of `pnpm build` and when the dev server starts (plain
// `node`, using its built-in type stripping).
//
// A person's pictures go in their folder, sorted by what they are for:
//
//   content/team/ada-lovelace/ada-lovelace.md
//   content/team/ada-lovelace/images/profile/me.jpg     <- their portrait
//   content/team/ada-lovelace/images/gallery/desk.jpg   <- a gallery picture
//
// People add whatever they have, straight off a phone or camera. This turns
// each file into WebP copies at the sizes the site uses, in
// public/team/<name>/ (generated, not committed), and lists them in
// src/team-media.generated.json for the pages to read.
//
// Resizing drops the file's metadata, so a photograph's embedded location
// and camera details are never published.
//
// A caption that names no file fails the build and names the profile,
// because it is almost always a typo.

import {
  mkdir,
  readFile,
  readdir,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import { fileURLToPath } from "node:url";
import sharp from "sharp";
import { mediaName } from "../src/team-media.ts";
import type { TeamMedia } from "../src/team-media.ts";
import { profiles } from "./team-profiles.ts";

declare const process: {
  exit(code: number): never;
};

const OUTPUT = new URL("../public/team/", import.meta.url);
const MANIFEST = new URL("../src/team-media.generated.json", import.meta.url);

const READABLE = /\.(?:jpe?g|png|webp|avif|tiff?)$/i;
// Formats a phone produces that the resizer cannot open.
const UNREADABLE = /\.(?:heic|heif|gif|bmp|raw|dng)$/i;

/** Longest edge, in pixels. Never enlarges a smaller original. */
const FULL = 2000;
const THUMB = 800;
const SMALL = 96;
/** The profile page's 4:5 portrait. */
const BUST = { height: 750, width: 600 };

const exists = async (url: URL): Promise<boolean> =>
  stat(url).then(
    () => true,
    () => false,
  );

/** True when `output` is missing or older than the picture it is made from. */
const stale = async (source: URL, output: URL): Promise<boolean> => {
  const [from, to] = await Promise.all([
    stat(source),
    stat(output).catch(() => undefined),
  ]);

  return !to || to.mtimeMs < from.mtimeMs;
};

const kept = new Set<string>();

/**
 * Where a seated studio portrait's head is, across the frame: the middle of
 * the dark pixels (hair, mostly) against the bright backdrop, in the band the
 * heads sit in. Searched in the middle of the frame, away from the backdrop's
 * dark edges.
 */
const headCentre = async (image: Buffer): Promise<number> => {
  const { data, info } = await sharp(image)
    .greyscale()
    .resize(400)
    .raw()
    .toBuffer({ resolveWithObject: true });
  const { height, width } = info;
  let total = 0;
  let count = 0;

  for (let y = Math.round(height * 0.12); y < height * 0.24; y++) {
    for (let x = Math.round(width * 0.3); x < width * 0.8; x++) {
      if (data[y * width + x] < 110) {
        total += x;
        count++;
      }
    }
  }

  return count > 200 ? total / count / width : 0.5;
};

/**
 * "inside" keeps the whole picture; "square" and "bust" crop it. A tall
 * portrait is a seated studio shot, so those two crop to the person (head and
 * shoulders for the square, down to the chest for the bust) rather than leave
 * it to the attention crop, which picks the body in black and white.
 */
const resize = async (
  source: URL,
  output: URL,
  shape: "bust" | "inside" | "square",
  edge = 0,
): Promise<void> => {
  kept.add(output.href);
  if (!(await stale(source, output))) return;

  // rotate() with no angle applies the camera's orientation, then forgets it.
  const upright = await sharp(fileURLToPath(source)).rotate().toBuffer();
  const image = sharp(upright);
  const { height = 0, width = 0 } = await image.metadata();

  if (shape !== "inside" && height >= width * 1.2) {
    const cropWidth = Math.round(width * (shape === "square" ? 0.46 : 0.5));
    const centre = (await headCentre(upright)) * width;
    image.extract({
      height: shape === "square" ? cropWidth : Math.round(cropWidth * 1.25),
      left: Math.round(
        Math.min(Math.max(centre - cropWidth / 2, 0), width - cropWidth),
      ),
      top: Math.round(height * (shape === "square" ? 0.08 : 0.06)),
      width: cropWidth,
    });
  }

  const resized =
    shape === "inside"
      ? image.resize(edge, edge, { fit: "inside", withoutEnlargement: true })
      : shape === "square"
        ? image.resize(edge, edge, { fit: "cover", position: "attention" })
        : image.resize(BUST.width, BUST.height, {
            fit: "cover",
            position: "attention",
            withoutEnlargement: true,
          });

  await resized.webp({ quality: 80 }).toFile(fileURLToPath(output));
};

const problems: string[] = [];

/** The pictures in one of a person's image folders, in file-name order. */
const picturesIn = async (
  folder: URL,
  label: string,
): Promise<Array<{ file: string; name: string; source: URL }>> => {
  if (!(await exists(folder))) return [];

  const files = (await readdir(folder)).filter((file) => !file.startsWith("."));
  for (const file of files.filter((name) => UNREADABLE.test(name))) {
    problems.push(
      `${label}${file}: this format cannot be resized. Save it as a JPG or PNG and add that instead.`,
    );
  }

  return files
    .filter((file) => READABLE.test(file))
    .sort((a, b) => a.localeCompare(b, "en", { numeric: true }))
    .map((file) => ({
      file,
      name: mediaName(file),
      source: new URL(encodeURIComponent(file), folder),
    }));
};

const main = async (): Promise<void> => {
  const media: TeamMedia = {};

  for (const profile of await profiles()) {
    const { slug } = profile;
    const images = `content/team/${slug}/images/`;
    const [portraits, gallery] = await Promise.all(
      ["profile", "gallery"].map((kind) =>
        picturesIn(
          new URL(`images/${kind}/`, profile.folder),
          `${images}${kind}/`,
        ),
      ),
    );
    if (portraits.length + gallery.length === 0) continue;

    const out = new URL(`${slug}/`, OUTPUT);
    await mkdir(out, { recursive: true });
    const entry: TeamMedia[string] = { gallery: {} };
    media[slug] = entry;
    const failed = (file: string, kind: string, error: unknown) =>
      problems.push(
        `${images}${kind}/${file}: could not be read as a picture (${(error as Error).message}).`,
      );

    if (portraits.length > 1) {
      problems.push(
        `${images}profile/: keep one picture here. Found ${portraits.map(({ file }) => file).join(", ")}.`,
      );
    }
    const [portrait] = portraits;
    if (portrait) {
      try {
        await resize(
          portrait.source,
          new URL("profile.webp", out),
          "inside",
          THUMB,
        );
        await resize(
          portrait.source,
          new URL("profile-bust.webp", out),
          "bust",
        );
        await resize(
          portrait.source,
          new URL("profile-small.webp", out),
          "square",
          SMALL,
        );
        entry.profile = {
          bust: `/team/${slug}/profile-bust.webp`,
          small: `/team/${slug}/profile-small.webp`,
          src: `/team/${slug}/profile.webp`,
        };
      } catch (error) {
        failed(portrait.file, "profile", error);
      }
    }

    for (const picture of gallery) {
      const full = new URL(`gallery-${picture.name}.webp`, out);
      const base = `/team/${slug}/gallery-${picture.name}`;
      try {
        await resize(picture.source, full, "inside", FULL);
        await resize(
          picture.source,
          new URL(`gallery-${picture.name}-thumb.webp`, out),
          "inside",
          THUMB,
        );
        const { height = 0, width = 0 } = await sharp(
          fileURLToPath(full),
        ).metadata();
        entry.gallery[picture.name] = {
          height,
          src: `${base}.webp`,
          thumb: `${base}-thumb.webp`,
          width,
        };
      } catch (error) {
        failed(picture.file, "gallery", error);
      }
    }

    // A caption that points at nothing.
    const captions = (profile.front.captions ?? {}) as Record<string, unknown>;
    for (const file of Object.keys(captions)) {
      if (entry.gallery[mediaName(file)]) continue;
      problems.push(
        `${profile.label}: the caption "${file}" matches no picture in ${images}gallery/.`,
      );
    }
  }

  // Copies of pictures that have since been removed or renamed.
  if (await exists(OUTPUT)) {
    for (const entry of await readdir(OUTPUT, {
      recursive: true,
      withFileTypes: true,
    })) {
      if (!entry.isFile()) continue;
      const file = new URL(
        `file://${entry.parentPath.replace(/\/?$/, "/")}${entry.name}`,
      );
      if (!kept.has(file.href)) await rm(file);
    }
  }

  const output = `${JSON.stringify(media, null, 2)}\n`;
  const current = await readFile(MANIFEST, "utf8").catch(() => "");
  if (output !== current) await writeFile(MANIFEST, output);

  if (problems.length === 0) return;

  console.error(`Team pictures:\n${problems.join("\n")}`);
  process.exit(1);
};

await main();
