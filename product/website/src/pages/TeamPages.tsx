import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactElement } from "react";
import { marked } from "marked";
import { useLocation } from "react-router-dom";
import { articles } from "../articles";
import { PixelIcon, Tabs } from "../components/design";
import { useRailDocNav } from "../components/design/RailShell";
import type { RailDocGroup } from "../components/design/RailShell";
import { SectionNavigationFab } from "../components/design/SectionNavigation";
import { initials } from "../people";
import {
  Arrow,
  Band,
  Footer,
  Module,
  Nav,
  Reveal,
  Substrate,
} from "../components/design";
import { Portrait } from "../components/team/Portrait";
import { TeamMap } from "../components/team/TeamMap";
import { displayDate } from "../library-stories";
import { team, teamPlaces } from "../team";
import { postsIn, sectionsOf } from "../team-metadata";
import type { ExternalPost } from "../team-metadata";
import type { TeamMember } from "../team";
import "../styles/index.css";

/* The rail lists everyone by name, as it lists the handbook's pages.
   Module-level so its identity is stable. */
const RAIL_GROUPS: RailDocGroup[] = [
  {
    items: team.map((member) => ({
      href: member.path,
      label: member.name,
      thumb: member.photo
        ? { src: member.photo.small }
        : { text: initials(member.name.replace(/^Dr\s+/, "")) },
    })),
  },
];

/* On a phone the rail is a strip, so the same contents sit behind a button. */
const FAB_GROUPS = [
  {
    items: team.map((member) => ({ href: member.path, label: member.name })),
  },
];

const useTeamRail = (current: string): void =>
  useRailDocNav({
    title: "Team",
    current,
    groups: RAIL_GROUPS,
    backHref: "/about/",
  });

// Turned to the North Atlantic, so the UK, Toronto and San Francisco all
// face the reader on the part of the globe that shows.
const GLOBE_CENTRE = { latitude: 40, longitude: -40 };

/** /team/ — who we are, beside where in the world we are. */
export const TeamPage = (): ReactElement => {
  useTeamRail("/team/");

  return (
    <Substrate>
      <Nav />

      <Band>
        <Module bleed className="gr-team-overview" index={0}>
          <div className="gr-team-overview-copy">
            <h1 className="gr-team-overview-title">
              {["The people", "at Gradiated"].map((line, index) => (
                <span className="gr-hero-line" key={line}>
                  <Reveal by="word" from={index * 2}>
                    {line}
                  </Reveal>
                </span>
              ))}
            </h1>
            <p className="gr-body">
              Gradiated (a subsidiary of PostHog) is helping organizations the
              world over reduce their dependence on the frontier labs and,
              consequently, the cost of inference. Our team is small, wildly
              talented, and diverse in both education and experience.
            </p>
            <p className="gr-body">
              We value depth, candor, and a scientific temperament, and prefer
              dropping our egos at work. The team at Gradiated is comfortable
              navigating ambiguity and very resourceful in doing so.
            </p>
            <div className="gr-page-hero-actions">
              <a className="gr-button gr-button--main" href="/careers/">
                Join our team
                <Arrow />
              </a>
            </div>
          </div>

          {teamPlaces.length > 0 ? (
            <TeamMap centre={GLOBE_CENTRE} places={teamPlaces} />
          ) : null}
        </Module>
      </Band>
    </Substrate>
  );
};

/* -- profile ---------------------------------------------------------------- */

const LINKS = [
  { key: "website", label: "Website" },
  { key: "github", label: "GitHub" },
  { key: "linkedin", label: "LinkedIn" },
  { key: "x", label: "X" },
] as const;

const LINK_ICONS = {
  github: "github",
  linkedin: "linkedin",
  website: "globe",
  x: "x-logo",
} as const;

const LinkIcon = ({
  kind,
}: {
  kind: (typeof LINKS)[number]["key"];
}): ReactElement => <PixelIcon name={LINK_ICONS[kind]} />;

/* The icon beside each entry in the profile's contents. A heading nobody
   planned for still gets one. */
const sectionIcon = (title: string): ReactElement => {
  const name = title.toLowerCase();
  if (name === "bio") return <PixelIcon name="user" />;
  if (name.startsWith("working on")) return <PixelIcon name="hammer" />;
  if (name.startsWith("things")) return <PixelIcon name="list-checks" />;
  if (name === "posts") return <PixelIcon name="file-text" />;
  if (name === "gallery") return <PixelIcon name="image" />;

  return <PixelIcon name="hash" />;
};

