import { useEffect, useRef, useState } from "react";
import type { ReactElement } from "react";
import {
  Arrow,
  Band,
  Footer,
  Module,
  Nav,
  Reveal,
  SectionFab,
  Substrate,
} from "../components/design";
import { ApplyForm } from "../components/ApplyForm";
import { jobs } from "../careers";
import type { Job } from "../careers";
import {
  COMPENSATION,
  OFFICE_DAYS,
  aboutGradiated,
  howWeWork,
  interviewSteps,
  payAndEquity,
} from "../careers-copy";
import "../styles/index.css";

/**
 * Careers, in the design system.
 *
 * The index is a list rather than a grid: there are three roles, and a grid of
 * three cards would make them look like a product range. A role is read one at
 * a time, and each line is a decision — so the layout is rows with room, and
 * the only thing competing for attention is the next title down.
 */
export const CareersIndexPage = (): ReactElement => (
  <Substrate>
    <Nav />

    <Band>
      <Module className="gr-module--top" index={0}>
        <header className="gr-masthead">
          <p className="gr-label">Careers</p>
          <Reveal
            as="h1"
            by="word"
            className="gr-masthead-title gr-masthead-title--display"
          >
            We are hiring.
          </Reveal>
        </header>

        <ul className="gr-roles">
          {jobs.map((job) => (
            <li key={job.slug}>
              <a className="gr-role" href={`/careers/${job.slug}/`}>
                <span className="gr-role-text">
                  <span className="gr-role-title">{job.title}</span>
                  <span className="gr-role-summary gr-muted">
                    {job.summary}
                  </span>
                  <span className="gr-role-facts gr-label gr-muted">
                    {job.team ? (
                      <>
                        <span>{job.team}</span>
                        <span aria-hidden>·</span>
                      </>
                    ) : null}
                    <span>{job.location}</span>
                  </span>
                </span>

                {/* At the end of the row and centred on it, rather than
                    chasing the title's baseline — a mark that points at the
                    whole row belongs at the row's edge. */}
                <span aria-hidden className="gr-role-go">
                  <Arrow />
                </span>
              </a>
            </li>
          ))}
        </ul>
      </Module>
    </Band>

    <Band>
      <Footer index={1} />
    </Band>
  </Substrate>
);

/** `Pay and equity` -> `pay-and-equity`, for the anchor. */
const anchor = (title: string) =>
  title
    .toLowerCase()
    .replace(/[^\w]+/g, "-")
    .replace(/^-|-$/g, "");

/** One block of the posting: its heading, and what it lists. */
const Section = ({
  items,
  numbered = false,
  title,
}: {
  items: readonly string[];
  /** The interview steps are a sequence; everything else is a set. */
  numbered?: boolean;
  title: string;
}): ReactElement => (
  <section className="gr-job-section" id={anchor(title)}>
    <h2 className="gr-job-section-title">{title}</h2>
    <ol className={`gr-job-list${numbered ? " gr-job-list--numbered" : ""}`}>
      {items.map((item, index) => (
        <li key={item}>
          {numbered ? (
            <span aria-hidden className="gr-job-step">
              {String(index + 1).padStart(2, "0")}
            </span>
          ) : (
            <span aria-hidden className="gr-job-mark" />
          )}
          <span>{item}</span>
        </li>
      ))}
    </ol>
  </section>
);

