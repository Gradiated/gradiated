import {
  type CSSProperties,
  type ReactElement,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  Arrow,
  Band,
  CollageHero,
  type CollageLayer,
  Features,
  Footer,
  Module,
  Nav,
  Reveal,
  Substrate,
} from "../components/design";
import { MemberGrid } from "../components/team/MemberCard";
import { team } from "../team";
import "../styles/index.css";

const ASSETS = "/assets/about";

const BOOKING_URL = "https://cal.com/team/gradiated/chat-with-gradiated";

const TITLE = ["From PostHog,", "for Inference"];

const COLLAGE: CollageLayer[] = [
  {
    drift: 0.2,
    file: "hero-poster.webp",
    from: { r: -4, x: -6, y: 12 },
    left: 0,
    top: 1642,
    width: 1115,
  },
  {
    drift: 0.3,
    file: "hero-map.webp",
    from: { r: 3, x: 4, y: -8 },
    left: 1486,
    top: 0,
    width: 1443,
  },
  {
    drift: 0.12,
    file: "hero-paper.webp",
    from: { r: -2, x: -3, y: 16 },
    left: 0,
    top: 1170,
    width: 2245,
  },
  {
    drift: 0.05,
    file: "hero-photo.webp",
    from: { r: 1.5, x: 7, y: 2 },
    left: 1178,
    top: 8,
    width: 1750,
  },
];

const PRINCIPLES = [
  {
    body: "Gradiated is a brand owned by PostHog Inc. It carries the same builder-first approach into the infrastructure underneath AI products.",
    icon: `${ASSETS}/icon-company.webp`,
    title: "One company",
  },
  {
    body: "Inference rewards depth. Gradiated exists so one team can concentrate on models, serving systems, and hardware without diluting that work.",
    icon: `${ASSETS}/icon-focus.webp`,
    title: "A distinct focus",
  },
  {
    body: "Make open-model inference more affordable by improving the whole stack, from the API developers use to the systems and silicon that run it.",
    icon: `${ASSETS}/icon-goal.webp`,
    title: "A practical goal",
  },
];

const DIES = ["substrate", "solder", "silicon", "metal", "underfill", "cover"];

/** "waiting" once the row is being watched, "seen" when it scrolls into view. */
const useReveal = () => {
  const ref = useRef<HTMLDivElement>(null);
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

export const AboutPage = (): ReactElement => {
  const dies = useReveal();

  return (
    <Substrate>
      <Nav />

      <Band>
        <CollageHero
          canvas={{ height: 2120, width: 2928 }}
          className="gr-module--about-hero"
          layers={COLLAGE}
          path={ASSETS}
        >
          <h1 className="gr-collage-hero-title">
            {TITLE.map((line, index) => (
              <span className="gr-hero-line" key={line}>
                <Reveal by="word" from={index * 2}>
                  {line}
                </Reveal>
              </span>
            ))}
          </h1>
          <p className="gr-body gr-muted">
            Gradiated began inside PostHog, from a question about what AI
            builders would need next: better access to efficient, dependable
            inference. PostHog created Gradiated as a focused brand for
            answering that question across software, systems, and hardware.
          </p>
          <div className="gr-page-hero-actions">
            <a className="gr-button gr-button--main" href={BOOKING_URL}>
              Talk to us
              <Arrow />
            </a>
            <a className="gr-button gr-button--secondary" href="/careers/">
              Join our team
              <Arrow />
            </a>
          </div>
        </CollageHero>

        <Module className="gr-module--about-why" index={1}>
          <Features items={PRINCIPLES} />

          <div
            aria-label="The layers of a chip package, from its substrate up to its lid"
            className="gr-about-dies"
            data-reveal={dies.state}
            ref={dies.ref}
            role="img"
          >
            {DIES.map((die, index) => (
              <span
                className="gr-about-die"
                key={die}
                style={{ "--i": index } as CSSProperties}
              >
                <img alt="" loading="lazy" src={`${ASSETS}/die-${die}.webp`} />
              </span>
            ))}
          </div>
        </Module>

        <Module className="gr-module--about-team" index={2}>
          <div className="gr-about-team-head">
            <h2 className="gr-section-title">The Team</h2>
            <a className="gr-button gr-button--secondary" href="/team/">
              Meet the team
              <Arrow />
            </a>
          </div>
          <MemberGrid
            className="gr-member-grid--about"
            detail="none"
            members={team}
          />

          <div className="gr-about-silicon">
            <h2 className="gr-section-title">
              Going down to silicon
              <br />
              is the imperative.
            </h2>
            <p className="gr-body gr-muted">
              Driving down tokens per joule we believe is the greatest impact we
              can have on mankind as it is the best way to empower every person
              and every system to research, build, understand and do more.
            </p>
          </div>
        </Module>
      </Band>

      <Band>
        <Footer index={3} />
      </Band>
    </Substrate>
  );
};
