/**
 * The prose a job posting carries that is not about the job.
 *
 * It lived inside JobPage.tsx, which meant the design system's version of the
 * page could only have it by copying it — and a paragraph about pay that
 * exists twice is a paragraph that will eventually say two different things.
 * Both pages read it from here instead.
 */

export const aboutGradiated = [
  "Gradiated is a research lab focused on inference. We co-design software and hardware for efficiently serving open-weight models.",
  "Our goal is to maximize intelligence per joule. We work across model behavior, software, systems, and silicon to find better ways to run models.",
  "We start by thinking about the model as a mathematical function, and map that out onto hardware and then build software on top of that which is custom to each model. This maximizes performance and removes wasted abstractions.",
  "We are early. You will help set the technical direction and the way the company works.",
];

export const howWeWork = [
  "We like to experiment a lot and do the hard thing even if it's likely to fail.",
  "We work in the office on Monday, Wednesday, Friday. We value working in person to solve hard problems, but are also flexible, some of the team work abroad for short periods.",
];

export const payAndEquity = [
  "We offer top-of-market compensation, with significant equity.",
  "We pay at the top of the market because talent density is what allows us to build the most efficient inference. We want a small team of exceptional people who have fun solving hard problems together.",
];

export const interviewSteps = [
  "A 60-minute call about your goals and the role.",
  "We get together in person and talk through the problems we will work on.",
  "A paid in-person working session, so we can get to know you and you can meet the team.",
  "References and an offer decision.",
];

/** The facts every posting states, in the order the page states them. */
export const COMPENSATION = "Top-of-market compensation + significant equity";
export const OFFICE_DAYS = "Mon, Wed, Fri";

export const applyHrefFor = (title: string): string =>
  `mailto:team@gradiated.com?subject=${encodeURIComponent(`Application: ${title}`)}`;
