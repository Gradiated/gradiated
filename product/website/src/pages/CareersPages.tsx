import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { CSSProperties, ReactElement } from "react";
import {
  Arrow,
  Band,
  BadgeCard,
  BounceCards,
  CollageHero,
  type CollageLayer,
  EnergyField,
  type EnergyFieldProps,
  Footer,
  Module,
  Nav,
  Reveal,
  SectionFab,
  Substrate,
} from "../components/design";
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

const ASSETS = "/assets/careers";

/** A remote role says so in its location, even if Ashby's location doesn't. */
const locationOf = (job: Job): string =>
  job.workplace === "REMOTE" && !/remote/i.test(job.location)
    ? `Remote, ${job.location}`
    : job.location;

const TITLE = ["Come make AI", "use less energy"];

const COLLAGE: CollageLayer[] = [
  {
    drift: 0.3,
    file: "hero-aerial.webp",
    from: { r: 3, x: 6, y: -6 },
    left: 2274,
    top: 0,
    width: 652,
  },
  {
    drift: 0.22,
    file: "hero-monitor.webp",
    from: { r: 2, x: 6, y: -3 },
    left: 1933,
    top: 334,
    width: 993,
  },
  {
    drift: 0.15,
    file: "hero-grass.webp",
    from: { r: -1.5, x: -2, y: 14 },
    left: 17,
    top: 438,
    width: 2910,
  },
  {
    drift: 0.1,
    file: "hero-heatmap.webp",
    from: { r: -4, x: -8, y: 12 },
    left: -2,
    top: 1715,
    width: 1042,
  },
  {
    drift: 0.08,
    file: "hero-paper.webp",
    from: { r: 2, x: 3, y: 16 },
    left: 538,
    top: 967,
    width: 2389,
  },
  {
    drift: 0.04,
    file: "hero-laptop.webp",
    from: { r: 1.5, x: 5, y: 6 },
    left: 996,
    top: 801,
    width: 1914,
  },
];

const reasons = [
  {
    body: "We put the latest open-weight models into production, develop new inference techniques, and follow performance all the way down to silicon. Nobody arrives knowing every layer, so we run internal lectures, work through problems together, and expect everyone to teach what they know.",
    icon: "icon-cake.webp",
    title: "One problem. Every layer.",
  },
  {
    body: "You will work directly with a small founding team that has built PostHog into a unicorn and a developer brand people love, led AI engineering, and gone deep in mathematics, semiconductors, and quantum computing.",
    icon: "icon-rewind.webp",
    title: (
      <>
        Half a million customers later,
        <br />
        we’re starting again.
      </>
    ),
  },
  {
    body: "We are engineering-led and trust-led. We want customers to find us through excellent work, useful writing, and other builders telling them about us. The aim is lasting technical advantage, not a brief turn in the hype cycle.",
    icon: "icon-star.webp",
    title: "Build a reputation that compounds.",
  },
];

// Each card's ground and ink: the ink sets the writing, the texture and its
// grain, except on a light ground, where dark grain reads as dirt.
const expectations = [
  {
    body: "We do not develop technology in isolation and look for a use later. Customer workloads tell us what matters, what is wasteful, and what to build next.",
    ground: "#1d4b38",
    ink: "#c9e89f",
    title: "Customers are part of the technical work.",
  },
  {
    body: "Nobody knows every layer, but ‘that is not my area’ cannot become a reason to stop. You will be expected to learn outside your discipline and help wherever progress is blocked.",
    ground: "#472f96",
    ink: "#dce7f5",
    title: "Specialists still work on the whole problem.",
  },
  {
    body: "The work is technically demanding, but we do not hire people who need to be the smartest person in the room. Startups are humbling; good people change their minds quickly.",
    ground: "#18181b",
    ink: "#efe3c3",
    title: (
      <>
        High standards.
        <br />
        Low ego.
      </>
    ),
  },
  {
    body: "We want to redesign inference all the way down to silicon. Today that means hustling for customers, shipping constantly, and learning as we go. This is not an academic lab: the pressure to perform, grow, and win is real.",
    ground: "#1f3b50",
    ink: "#8ed3f2",
    title: "The mission is long term. The cadence is not.",
    wide: true,
  },
  {
    body: "Our handbook is public, including beliefs that may change. Writing clearly enough for other people to disagree with us is part of doing the work properly.",
    grain: "#ffffff",
    ground: "#efe3c3",
    ink: "#1d4b38",
    title: "We show our thinking.",
  },
];