/** "GB" -> the Union flag. Two regional-indicator letters make a flag. */
const flagOf = (code: string): string =>
  String.fromCodePoint(
    ...[...code].map((letter) => 0x1f1e6 + letter.charCodeAt(0) - 65),
  );

/**
 * Which section is open. One section shows at a time; the address carries it
 * as a hash (/team/ada/#posts), so a section can be linked and shared.
 *
 * The first section is what the server renders, so the hash is read after
 * mount rather than during it.
 */
const useOpenSection = (
  ids: string[],
): [string | undefined, (id: string) => void] => {
  const [open, setOpen] = useState(ids[0]);
  const key = ids.join("|");
  // A route change between profiles reuses this component and fires no
  // hashchange, so the location is a dependency too.
  const { hash, pathname } = useLocation();

  useEffect(() => {
    const read = () => {
      let wanted = "";
      try {
        wanted = decodeURIComponent(window.location.hash.slice(1));
      } catch {
        // A malformed fragment (#%) names no section.
      }
      setOpen(ids.includes(wanted) ? wanted : ids[0]);
    };

    read();
    window.addEventListener("hashchange", read);
    return () => window.removeEventListener("hashchange", read);
    // `key` stands in for `ids`, which is a new array each render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, pathname, hash]);

  const choose = (id: string) => {
    setOpen(id);
    // replaceState: moving between sections is not a page in the history.
    window.history.replaceState(
      window.history.state,
      "",
      id === ids[0] ? window.location.pathname : `#${id}`,
    );
  };

  return [open, choose];
};

type Picture = TeamMember["gallery"][number];

/**
 * The gallery: a grid of pictures, each opening full size.
 *
 * A native <dialog>, so focus is held inside it, Escape closes it and the
 * page behind is inert without any of that being written here.
 */
const Gallery = ({ pictures }: { pictures: Picture[] }): ReactElement => {
  const dialog = useRef<HTMLDialogElement>(null);
  const [index, setIndex] = useState<number | null>(null);
  const shown = index === null ? null : pictures[index];
  const step = (by: number) =>
    setIndex((current) =>
      current === null
        ? current
        : (current + by + pictures.length) % pictures.length,
    );

  useEffect(() => {
    const node = dialog.current;
    if (!node) return;
    if (index !== null && !node.open) node.showModal();
    if (index === null && node.open) node.close();
  }, [index]);

  return (
    <>
      <ul className="gr-profile-gallery">
        {pictures.map((picture, at) => (
          <li key={picture.name}>
            <figure>
              <button
                aria-label={`Open ${picture.caption ?? `picture ${at + 1}`}`}
                className="gr-profile-gallery-open"
                onClick={() => setIndex(at)}
                type="button"
              >
                <img
                  alt={picture.caption ?? ""}
                  loading="lazy"
                  src={picture.thumb}
                />
              </button>
              {picture.caption ? (
                <figcaption>{picture.caption}</figcaption>
              ) : null}
            </figure>
          </li>
        ))}
      </ul>

      <dialog
        aria-label="Picture"
        className="gr-lightbox"
        onClick={(event) => {
          // A click on the backdrop lands on the dialog itself.
          if (event.target === event.currentTarget) setIndex(null);
        }}
        onClose={() => setIndex(null)}
        onKeyDown={(event) => {
          if (event.key === "ArrowRight") step(1);
          if (event.key === "ArrowLeft") step(-1);
        }}
        ref={dialog}
      >
        {shown ? (
          <figure className="gr-lightbox-figure">
            <img
              alt={shown.caption ?? ""}
              height={shown.height}
              src={shown.src}
              width={shown.width}
            />
            {shown.caption ? <figcaption>{shown.caption}</figcaption> : null}
          </figure>
        ) : null}
        <button
          aria-label="Close"
          className="gr-lightbox-button gr-lightbox-close"
          onClick={() => setIndex(null)}
          type="button"
        >
          <PixelIcon name="x" />
        </button>
        {pictures.length > 1 ? (
          <>
            <button
              aria-label="Previous picture"
              className="gr-lightbox-button gr-lightbox-prev"
              onClick={() => step(-1)}
              type="button"
            >
              <PixelIcon name="caret-left" />
            </button>
            <button
              aria-label="Next picture"
              className="gr-lightbox-button gr-lightbox-next"
              onClick={() => step(1)}
              type="button"
            >
              <PixelIcon name="caret-right" />
            </button>
          </>
        ) : null}
      </dialog>
    </>
  );
};

/**
 * Share this profile. On a phone this opens the system share sheet; where
 * there is none, it copies the page's link and says so.
 */
const ShareButton = ({ name }: { name: string }): ReactElement => {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 2000);
    return () => window.clearTimeout(timer);
  }, [copied]);

  const share = async () => {
    // With the hash, so the link opens on the section being read.
    const url = window.location.href;
    try {
      // The share sheet is a phone's habit. With a mouse, a copied link is
      // the quicker thing, even where the browser has a sheet to offer.
      if (navigator.share && window.matchMedia("(pointer: coarse)").matches) {
        await navigator.share({ title: `${name} | Gradiated`, url });
        return;
      }
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      // Dismissing the share sheet rejects; there is nothing to report.
    }
  };

  return (
    <button
      aria-label={`Share ${name}'s profile`}
      className="gr-profile-share"
      data-copied={copied || undefined}
      onClick={() => void share()}
      type="button"
    >
      {copied ? (
        <PixelIcon name="check" />
      ) : (
        <PixelIcon name="arrow-up-right" />
      )}
      <span aria-live="polite" className="gr-profile-share-note">
        {copied ? "Link copied" : ""}
      </span>
    </button>
  );
};

