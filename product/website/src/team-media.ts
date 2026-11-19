/* A person's pictures live in their folder, sorted by what they are for:

     content/team/<name>/images/profile/   their portrait (one picture)
     content/team/<name>/images/gallery/   the Gallery section

   scripts/sync-team-media.ts resizes each one into public/team/<name>/ and
   lists the results in src/team-media.generated.json, which is what the
   pages read. */

export type TeamPicture = {
  height: number;
  /** The picture at full size, for the viewer. */
  src: string;
  /** A smaller copy, for grids and cards. */
  thumb: string;
  width: number;
};

export type TeamPortrait = {
  /** Cropped to head and chest at 4:5, for the person's own page. */
  bust: string;
  /** A small square, for the navigation and name pills. */
  small: string;
  src: string;
};

export type TeamMedia = Record<
  string,
  {
    /** Keyed by `mediaName`, in the order they are shown. */
    gallery: Record<string, TeamPicture>;
    profile?: TeamPortrait;
  }
>;

/** "My Desk (2).JPG" -> "my-desk-2": what a picture is called everywhere
 *  after it has been dropped in the folder. */
export const mediaName = (file: string): string =>
  file
    .replace(/\.[a-z0-9]+$/i, "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