type Texture = Omit<EnergyFieldProps, "angle" | "ground" | "ink">;

const DOTS: Texture = {
  blur: 0,
  density: 1.4,
  noise: 0.15,
  shape: "bits",
  size: 2,
};

const SPIRAL: Texture = {
  blur: 2,
  density: 0.7,
  length: 7,
  noise: 0.3,
  shape: "spiral",
  size: 1,
};

const LINES: Texture[] = [
  { blur: 6, density: 0.8, length: 14, noise: 0.35, shape: "bars" },
  { blur: 2.5, density: 0.9, length: 10, noise: 0.3, shape: "bars" },
  { blur: 1, density: 0.8, length: 14, noise: 0.85, shape: "bars" },
];

const shuffle = <T,>(items: T[]): T[] => {
  const copy = [...items];
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }

  return copy;
};

/** Two cards of dots, one spiral and two of lines, wherever they fall, each
    flowing its own way. */
const drawTextures = (count: number): Array<Texture & { angle: number }> => {
  const textures = [DOTS, DOTS, SPIRAL, ...shuffle(LINES)].slice(0, count);

  return shuffle(textures).map((texture) => ({
    ...texture,
    angle: Math.round(Math.random() * 360),
  }));
};

/** "waiting" once the element is being watched, "seen" when it scrolls into
    view. */
const useReveal = <T extends HTMLElement>() => {
  const ref = useRef<T>(null);
  const [state, setState] = useState<"seen" | "waiting">();

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    setState("waiting");
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        setState("seen");
        observer.disconnect();
      },
      { rootMargin: "0px 0px -15% 0px" },
    );
    observer.observe(node);

    return () => observer.disconnect();
  }, []);

  return { ref, state };
};

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
    <Module bleed className="gr-careers-module gr-careers-interlude" index={3}>
      <p className="gr-careers-interlude-line" ref={lineRef}>
        <span>Gradiated</span>
        <span>Inference lab in Cambridge,&nbsp;UK</span>
      </p>
      {/* Film grain over the photograph. */}
      <Noise dust={0.25} opacity={0.14} size={1.4} />
    </Module>
  );
};

