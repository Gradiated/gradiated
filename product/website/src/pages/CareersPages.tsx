import { useEffect, useRef, useState } from "react";
import type { CSSProperties, ReactElement } from "react";
import {
  Arrow,
  Band,
  Footer,
  Module,
  BadgeCard,
  Nav,
  Reveal,
  SectionFab,
  Substrate,
} from "../components/design";
import { GradientASCII } from "../components/design/GradientASCII";
import { Noise } from "../components/design/Noise";
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
import { useRailBack } from "../components/design/RailShell";
import "../styles/index.css";

/** A remote role says so in its location, even if Ashby's location doesn't. */
const locationOf = (job: Job): string =>
  job.workplace === "REMOTE" && !/remote/i.test(job.location)
    ? `Remote, ${job.location}`
    : job.location;

const reasons = [
  {
    title: (
      <>
        One problem.
        <br />
        Every layer.
      </>
    ),
    body: "We put the latest open-weight models into production, develop new inference techniques, and follow performance all the way down to silicon. Nobody arrives knowing every layer, so we run internal lectures, work through problems together, and expect everyone to teach what they know.",
  },
  {
    title: "Half a million customers later, we’re starting again.",
    body: "You will work directly with a small founding team that has built PostHog into a unicorn and a developer brand people love, led AI engineering, and gone deep in mathematics, semiconductors, and quantum computing.",
  },
  {
    title: "Build a reputation that compounds.",
    body: "We are engineering-led and trust-led. We want customers to find us through excellent work, useful writing, and other builders telling them about us. The aim is lasting technical advantage, not a brief turn in the hype cycle.",
  },
] as const;

const expectations = [
  {
    title: "The mission is long term. The cadence is not.",
    body: "We want to redesign inference all the way down to silicon. Today that means hustling for customers, shipping constantly, and learning as we go. This is not an academic lab: the pressure to perform, grow, and win is real.",
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
    body: "Our handbook is public, including beliefs that may change. Writing clearly enough for other people to disagree with us is part of doing the work properly.",
  },
  {
    title: "High standards. Low ego.",
    body: "The work is technically demanding, but we do not hire people who need to be the smartest person in the room. Startups are humbling; good people change their minds quickly.",
  },
] as const;

/**
 * The separator is Cambridge itself: punts under Clare Bridge, drifting
 * slower than the page — the background-position eases against scroll,
 * so the photograph lags the text passing over it. Reduced motion (and
 * no slack in the crop) leaves it a still image.
 */
const Interlude = (): ReactElement => {
  const lineRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    const band = lineRef.current?.closest<HTMLElement>(".gr-careers-interlude");
    if (!band) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const DRIFT = 110; // px of image travel across the band's pass
    let raf = 0;
    const update = () => {
      raf = 0;
      const rect = band.getBoundingClientRect();
      const vh = window.innerHeight;
      /* -1 when the band enters from below, +1 as it leaves above. */
      const progress =
        (vh / 2 - (rect.top + rect.height / 2)) / ((vh + rect.height) / 2);
      const shift = Math.max(-1, Math.min(1, progress)) * DRIFT;
      band.style.backgroundPositionY = `calc(50% + ${shift.toFixed(1)}px)`;
    };
    const queue = () => {
      if (raf === 0) raf = requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", queue, { passive: true });
    window.addEventListener("resize", queue);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("scroll", queue);
      window.removeEventListener("resize", queue);
    };
  }, []);

  return (
    <Module bleed className="gr-careers-module gr-careers-interlude" index={2}>
      <p className="gr-careers-interlude-line" ref={lineRef}>
        <span>Gradiated</span>
        <span>Inference lab in Cambridge,&nbsp;UK</span>
      </p>
      {/* Film grain over the photograph. */}
      <Noise dust={0.25} opacity={0.14} size={1.4} />
    </Module>
  );
};

/**
 * The badge holds the centre; the reasons take the remaining sides —
 * left, right, and below. The whole fold blur-fades in once seen:
 * title first, then the card, then the orbiting reasons (the seen
 * class lands on the module so the title is choreographed too).
 */