export const JobDetailPage = ({ job }: { job: Job }): ReactElement => {
  /* Built from the same list the page renders, so the contents cannot come to
     disagree with the sections — unlike the Library's reading page, a posting
     knows its own headings before it draws them. */
  const about =
    job.about ??
    (job.foundingContext
      ? [...aboutGradiated.slice(0, -1), job.foundingContext]
      : aboutGradiated);
  const sections = [
    { items: about, title: "About Gradiated" },
    { items: job.purpose, title: "Why this role exists" },
    { items: job.responsibilities, title: "What you will do" },
    { items: job.problems, title: "Problems you may work on" },
    { items: job.requirements, title: "What we are looking for" },
    { items: job.notFor, title: "This role is not for you if" },
    ...(job.extraSections ?? []),
    { items: job.howWeWork ?? howWeWork, title: "How we work" },
    { items: job.pay ?? payAndEquity, title: "Pay and equity" },
    {
      items: job.interviewSteps ?? interviewSteps,
      numbered: true,
      title: "Interview process",
    },
  ].filter((section) => section.items.length > 0);

  const [active, setActive] = useState<string>();

  /* A contents link pins the section it asked for until the reader scrolls
     by themselves: near the end of the page a short section cannot reach the
     top, and the highlight should still name the section that was chosen. */
  const pinned = useRef<string | undefined>(undefined);
  const jumpTo = (id: string): void => {
    pinned.current = id;
    setActive(id);
  };

  useEffect(() => {
    const blocks = [
      ...document.querySelectorAll<HTMLElement>(".gr-job-section"),
    ];
    /* The section the reader is IN: the last one whose top has passed the
       reading line, a little below where a contents link lands a heading
       (the root scroll-padding). Taking the first IntersectionObserver entry
       instead could name the section above the one just jumped to. */
    const update = (): void => {
      if (pinned.current) {
        setActive(pinned.current);
        return;
      }
      const landing =
        parseFloat(
          getComputedStyle(document.documentElement).scrollPaddingTop,
        ) || 0;
      const line = landing + window.innerHeight * 0.15;
      const atEnd =
        window.innerHeight + window.scrollY >=
        document.documentElement.scrollHeight - 2;
      let current = blocks[0]?.id;
      for (const block of blocks) {
        if (block.getBoundingClientRect().top <= line) current = block.id;
      }
      setActive(atEnd ? (blocks.at(-1)?.id ?? current) : current);
    };
    const unpin = (): void => {
      pinned.current = undefined;
    };
    const userScrollEvents = ["wheel", "touchstart", "keydown"] as const;

    update();
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    userScrollEvents.forEach((type) =>
      window.addEventListener(type, unpin, { passive: true }),
    );
    return () => {
      window.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
      userScrollEvents.forEach((type) =>
        window.removeEventListener(type, unpin),
      );
    };
  }, [job.slug]);

  return (
    <Substrate>
      <Nav />

      <Band>
        <Module className="gr-module--top" index={0}>
          <a className="gr-read-back gr-label" href="/careers/">
            <span aria-hidden className="gr-read-back-arrow">
              <Arrow />
            </span>
            Careers
          </a>

          <div className="gr-job-top">
            <header className="gr-job-head">
              {job.team ? (
                <p className="gr-label gr-muted">{job.team}</p>
              ) : null}
              <h1 className="gr-job-title">{job.title}</h1>
              <p className="gr-job-summary gr-muted">{job.summary}</p>
            </header>

            {/* The three things a reader checks before reading anything else,
              beside the title rather than under it — they are the terms of the
              role, and the reader is weighing them WHILE they read it. */}
            <dl className="gr-job-facts">
              <div>
                <dt className="gr-label gr-muted">Location</dt>
                <dd>{job.location}</dd>
              </div>
              <div>
                <dt className="gr-label gr-muted">Office</dt>
                <dd>
                  {job.workplace === "REMOTE"
                    ? "Remote"
                    : (job.officeDays ?? OFFICE_DAYS)}
                </dd>
              </div>
              <div>
                <dt className="gr-label gr-muted">Compensation</dt>
                <dd>{COMPENSATION}</dd>
              </div>
            </dl>
          </div>

          <div className="gr-job-body">
            {/* Sticky, so the whole posting stays reachable however far down it
              the reader is — nine sections is too many to scroll back through
              to find the one about pay. */}
            <nav aria-label="Sections" className="gr-job-nav">
              {sections.map((section) => (
                <a
                  aria-current={
                    anchor(section.title) === active ? "true" : undefined
                  }
                  className="gr-job-nav-link"
                  onClick={() => jumpTo(anchor(section.title))}
                  href={`#${anchor(section.title)}`}
                  key={section.title}
                >
                  {section.title}
                </a>
              ))}
            </nav>

            <div className="gr-job-sections">
              {sections.map((section) => (
                <Section key={section.title} {...section} />
              ))}
            </div>
          </div>

          {/* The section index's mobile form — hidden above the wide tier,
            where the sticky column beside the text does this job. */}
          {sections.length > 1 ? (
            <SectionFab>
              {sections.map((section) => (
                <a
                  className="gr-fab-link"
                  onClick={() => jumpTo(anchor(section.title))}
                  href={`#${anchor(section.title)}`}
                  key={section.title}
                >
                  {section.title}
                </a>
              ))}
            </SectionFab>
          ) : null}

          <section className="gr-job-apply">
            <p className="gr-label">Apply</p>
            <h2 className="gr-job-apply-title">Let&apos;s talk.</h2>
            <p className="gr-job-apply-body gr-muted">
              If this sounds interesting to you, we&apos;d like to hear from
              you. Fill in the form below and we&apos;ll get back to you within
              a few days.
            </p>
            <ApplyForm jobPostingId={job.ashbyJobPostingId} />
          </section>
        </Module>
      </Band>

      <Band>
        <Footer index={1} />
      </Band>
    </Substrate>
  );
};