const Why = (): ReactElement => {
  const { ref, state } = useReveal<HTMLDivElement>();

  return (
    <div className="gr-careers-why" data-reveal={state} ref={ref}>
      <div className="gr-careers-why-lead">
        <h2 className="gr-section-title">Why Gradiated</h2>
        <BadgeCard />
      </div>
      <div className="gr-careers-reasons">
        {reasons.map((reason, index) => (
          <div
            className="gr-careers-reason"
            key={reason.body}
            style={{ "--i": index } as CSSProperties}
          >
            <img
              alt=""
              className="gr-careers-reason-icon"
              src={`${ASSETS}/${reason.icon}`}
            />
            <div>
              <h3 className="gr-careers-reason-title">{reason.title}</h3>
              <p className="gr-careers-reason-body gr-muted">{reason.body}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

/** The element's width in px, kept current; 0 until it has been measured. */
const useWidth = <T extends HTMLElement>() => {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    const observer = new ResizeObserver(([entry]) =>
      setWidth(Math.round(entry.contentRect.width)),
    );
    observer.observe(node);

    return () => observer.disconnect();
  }, []);

  return { ref, width };
};

const Decide = (): ReactElement => {
  const { ref, state } = useReveal<HTMLUListElement>();
  const fan = useReveal<HTMLDivElement>();
  const frame = useWidth<HTMLDivElement>();
  const [textures] = useState(() => drawTextures(expectations.length));
  const [hovered, setHovered] = useState<number>();
  const [needed, setNeeded] = useState(0);

  // The tallest card's writing, so no card cuts its text off at this width.
  useLayoutEffect(() => {
    const cards = frame.ref.current?.querySelectorAll<HTMLElement>(
      ".gr-careers-tile--fan",
    );
    if (!cards?.length) return;

    let tallest = 0;
    for (const card of cards) {
      const style = getComputedStyle(card);
      const text = [...card.children].filter(
        (child): child is HTMLElement =>
          child instanceof HTMLElement && child.tagName !== "CANVAS",
      );
      tallest = Math.max(
        tallest,
        parseFloat(style.paddingTop) +
          parseFloat(style.paddingBottom) +
          parseFloat(style.rowGap) * (text.length - 1) +
          text.reduce((sum, child) => sum + child.offsetHeight, 0),
      );
    }
    setNeeded(Math.ceil(tallest));
  }, [frame.width, fan.state]);

  const card = (index: number) => {
    const { body, ground, ink, title } = expectations[index];
    const grain =
      "grain" in expectations[index] ? expectations[index].grain : undefined;

    return (
      <>
        <EnergyField
          {...textures[index]}
          className="gr-careers-tile-field"
          ground={ground}
          ink={ink}
          moving={hovered === index}
          noiseColor={grain ?? ink}
          speed={0.5}
        />
        <h3 className="gr-careers-tile-title">{title}</h3>
        <p className="gr-careers-tile-body">{body}</p>
      </>
    );
  };

  // The five cards fill the band, overlapping more as it narrows rather
  // than growing too slim to read.
  const cardWidth = Math.min(340, Math.max(280, Math.round(frame.width * 0.3)));
  const cardHeight = Math.max(Math.round(cardWidth * 1.1), needed);
  const spread = (frame.width - cardWidth) / (expectations.length - 1);

  return (
    <>
      <div className="gr-careers-decide-head">
        <h2 className="gr-section-title">Before you decide</h2>
        <div className="gr-careers-handbook">
          <img alt="" src={`${ASSETS}/icon-book.webp`} />
          <p>
            <a className="gr-link" href="/handbook/">
              Read our Handbook
            </a>{" "}
            if you’d like to learn more about how we get work done.
          </p>
        </div>
      </div>

      <div
        className="gr-careers-fan"
        ref={(node) => {
          frame.ref.current = node;
          fan.ref.current = node;
        }}
        style={{ height: cardHeight + 96 }}
      >
        {frame.width > 0 && fan.state !== "waiting" ? (
          <BounceCards
            animationDelay={0.1}
            borderWidth={0}
            bounciness={0.15}
            cardHeight={cardHeight}
            cards={expectations.map(({ body, ground, ink }, index) => (
              <div
                className="gr-careers-tile gr-careers-tile--fan"
                key={body}
                style={{ "--ink": ink, background: ground } as CSSProperties}
              >
                {card(index)}
              </div>
            ))}
            cardWidth={cardWidth}
            fromScale={0.92}
            containerHeight="100%"
            containerWidth="100%"
            hoverScale={1.04}
            onHoverChange={(index) => setHovered(index < 0 ? undefined : index)}
            pushDistance={cardWidth * 0.45}
            radius={5}
            rotation={2.5}
            spread={spread}
          />
        ) : null}
      </div>

      <div className="gr-careers-tiles-frame">
        <ul className="gr-careers-tiles" data-reveal={state} ref={ref}>
          {expectations.map(({ body, ground, ink, wide }, index) => (
            <li
              className={`gr-careers-tile${wide ? " gr-careers-tile--wide" : ""}`}
              key={body}
              style={
                {
                  "--i": index,
                  "--ink": ink,
                  background: ground,
                } as CSSProperties
              }
            >
              {card(index)}
            </li>
          ))}
        </ul>
      </div>
    </>
  );
};

export const CareersIndexPage = (): ReactElement => (
  <Substrate>
    <Nav />

    <Band>
      <CollageHero
        canvas={{ height: 2120, width: 2926 }}
        className="gr-module--careers-hero"
        layers={COLLAGE}
        path={ASSETS}
      >
        <h1 className="gr-collage-hero-title">
          {TITLE.map((line, index) => (
            <span className="gr-hero-line" key={line}>
              <Reveal by="word" from={index * 3}>
                {line}
              </Reveal>
            </span>
          ))}
        </h1>
        <p className="gr-body gr-muted">
          Gradiated is a small research and engineering team focused on making
          open-model inference radically more efficient at every layer—from the
          models to inference, chips, and the data center.
        </p>
        <div className="gr-page-hero-actions">
          <a className="gr-button gr-button--main" href="#open-roles">
            See open roles
            <Arrow />
          </a>
        </div>
      </CollageHero>

      <Module className="gr-careers-module gr-careers-why-module" index={1}>
        <Why />
      </Module>

      <Module className="gr-careers-decide-module" index={2}>
        <Decide />
      </Module>

      <Interlude />

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