const WhyOrbit = (): ReactElement => {
  const hostRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          host.classList.add("gr-careers-why--seen");
          io.disconnect();
        }
      },
      { threshold: 0.2 },
    );
    io.observe(host);
    return () => io.disconnect();
  }, []);

  /* The card shows at load: it starts lifted over the title (visible
     in the hero's sliver) and travels down into its orbit seat as the
     reader scrolls, revealing "Why Gradiated" from underneath. */
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (!window.matchMedia("(min-width: 60rem)").matches) return;
    const card = host.querySelector<HTMLElement>(".gr-idcard");
    const module = host.closest<HTMLElement>(".gr-careers-why-module");
    if (!card || !module) return;

    const LOAD_GAP = 200; // hero leaves this much of the fold on screen
    const PEEK = 120; // px of card visible at load
    const ARRIVE = 110; // module top at which the card is seated
    const INTRO_MS = 1000; // the card slides up into its peek on load
    let travel = 0;
    let uncoverAt = 40; // lift (px) below which the title is clear of the card
    let uncovered = false;
    let raf = 0;
    let introStart = 0;

    const measure = () => {
      const prev = card.style.transform;
      card.style.transform = "none";
      const moduleTop = module.getBoundingClientRect().top;
      const inner = card.getBoundingClientRect().top - moduleTop;
      card.style.transform = prev;
      travel = Math.max(0, inner - LOAD_GAP + PEEK);
      const title = module.querySelector(".gr-module-title");
      if (title) {
        const titleBottom = title.getBoundingClientRect().bottom - moduleTop;
        uncoverAt = Math.max(8, inner - titleBottom + 6);
      }
    };

    const update = () => {
      raf = 0;
      const vh = window.innerHeight;
      const top = module.getBoundingClientRect().top;
      const start = vh - LOAD_GAP;
      const p = Math.min(
        1,
        Math.max(0, (top - ARRIVE) / Math.max(1, start - ARRIVE)),
      );
      const eased = p * p * (3 - 2 * p);
      /* The load intro: the card starts below the fold's edge and
         slides up into its peek, then the scroll owns it. */
      if (introStart === 0) introStart = performance.now();
      const introP = Math.min(1, (performance.now() - introStart) / INTRO_MS);
      const introEase = 1 - (1 - introP) ** 3;
      const slide = (1 - introEase) * (PEEK + 60) * eased;
      card.style.transform = `translateY(${(-eased * travel + slide).toFixed(1)}px)`;
      /* The title stays hidden while the card's lift still covers it;
         once the card has scrolled clear, it blur-reveals (one way). */
      if (!uncovered && eased * travel < uncoverAt) {
        uncovered = true;
        host.classList.add("gr-careers-why--uncovered");
      }
      if (introP < 1) queue();
    };

    const queue = () => {
      if (raf === 0) raf = requestAnimationFrame(update);
    };
    const onResize = () => {
      measure();
      queue();
    };
    measure();
    update();
    window.addEventListener("scroll", queue, { passive: true });
    window.addEventListener("resize", onResize);
    return () => {
      cancelAnimationFrame(raf);
      card.style.transform = "";
      window.removeEventListener("scroll", queue);
      window.removeEventListener("resize", onResize);
    };
  }, []);

  return (
    <div className="gr-careers-why" ref={hostRef}>
      {reasons.map((reason, i) => (
        <div
          className={`gr-careers-reason gr-careers-why-${
            (["left", "right", "bottom"] as const)[i]
          }`}
          key={reason.body}
        >
          <h3 className="gr-careers-reason-title">{reason.title}</h3>
          <p className="gr-careers-reason-body gr-muted">{reason.body}</p>
        </div>
      ))}
      <BadgeCard />
    </div>
  );
};

/** Per-item parallax depth, px of travel across the board's pass. */
const DECIDE_DRIFTS = [-48, 38, -26, 56, -38, 44] as const;

/** The expectations that have poster art (the rest stay text notes). */
const BOARD_ART: Record<string, string> = {
  "The mission is long term. The cadence is not.":
    "/assets/careers-board/mission-cadence.jpg",
  "Specialists still work on the whole problem.":
    "/assets/careers-board/specialists-work.jpg",
  "Customers are part of the technical work.":
    "/assets/careers-board/customers-work.jpg",
  "We show our thinking.": "/assets/careers-board/show-thinking.jpg",
  "High standards. Low ego.": "/assets/careers-board/high-low.jpg",
};

/**
 * Before you decide, as a collage: the expectations scattered across
 * the fold like notes on a board, the handbook poster among them, each
 * drifting at its own rate against the scroll (timeless.co/type's
 * layout, in our materials). Reduced motion pins everything flat.
 */
