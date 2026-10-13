// Runs at the start of `pnpm build` (plain `node`, using its built-in type stripping).
//
// Pulls every listed job posting from Gradiated's public Ashby job board and
// writes them to src/ashby-jobs.generated.ts in the same shape as the jobs in
// src/careers.ts, so they render with the exact same page and styling.
//
// Jobs already written natively in careers.ts (matched by ashbyJobPostingId or
// slug) keep their native copy; careers.ts filters the duplicates out.
//
// How an Ashby description maps onto the page:
//   - text above the first heading      -> the summary under the job title
//   - each H2 heading                   -> a section; bullets/paragraphs -> its items
//   - the usual headings ("Why this role exists", "What you will do", ...)
//     fill the usual sections; any other heading becomes an extra section
//   - "About Gradiated" and "Pay and equity" are ignored: every job uses the
//     shared copy in careers-copy.ts
//
// No API key needed: the job board API is public. If Ashby can't be reached
// the last generated file is kept, so a build never fails because of it.

import { writeFile } from "node:fs/promises";
import { AshbyService } from "../src/ashby.ts";
import type { AshbyPosting } from "../src/ashby.ts";
import type { Job } from "../src/careers.ts";

declare const process: { env: Record<string, string | undefined> };

const BOARD = process.env.ASHBY_JOB_BOARD ?? "gradiated";
const OUTPUT = new URL("../src/ashby-jobs.generated.ts", import.meta.url);

type ListSection =
  "purpose" | "responsibilities" | "problems" | "requirements" | "notFor";

/** Headings (normalised by `headingKey`) that fill a standard section. */
const STANDARD_SECTIONS: Record<
  string,
  ListSection | "howWeWork" | "interviewSteps"
> = {
  "why this role exists": "purpose",
  "what you will do": "responsibilities",
  "what youll do": "responsibilities",
  "problems you may work on": "problems",
  "what we are looking for": "requirements",
  "what were looking for": "requirements",
  "this role is not for you if": "notFor",
  "how we work": "howWeWork",
  "interview process": "interviewSteps",
};
/** Headings whose content comes from the shared copy instead. */
const SHARED_SECTIONS = new Set(["about gradiated", "pay and equity"]);

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

const matchesOf = (html: string, tag: string): string[] =>
  [...html.matchAll(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)</${tag}>`, "gi"))]
    .map((match) => textOf(match[1]))
    .filter(Boolean);

/** List items if there are any, otherwise paragraphs. */
const itemsIn = (html: string): string[] => {
  const listItems = matchesOf(html, "li");
  return listItems.length > 0 ? listItems : matchesOf(html, "p");
};

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
    if (!heading || SHARED_SECTIONS.has(key) || items.length === 0) continue;

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

    if (titles.has(job.title) && job.location)
      job.title = `${job.title} (${job.location})`;
    titles.add(job.title);

    const baseSlug = job.slug;
    for (let n = 2; slugs.has(job.slug); n++) job.slug = `${baseSlug}-${n}`;
    slugs.add(job.slug);

    if (summaries.has(job.summary))
      job.summary = `${posting.title} at Gradiated: ${job.summary}`;
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
      "// edit the job in Ashby, or copy it into careers.ts to manage it natively.",
      'import type { Job } from "./careers";',
      "",
      `export const ashbyJobs: Job[] = ${JSON.stringify(jobs, null, 2)};`,
      "",
    ].join("\n"),
  );
  console.log(`Synced ${jobs.length} job postings from Ashby (${BOARD}).`);
} catch (error) {
  console.warn(
    `Ashby job sync skipped, keeping the existing file: ${(error as Error).message}`,
  );
}
