// Runs at the start of `pnpm build` (plain `node`, using its built-in type stripping).
//
// Pulls every listed job posting from Gradiated's public Ashby job board and
// writes them to src/ashby-jobs.generated.ts in the `Job` shape from
// src/careers.ts. Ashby is the only source of job postings: to add, change or
// take down a job, do it in Ashby and redeploy.
//
// How an Ashby description maps onto the page:
//   - text above the first heading -> the summary under the job title
//   - each H2 heading -> a section; bullets/paragraphs -> its items
//   - the usual headings ("About Gradiated", "Why this role exists", "What you
//     will do", "Pay and equity", ...) fill the usual sections; any other
//     heading becomes an extra section
//   - an "Office" heading (e.g. "Several days a week") sets the office line
//     beside the title instead of adding a section
//   - a usual section missing from Ashby falls back to the shared copy in
//     careers-copy.ts where there is one (About, How we work, Pay, Interview)
//
// No API key needed: the job board API is public. If Ashby can't be reached
// the build fails on purpose, so Vercel keeps the last good deployment live
// rather than publishing a careers page with no jobs on it. The dev server
// (vite.config.ts) runs the sync on start and carries on if it is offline.

import { writeFile } from "node:fs/promises";
import { AshbyService } from "../src/ashby.ts";
import type { AshbyPosting } from "../src/ashby.ts";
import type { Job } from "../src/careers.ts";

declare const process: {
  env: Record<string, string | undefined>;
  exit(code: number): never;
};

const BOARD = process.env.ASHBY_JOB_BOARD ?? "gradiated";
const OUTPUT = new URL("../src/ashby-jobs.generated.ts", import.meta.url);

type ListSection =
  "purpose" | "responsibilities" | "problems" | "requirements" | "notFor";

/** Headings (normalised by `headingKey`) that fill a standard section. */
const STANDARD_SECTIONS: Record<
  string,
  ListSection | "about" | "howWeWork" | "pay" | "interviewSteps"
> = {
  "about gradiated": "about",
  "why this role exists": "purpose",
  "what you will do": "responsibilities",
  "what youll do": "responsibilities",
  "problems you may work on": "problems",
  "what we are looking for": "requirements",
  "what were looking for": "requirements",
  "this role is not for you if": "notFor",
  "how we work": "howWeWork",
  "pay and equity": "pay",
  "interview process": "interviewSteps",
};

/** Headings that set the office line beside the title instead of a section. */
const OFFICE_HEADINGS = new Set(["office", "office days", "in the office"]);

/** Ashby employment types as schema.org JobPosting values. */
const EMPLOYMENT_TYPES: Record<string, string> = {
  FullTime: "FULL_TIME",
  PartTime: "PART_TIME",
  Intern: "INTERN",
  Contract: "CONTRACTOR",
  Temporary: "TEMPORARY",
};

const ENTITIES: Record<string, string> = {
  "&nbsp;": " ",
  "&amp;": "&",
  "&lt;": "<",
  "&gt;": ">",
  "&quot;": '"',
  "&#39;": "'",
  "&#039;": "'",
  "&apos;": "'",
};

/** HTML fragment -> plain text on one line. */
const textOf = (html: string): string =>
  html
    .replace(/<br\s*\/?>/gi, " ")
    .replace(/<[^>]+>/g, "")
    .replace(
      /&nbsp;|&amp;|&lt;|&gt;|&quot;|&#0?39;|&apos;/g,
      (entity) => ENTITIES[entity],
    )
    .replace(/&#(\d+);/g, (_, code: string) =>
      String.fromCharCode(Number(code)),
    )
    .replace(/\s+/g, " ")
    .trim();

/** Bullets and paragraphs in document order; a paragraph inside a bullet is part of it. */
const itemsIn = (html: string): string[] =>
  [...html.matchAll(/<(li|p)[^>]*>([\s\S]*?)<\/\1>/gi)]
    .map((match) => textOf(match[2]))
    .filter(Boolean);

const slugify = (title: string): string =>
  title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");

const headingKey = (heading: string): string =>
  heading
    .toLowerCase()
    .replace(/[^a-z ]/g, "")
    .replace(/\s+/g, " ")
    .trim();

