import type { CSSProperties, ReactElement } from "react";
import type { ArtworkPreset } from "../../lib/artwork";
import { WaferArtwork } from "./WaferArtwork";
import { SandCircuitArtwork } from "./SandCircuitArtwork";

/**
 * One piece in the Library, as a card.
 *
 * Two shapes, and the difference is only where the well sits: the lead puts
 * it BESIDE the text, everything else puts it ABOVE. Same parts in the same
 * order either way — well, title, standfirst, excerpt, byline — so a piece
 * reads the same whether it is leading the page or sitting three-up at the
 * foot of it, and promoting one is a change of shape rather than of content.
 *
 * Covers are one small system rather than a second catalogue: the Story owns
 * its source image, crop and treatment, and every surface that renders it gets
 * the same artwork.
 */

export type StoryCover = ArtworkPreset;

/** Real artwork for a piece, in the two crops the layout uses. */
export type StoryArt = {
  /** The 0.89 portrait crop — narrow cells, the read page, mobile. */
  tall: string;
  /** The landscape crop for the lead and pair cells. Falls back to tall. */
  wide?: string;
};

export type Story = {
  /** Real artwork, when a piece has it. Wins over `cover`. */
  art?: StoryArt;
  /** A generated wafer artwork — the fallback while art does not exist. */
  cover?: StoryCover;
  /** Which collection in the Library this belongs to — what the filters act on. */
  kind: "method" | "note" | "hardware";
  animatedCover?: "sand-circuit";
  /** Human-readable date; `dateTime` carries the machine-readable one. */
  date: string;
  dateTime?: string;
  /** The opening of the piece itself, trimmed. */
  excerpt?: string;
  href: string;
  /** The one line under the title — what the piece is about. */
  lede?: string;
  title: string;
};

export const StoryCard = ({
  story,
  variant = "card",
}: {
  story: Story;
  variant?: "card" | "lead";
}): ReactElement => (
  <article className={`gr-story gr-story--${variant}`}>
    <a className="gr-story-link" href={story.href}>
      {/* Decorative: the title immediately below carries the meaning.
          Real artwork wins over the generated cover; the two crops are
          chosen by the CARD'S OWN WIDTH via a container query, because a
          story does not know which cell the row cycle will seat it in —
          see .gr-story-art in pages.css. */}
      <span
        aria-hidden
        className={`gr-story-well${story.art || story.cover || story.animatedCover ? " gr-story-cover" : ""}`}
      >
        {story.animatedCover === "sand-circuit" ? (
          <SandCircuitArtwork />
        ) : story.art ? (
          <span
            className="gr-story-art"
            style={
              {
                "--art-tall": `url(${story.art.tall})`,
                "--art-wide": `url(${story.art.wide ?? story.art.tall})`,
              } as CSSProperties
            }
          />
        ) : story.cover ? (
          <WaferArtwork options={story.cover} />
        ) : null}
      </span>

      <span className="gr-story-text">
        <span className="gr-story-title">{story.title}</span>

        {story.lede ? (
          <span className="gr-story-lede">{story.lede}</span>
        ) : null}

        {story.excerpt ? (
          <span className="gr-story-excerpt gr-muted">{story.excerpt}</span>
        ) : null}

        {/* Last, and set quietest: the date is what you check after you have
            decided you are interested, not before. */}
        <span className="gr-story-byline gr-muted">
          {story.dateTime ? (
            <time dateTime={story.dateTime}>{story.date}</time>
          ) : (
            story.date
          )}
        </span>
      </span>
    </a>
  </article>
);

/**
 * A row of cards. `columns` is a grid-template-columns value, so the page can
 * say `1fr 2fr` and mean it — the rhythm of wide and narrow rows IS the
 * magazine layout, and it belongs in the page rather than hidden behind names
 * like "featured" and "secondary".
 */
export const StoryRow = ({
  columns,
  lead = false,
  stories,
}: {
  columns: string;
  /** The one card at the top of the page, laid out with its well beside. */
  lead?: boolean;
  stories: Story[];
}): ReactElement => {
  return (
    <div
      className="gr-story-row"
      data-columns={stories.length}
      style={{ gridTemplateColumns: columns } as CSSProperties}
    >
      {stories.map((story) => (
        <StoryCard
          key={story.href}
          story={story}
          variant={lead ? "lead" : "card"}
        />
      ))}
    </div>
  );
};

/**
 * The same pieces as rows rather than cards.
 *
 * Not a different component's worth of difference: it is the same title,
 * standfirst and byline, with the well dropped and the metadata pulled into a
 * column of its own so a reader scanning for one piece has a single axis to
 * run down. The card view is for browsing; this is for finding.
 */
export const StoryList = ({ stories }: { stories: Story[] }): ReactElement => (
  <ul className="gr-storylist">
    {stories.map((story) => (
      <li key={story.href}>
        <a className="gr-storylist-row" href={story.href}>
          <span className="gr-storylist-meta gr-muted">
            {story.dateTime ? (
              <time dateTime={story.dateTime}>{story.date}</time>
            ) : (
              story.date
            )}
          </span>
          <span className="gr-storylist-text">
            <span className="gr-storylist-title">{story.title}</span>
            {story.lede ? (
              <span className="gr-storylist-lede gr-muted">{story.lede}</span>
            ) : null}
          </span>
        </a>
      </li>
    ))}
  </ul>
);