const POST_FILTERS = ["All", "Gradiated", "External"] as const;

/**
 * A person's writing, as a plain list. What they published on Gradiated is
 * found for them; what they published elsewhere is the list of links under
 * their Posts heading. The filter is always there, so the section looks the
 * same on every profile; a filter with nothing behind it says so.
 */
const Posts = ({
  external,
  gradiated,
}: {
  external: ExternalPost[];
  gradiated: Array<{ date: string; href: string; title: string }>;
}): ReactElement => {
  const [filter, setFilter] = useState<(typeof POST_FILTERS)[number]>("All");
  const shown = [
    ...(filter === "External" ? [] : gradiated),
    ...(filter === "Gradiated" ? [] : external),
  ];

  return (
    <div className="gr-profile-posts">
      <Tabs
        label="Which posts to show"
        onChange={(option) =>
          setFilter(option as (typeof POST_FILTERS)[number])
        }
        options={[...POST_FILTERS]}
        quiet
        value={filter}
      />
      {shown.length > 0 ? (
        <ul>
          {shown.map((post) =>
            "href" in post ? (
              <li key={post.href}>
                <a href={post.href}>{post.title}</a>
                <time dateTime={post.date}>{displayDate(post.date)}</time>
              </li>
            ) : (
              <li key={post.url}>
                <a href={post.url} rel="noreferrer" target="_blank">
                  {post.title}
                </a>
                {post.note ? <span>{post.note}</span> : null}
              </li>
            ),
          )}
        </ul>
      ) : (
        <p className="gr-profile-posts-none">
          {filter === "Gradiated"
            ? "Nothing published on Gradiated yet."
            : "Nothing published elsewhere yet."}
        </p>
      )}
    </div>
  );
};