const toJob = (posting: AshbyPosting): Job => {
  const [introHtml, ...sectionHtml] = (posting.descriptionHtml ?? "").split(
    /<h2[^>]*>/i,
  );

  const job: Job = {
    slug: slugify(posting.title),
    ashbyJobPostingId: posting.id,
    datePosted: posting.publishedAt?.slice(0, 10) || undefined,
    title: posting.title,
    employmentType: EMPLOYMENT_TYPES[posting.employmentType ?? ""],
    workplace: posting.workplaceType === "Remote" ? "REMOTE" : "IN_PERSON",
    team: posting.team || undefined,
    location: [
      posting.location,
      ...(posting.secondaryLocations ?? []).map((l) => l.location),
    ]
      .filter(Boolean)
      .join(", "),
    summary: itemsIn(introHtml).join(" "),
    purpose: [],
    responsibilities: [],
    problems: [],
    requirements: [],
    notFor: [],
  };
  const extraSections: NonNullable<Job["extraSections"]> = [];

  for (const section of sectionHtml) {
    const [headingHtml, bodyHtml = ""] = section.split(/<\/h2>/i);
    const heading = textOf(headingHtml);
    const key = headingKey(heading);
    const items = itemsIn(bodyHtml);
    if (!heading || items.length === 0) continue;

    // An "Office" heading sets the office line beside the title (e.g. "Several
    // days a week") rather than adding a section.
    if (OFFICE_HEADINGS.has(key)) {
      job.officeDays = items.join(" ");
      continue;
    }

    const standard = STANDARD_SECTIONS[key];
    if (standard) job[standard] = items;
    else extraSections.push({ title: heading, items });
  }
  if (extraSections.length > 0) job.extraSections = extraSections;

  // No intro text in Ashby: fall back to the first line of the description, then
  // to the title. The summary is also the page's meta description, which the SEO
  // check requires, so it is never left empty.
  job.summary ||=
    job.purpose[0] ??
    job.responsibilities[0] ??
    job.requirements[0] ??
    extraSections[0]?.items[0] ??
    `${posting.title} at Gradiated.`;

  return job;
};

/**
 * Every listed posting gets a page, however much of the description is filled
 * in. Titles, slugs and summaries must be unique (the SEO check fails on
 * duplicates), so a clash gets the location, a number or the title added.
 */
const toUniqueJobs = (postings: AshbyPosting[]): Job[] => {
  const titles = new Set<string>();
  const slugs = new Set<string>();
  const summaries = new Set<string>();

  return postings.map((posting) => {
    const job = toJob(posting);

    const baseTitle = job.title;
    if (titles.has(job.title) && job.location) {
      job.title = `${baseTitle} (${job.location})`;
    }
    for (let n = 2; titles.has(job.title); n++) {
      job.title = `${baseTitle} (${job.location ? `${job.location}, ` : ""}${n})`;
    }
    titles.add(job.title);

    const baseSlug = job.slug;
    for (let n = 2; slugs.has(job.slug); n++) job.slug = `${baseSlug}-${n}`;
    slugs.add(job.slug);

    // The title is unique by now, so prefixing it makes the summary unique too.
    if (summaries.has(job.summary))
      job.summary = `${job.title} at Gradiated: ${job.summary}`;
    summaries.add(job.summary);

    return job;
  });
};

try {
  const jobs = toUniqueJobs(await new AshbyService().listedPostings(BOARD));
  await writeFile(
    OUTPUT,
    [
      "// Generated by scripts/sync-ashby-jobs.ts at build time. Do not edit by hand:",
      "// edit the job in Ashby.",
      'import type { Job } from "./careers";',
      "",
      `export const ashbyJobs: Job[] = ${JSON.stringify(jobs, null, 2)};`,
      "",
    ].join("\n"),
  );
  console.log(`Synced ${jobs.length} job postings from Ashby (${BOARD}).`);
} catch (error) {
  const reason = `Could not load job postings from Ashby (${BOARD}): ${(error as Error).message}`;
  // The dev server asks for a best-effort sync; a build needs the real list.
  if (process.env.ASHBY_SYNC_OPTIONAL === "1") {
    console.warn(`${reason}. Keeping src/ashby-jobs.generated.ts as it is.`);
  } else {
    console.error(reason);
    process.exit(1);
  }
}