const DecideBoard = (): ReactElement => {
  const hostRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const items = Array.from(
      host.querySelectorAll<HTMLElement>("[data-drift]"),
    );
    let raf = 0;
    const update = () => {
      raf = 0;
      const rect = host.getBoundingClientRect();
      const vh = window.innerHeight;
      const progress =
        (vh / 2 - (rect.top + rect.height / 2)) / ((vh + rect.height) / 2);
      const p = Math.max(-1, Math.min(1, progress));
      for (const item of items) {
        const depth = Number(item.dataset.drift) || 0;
        item.style.transform = `translateY(${(p * depth).toFixed(1)}px)`;
      }
    };
    const queue = () => {
      if (raf === 0) raf = requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", queue, { passive: true });
    window.addEventListener("resize", queue);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("scroll", queue);
      window.removeEventListener("resize", queue);
    };
  }, []);

  const print = (i: number, extra = "") => {
    const expectation = expectations[i];
    const art = BOARD_ART[expectation.title];
    return (
      <div
        className={`gr-careers-note gr-careers-print${extra ? ` ${extra}` : ""}`}
        data-drift={DECIDE_DRIFTS[i]}
        key={expectation.title}
      >
        <figure className="gr-careers-print-frame" tabIndex={0}>
          <img alt={expectation.title} src={art} />
        </figure>
        {/* The writing is collapsed under the print; on hover the well
            opens (nudging the card below) and the words blur-stream in,
            in the prelude's manner. */}
        <div aria-hidden className="gr-careers-print-well">
          <div>
            <p className="gr-careers-print-caption gr-muted">
              {expectation.body
                .trim()
                .split(/\s+/)
                .map((word, wi) => (
                  <span
                    key={wi}
                    style={{ "--w-delay": `${wi * 14}ms` } as CSSProperties}
                  >
                    {word}{" "}
                  </span>
                ))}
            </p>
          </div>
        </div>
        <p className="gr-visually-hidden">{expectation.body}</p>
      </div>
    );
  };

  /* Four columns, the title part of the collage: title + mission on
     the left, then specialists over customers, high-low over
     show-thinking, and the handbook standing alone on the right. */
  return (
    <div className="gr-careers-boardwrap">
      {/* Outside the scroller, so on narrow screens it holds still
          above the swipe row; on wide screens it is placed over the
          board's first column. */}
      <h2 className="gr-heading gr-careers-board-title">Before you decide</h2>
      <div className="gr-careers-board" ref={hostRef}>
        <div className="gr-careers-stack gr-careers-stack--1">{print(0)}</div>
        <div className="gr-careers-stack gr-careers-stack--2">
          {print(1, "gr-careers-print--round")}
          {print(2, "gr-careers-print--wide")}
        </div>
        <div className="gr-careers-stack gr-careers-stack--3">
          {print(4)}
          {print(3)}
        </div>
        <div className="gr-careers-stack gr-careers-stack--4">
          {/* The handbook print — the way into the library. */}
          <div
            className="gr-careers-note gr-careers-print gr-careers-print--round"
            data-drift={DECIDE_DRIFTS[5]}
          >
            <a className="gr-careers-print-frame" href="/handbook/">
              <img
                alt="Read the Gradiated handbook"
                src="/assets/careers-board/work-methods.jpg"
              />
            </a>
          </div>
        </div>
      </div>
    </div>
  );
};

export const CareersIndexPage = (): ReactElement => (
  <Substrate>
    <Nav />

    <Band>
      {/* The field sits behind the whole fold: the hero module's
          entrance wrapper would otherwise become the absolute anchor. */}
      <div className="gr-careers-hero-wrap">
        <div aria-hidden className="gr-careers-hero-field">
          <GradientASCII
            cellSize={15}
            colors={["#f6f3ec", "#e9b748", "#be5e31", "#1f3b50"]}
            fontFamily='"JetBrains Mono", ui-monospace, monospace'
            glow={0.15}
            gradientOpacity={0.55}
            grain={0.05}
            lightMode
            scale={1.25}
            shape="horizon"
          />
        </div>
        <Module
          bleed
          className="gr-module--top gr-careers-module gr-careers-hero"
          index={0}
        >
          <header className="gr-masthead gr-careers-head">
            <Reveal
              as="h1"
              by="word"
              className="gr-masthead-title gr-masthead-title--display"
            >
              Come make AI use less energy.
            </Reveal>
            <p className="gr-careers-lede gr-muted">
              Gradiated is a small research and engineering team focused on
              making open-model inference radically more efficient at every
              layer—from the models to inference, chips, and the data center.
            </p>
            <a
              className="gr-button gr-button--main gr-careers-jump"
              href="#open-roles"
            >
              See open roles
              <Arrow />
            </a>
          </header>
        </Module>
      </div>

      <Module
        className="gr-careers-module gr-careers-why-module"
        index={1}
        title="Why Gradiated"
      >
        <WhyOrbit />
      </Module>

      <Interlude />

      {/* The board carries its own title, inside the collage. */}
      <Module className="gr-careers-module" index={3}>
        <DecideBoard />
      </Module>

      <Module
        className="gr-careers-module gr-careers-roles-module"
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

                  {/* At the end of the row and centered on it, rather than
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
  /* The rail draws "back"; the page draws nothing above its content. */
  useRailBack({ href: "/careers/", label: "Careers" });
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