/** /team/<name>/ — one person's page, written by them. */
export const ProfilePage = ({
  member,
}: {
  member: TeamMember;
}): ReactElement => {
  useTeamRail(member.path);

  const sections = useMemo(() => {
    const published = articles
      .filter((article) => article.author === member.name)
      .map((article) => ({
        date: article.publishedAt,
        href: article.path,
        title: article.title,
      }));
    const gallery =
      member.gallery.length > 0 ? <Gallery pictures={member.gallery} /> : null;
    // The file is the person's own Markdown, reviewed in a pull request.
    const prose = (markdown: string): ReactElement => (
      <div
        className="gr-prose gr-profile-prose"
        dangerouslySetInnerHTML={{ __html: marked.parse(markdown) as string }}
      />
    );
    /* Posts and Gallery are on every profile, and each has two sources: what
       the person wrote under the heading, and what the site knows (their
       Library articles, the pictures in their gallery folder). Either alone
       is enough to show the section; with neither, it is not there. */
    let postsPlaced = false;
    let galleryPlaced = false;
    const authored = sectionsOf(member.body, ["posts", "gallery"]).flatMap(
      (section) => {
        const name = section.title.toLowerCase();
        let { markdown } = section;
        let extra: ReactElement | null = null;

        if (name === "posts" && !postsPlaced) {
          postsPlaced = true;
          // Links listed under the heading join the Library articles.
          const listed = postsIn(markdown);
          markdown = listed.rest;
          if (published.length + listed.posts.length > 0)
            extra = <Posts external={listed.posts} gradiated={published} />;
        }
        if (name === "gallery" && !galleryPlaced) {
          galleryPlaced = true;
          extra = gallery;
        }
        if (!markdown && !extra) return [];

        return [
          {
            id: section.id,
            title: section.title,
            content: (
              <>
                {markdown ? prose(markdown) : null}
                {extra}
              </>
            ),
          },
        ];
      },
    );
    const supplied = {
      posts:
        !postsPlaced && published.length > 0 ? (
          <Posts external={[]} gradiated={published} />
        ) : null,
      gallery: galleryPlaced ? null : gallery,
    };

    return [
      // Until someone writes their bio, their summary stands in for it.
      ...(!authored.some((section) => section.title.toLowerCase() === "bio") &&
      member.summary
        ? [
            {
              id: "bio",
              title: "Bio",
              content: (
                <div className="gr-prose gr-profile-prose">
                  <p>{member.summary}</p>
                </div>
              ),
            },
          ]
        : []),
      ...authored,
      ...(supplied.posts
        ? [{ id: "posts", title: "Posts", content: supplied.posts }]
        : []),
      ...(supplied.gallery
        ? [{ id: "gallery", title: "Gallery", content: supplied.gallery }]
        : []),
    ];
  }, [member]);

  const [open, choose] = useOpenSection(sections.map((section) => section.id));
  const links = LINKS.flatMap((link) => {
    const href = member.links[link.key];
    return href ? [{ ...link, href }] : [];
  });

  return (
    <Substrate>
      <Nav />

      <Band>
        <Module bleed className="gr-module--profile" index={0}>
          <SectionNavigationFab
            current={member.path}
            groups={FAB_GROUPS}
            label="Team"
          />

          <div className="gr-profile">
            <header className="gr-profile-head">
              <h1 className="gr-profile-name">{member.name}</h1>
              <div className="gr-profile-meta">
                <p className="gr-profile-role">{member.role}</p>
                {member.location ? (
                  <p className="gr-profile-place">
                    {member.location.countryCode ? (
                      <span aria-hidden="true" className="gr-profile-flag">
                        {flagOf(member.location.countryCode)}
                      </span>
                    ) : null}
                    {member.location.city}, {member.location.country}
                  </p>
                ) : null}
                {links.length > 0 ? (
                  <ul className="gr-profile-links">
                    {links.map((link) => (
                      <li key={link.key}>
                        <a
                          aria-label={`${member.name} on ${link.label}`}
                          href={link.href}
                          rel="noreferrer me"
                          target="_blank"
                          title={link.label}
                        >
                          <LinkIcon kind={link.key} />
                        </a>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            </header>

            <div className="gr-profile-side">
              <Portrait bust eager member={member} />
              {/* Contents and share travel together, so they can never
                  meet on a short window. */}
              <div className="gr-profile-rail">
                {sections.length > 1 ? (
                  <div
                    aria-label={`${member.name}'s profile`}
                    aria-orientation="vertical"
                    className="gr-profile-nav"
                    onKeyDown={(event) => {
                      const by =
                        event.key === "ArrowDown" || event.key === "ArrowRight"
                          ? 1
                          : event.key === "ArrowUp" || event.key === "ArrowLeft"
                            ? -1
                            : 0;
                      if (!by) return;
                      event.preventDefault();
                      const at = sections.findIndex(
                        (section) => section.id === open,
                      );
                      const next =
                        sections[(at + by + sections.length) % sections.length];
                      choose(next.id);
                      document.getElementById(`tab-${next.id}`)?.focus();
                    }}
                    role="tablist"
                  >
                    {sections.map((section) => (
                      <button
                        aria-controls={`panel-${section.id}`}
                        aria-selected={section.id === open}
                        id={`tab-${section.id}`}
                        key={section.id}
                        onClick={() => choose(section.id)}
                        role="tab"
                        tabIndex={section.id === open ? 0 : -1}
                        type="button"
                      >
                        <span className="gr-profile-nav-icon">
                          {sectionIcon(section.title)}
                        </span>
                        {section.title}
                      </button>
                    ))}
                  </div>
                ) : null}
                <ShareButton name={member.name} />
              </div>
            </div>

            <div className="gr-profile-main">
              {/* Every section is in the document, for search engines and
                  for find-in-page; only the open one is shown. */}
              {sections.map((section) => (
                <section
                  aria-labelledby={
                    sections.length > 1 ? `tab-${section.id}` : undefined
                  }
                  className="gr-profile-section"
                  hidden={section.id !== open}
                  id={`panel-${section.id}`}
                  key={section.id}
                  role={sections.length > 1 ? "tabpanel" : undefined}
                >
                  <h2 className="gr-profile-title">{section.title}</h2>
                  {section.content}
                </section>
              ))}
            </div>
          </div>
        </Module>
      </Band>

      <Band>
        <Footer index={1} />
      </Band>
    </Substrate>
  );
};
