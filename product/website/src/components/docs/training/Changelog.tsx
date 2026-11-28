import type { ReactElement } from "react";

import changelog from "../../../docs/training/generated/changelog.json";

type Release = { version: string; date: string | null; html: string };

const RELEASES = (changelog as { releases: Release[] }).releases;

const anchorOf = (version: string): string => `v${version.replace(/\./g, "-")}`;

/* grad's CHANGELOG.md, one section per release, newest first. The HTML is
   rendered from the repository's own Markdown at sync time. */
export const DocsChangelog = (): ReactElement => (
  <div className="gr-changelog">
    {RELEASES.map((release) => (
      <section className="gr-changelog-release" key={release.version}>
        <h2 className="gr-doc-heading" id={anchorOf(release.version)}>
          {release.version}
          {release.date ? (
            <time className="gr-changelog-date" dateTime={release.date}>
              {release.date}
            </time>
          ) : null}
          <a
            aria-label={`Link to ${release.version}`}
            className="gr-doc-anchor"
            href={`#${anchorOf(release.version)}`}
          >
            #
          </a>
        </h2>
        <p className="gr-changelog-links">
          <a
            href={`https://github.com/Gradiated/grad/releases/tag/v${release.version}`}
          >
            Release on GitHub
          </a>
        </p>
        <div
          className="gr-changelog-body"
          dangerouslySetInnerHTML={{ __html: release.html }}
        />
      </section>
    ))}
  </div>
);
