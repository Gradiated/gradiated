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

/** A remote role says so in its location, even if Ashby's location doesn't. */
const locationOf = (job: Job): string =>
  job.workplace === "REMOTE" && !/remote/i.test(job.location)
    ? `Remote, ${job.location}`
    : job.location;

const reasons = [
  {
    title: "Work on the whole problem.",
    body: "We put the latest open-weight models into production, develop new inference techniques, and follow performance all the way down to silicon. The field moves quickly; the work stays close to its edge.",
  },
  {
    title: "Learn across the stack.",
    body: "Nobody arrives knowing every layer. We run internal lectures, work through problems together, and expect everyone to teach what they know. You will leave with a much wider technical range than you arrived with.",
  },
  {
    title: "Build with people who have done it before.",
    body: "You will work directly with a small founding team that has built PostHog into a unicorn and a developer brand people love, led AI engineering, and gone deep in mathematics, semiconductors, and quantum computing.",
  },
  {
    title: "Build a reputation that compounds.",
    body: "We are engineering-led and trust-led. We want customers to find us through excellent work, useful writing, and other builders telling them about us. The aim is lasting technical advantage, not a brief turn in the hype cycle.",
  },
] as const;

const expectations = [
  {
    title: "It is unusually low ego.",
    body: "The work is technically demanding, but we do not hire people who need to be the smartest person in the room. Startups are humbling; good people change their minds quickly.",
  },
  {
    title: "The mission is long term. The cadence is not.",
    body: "We want to redesign inference all the way down to silicon. Today, that means hustling for customers, shipping constantly, and learning from what happens. This is not an academic lab: there is real pressure to perform, grow, and win.",
  },
  {
    title: "Specialists still work on the whole problem.",
    body: "Nobody knows every layer, but ‘that is not my area’ cannot become a reason to stop. You will be expected to learn outside your discipline and help wherever progress is blocked.",
  },
  {
    title: "Customers are part of the technical work.",
    body: "We do not develop technology in isolation and look for a use later. Customer workloads tell us what matters, what is wasteful, and what to build next.",
  },
  {
    title: "We show our thinking.",
    body: "Our methods are public, including beliefs that may change. Writing clearly enough for other people to disagree with us is part of doing the work properly.",
  },
] as const;

const methods = [
  {
    href: "/library/method/mission/",
    title: "Affordable and open intelligence",
  },
  {
    href: "/library/method/sequencing-and-depth/",
    title: "Sequencing and depth",
  },
  {
    href: "/library/method/what-we-look-for/",
    title: "What we look for",
  },
  {
    href: "/library/method/values/",
    title: "Values",
  },
] as const;

export const CareersIndexPage = (): ReactElement => (
  <Substrate>
    <Nav />

    <Band>
      <Module className="gr-module--top gr-careers-module" index={0}>
        <header className="gr-masthead gr-careers-head">
          <Reveal
            as="h1"
            by="word"
            className="gr-masthead-title gr-masthead-title--display"
          >
            Come make AI use less energy.
          </Reveal>
          <p className="gr-careers-lede gr-muted">
            Gradiated is a small research and engineering team focused on making
            open-model inference radically more efficient. We work from model
            behaviour to software, systems, and silicon—and we are building the
            company for the long term.
          </p>
          <a className="gr-careers-jump gr-label" href="#open-roles">
            See open roles
            <span aria-hidden className="gr-careers-jump-arrow">
              <Arrow />
            </span>
          </a>
        </header>
      </Module>

      <Module className="gr-careers-module" index={1} title="Why Gradiated">
        <ul className="gr-careers-reasons">
          {reasons.map((reason) => (
            <li className="gr-careers-reason" key={reason.title}>
              <h3 className="gr-careers-reason-title">{reason.title}</h3>
              <p className="gr-careers-reason-body gr-muted">{reason.body}</p>
            </li>
          ))}
        </ul>
      </Module>

      <Module
        className="gr-careers-module"
        index={2}
        title="Before you decide."
      >
        <ul className="gr-careers-reasons">
          {expectations.map((expectation) => (
            <li className="gr-careers-reason" key={expectation.title}>
              <h3 className="gr-careers-reason-title">{expectation.title}</h3>
              <p className="gr-careers-reason-body gr-muted">
                {expectation.body}
              </p>
            </li>
          ))}
        </ul>
      </Module>

      <Module className="gr-careers-module" index={3}>
        <div className="gr-careers-methods-intro">
          <p className="gr-careers-methods-lede">
            Our handbook is public because the way we work should not be a
            surprise revealed after you start.
          </p>
          <nav aria-label="Selected methods" className="gr-careers-methods">
            {methods.map((method) => (
              <a
                className="gr-careers-method"
                href={method.href}
                key={method.href}
              >
                {method.title}
              </a>
            ))}
            <a className="gr-careers-method" href="/library/?show=methods">
              All methods
            </a>
          </nav>
        </div>
      </Module>

      <Module
        className="gr-careers-module"
        id="open-roles"
        index={4}
        title="Open roles"
      >
        {jobs.length > 0 ? (
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
                      <span>{locationOf(job)}</span>
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
        ) : (
          <div className="gr-careers-no-roles">
            <p className="gr-careers-no-roles-title">No role listed today?</p>
            <p className="gr-careers-no-roles-body gr-muted">
              If you are exceptional at inference software, systems, or silicon,
              we would still like to hear from you.
            </p>
            <a className="gr-label" href="mailto:team@gradiated.com">
              team@gradiated.com
            </a>
          </div>
        )}
      </Module>
    </Band>

    <Band>
      <Footer index={5} />
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
  /* The last section jumped to, kept after the pin is released so that, at the
     end of the page, it can still win over the sections around it. */
  const jumped = useRef<string | undefined>(undefined);
  const jumpTo = (id: string): void => {
    pinned.current = id;
    jumped.current = id;
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
    let settle: number | undefined;
    const update = (): void => {
      if (pinned.current) {
        setActive(pinned.current);
        /* Released once the jump has finished scrolling, so a scroll that no
           input event announces (dragging the scrollbar) still moves it on. */
        window.clearTimeout(settle);
        settle = window.setTimeout(settled, 200);
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
      if (atEnd) {
        /* At the end of the page several short sections can be on screen at
           once: keep the one the reader jumped to if it is still in view. */
        const target =
          jumped.current && document.getElementById(jumped.current);
        current =
          target && target.getBoundingClientRect().top < window.innerHeight
            ? target.id
            : (blocks.at(-1)?.id ?? current);
      }
      setActive(current);
    };
    const unpin = (): void => {
      pinned.current = undefined;
      jumped.current = undefined;
    };
    /* The jump has finished scrolling: let the scroll position decide again. */
    const settled = (): void => {
      pinned.current = undefined;
      update();
    };
    const userScrollEvents = [
      "wheel",
      "touchstart",
      "keydown",
      "pointerdown",
    ] as const;

    update();
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    userScrollEvents.forEach((type) =>
      window.addEventListener(type, unpin, { passive: true }),
    );
    return () => {
      window.clearTimeout(settle);
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
                <dd>{locationOf(job)}</dd>
              </div>
              {/* A remote role has no office days; its location says it is remote. */}
              {job.workplace !== "REMOTE" ? (
                <div>
                  <dt className="gr-label gr-muted">Office</dt>
                  <dd>{job.officeDays ?? OFFICE_DAYS}</dd>
                </div>
              ) : null}
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
