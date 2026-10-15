import type { ArtworkPreset } from "../../lib/artwork";
import { libraryStories } from "../../library-stories";

/**
 * The nav's "latest writing" list: the Library's own catalogue, shaped for a
 * thumbnail row.
 *
 * ONE CATALOGUE, which is the point of this file. It used to build its own
 * from `notes` and `methodPages` — a different set from the one the Library
 * page renders, which reads the MDX articles as well. So the newest piece on
 * the site, the Carat article, was missing from the navigation entirely while
 * appearing first on the Library index. Two sources for one list is how that
 * happens; there is one now.
 *
 * It cost two 404s before this, too: the method rows were written out by hand
 * against /library/handbook/ and carried on pointing there after that half
 * became /library/method/.
 *
 * Every row is a real page. There was briefly an invented one to design
 * against; it is gone, because a fabricated article in the navigation is worse
 * than a short list.
 */

export type LibraryEntry = {
  /** The tall crop of the piece's real artwork. Wins over `cover`. */
  art?: string;
  cover?: ArtworkPreset;
  /** Where in the gradient the cover's window sits. */
  coverAt: string;
  /** Already formatted for reading; `dateTime` carries the machine value. */
  date: string;
  dateTime?: string;
  /** A --gradient-* token, standing in until each piece has a real cover. */
  gradient: string;
  href: string;
  /** Which collection in the Library it belongs to. */
  kind: "method" | "note";
  title: string;
};

/* Placeholder covers. Assigned in order rather than chosen per piece — they
   are here so the list is not three empty wells, and each should be replaced
   by artwork the way the panel cards were.

   Each takes a SLICE of its gradient rather than the whole ramp: at thumbnail
   size a full two-stop gradient reads as a swatch of the system, and three of
   them stacked read as a legend. A window onto one part reads as a colour
   field, which is what a cover is. The offsets are spread so no two rows land
   on the same part of their ramp. */
const COVERS = [
  { at: "22%", token: "--gradient-shallows" },
  { at: "64%", token: "--gradient-dawn" },
  { at: "88%", token: "--gradient-morning" },
];

/* Order comes from the catalogue: newest writing first, then the handbook in
   its authored sequence. Covers are assigned after, so the newest piece always
   takes the first one and the set stays stable as entries are added. */
export const library: LibraryEntry[] = libraryStories.map((story, index) => {
  const cover = COVERS[index % COVERS.length];
  return {
    art: story.art?.tall,
    cover: story.cover,
    coverAt: cover.at,
    date: story.date,
    dateTime: story.dateTime,
    gradient: cover.token,
    href: story.href,
    kind: story.kind,
    title: story.title,
  };
});
