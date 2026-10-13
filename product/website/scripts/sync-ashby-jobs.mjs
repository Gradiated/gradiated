// Runs at the start of `pnpm build`.
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
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const BOARD = process.env.ASHBY_JOB_BOARD ?? "gradiated";
const outputPath = join(dirname(fileURLToPath(import.meta.url)), "..", "src", "ashby-jobs.generated.ts");

const decode = (text) =>
  text
    .replace(/<br\s*\/?>/gi, " ")
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;|&#039;|&apos;/g, "'")
    .replace(/&#(\d+);/g, (_, code) => String.fromCharCode(Number(code)))
    .replace(/\s+/g, " ")
    .trim();

/** List items if there are any, otherwise paragraphs. */
const itemsIn = (html) => {
  const listItems = [...html.matchAll(/<li[^>]*>([\s\S]*?)<\/li>/gi)].map((m) => decode(m[1]));
  if (listItems.length > 0) return listItems.filter(Boolean);
  return [...html.matchAll(/<p[^>]*>([\s\S]*?)<\/p>/gi)].map((m) => decode(m[1])).filter(Boolean);
};

const slugify = (title) =>
  title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");

const key = (heading) => heading.toLowerCase().replace(/[^a-z ]/g, "").replace(/\s+/g, " ").trim();

const KNOWN = {
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
const IGNORED = new Set(["about gradiated", "pay and equity"]);

const toJob = (posting) => {
  const html = posting.descriptionHtml ?? "";
  const [intro, ...rest] = html.split(/<h2[^>]*>/i);

  const job = {
    slug: slugify(posting.title),
    ashbyJobPostingId: posting.id,
    datePosted: (posting.publishedAt ?? "").slice(0, 10) || undefined,
    title: posting.title,
    team: posting.team || undefined,
    location: [posting.location, ...(posting.secondaryLocations ?? []).map((l) => l.location)]
      .filter(Boolean)
      .join(", "),
    summary: itemsIn(intro).join(" "),
    purpose: [],
    responsibilities: [],
    problems: [],
    requirements: [],
    notFor: [],
    extraSections: [],
  };

  for (const block of rest) {
    const [headingHtml, bodyHtml = ""] = block.split(/<\/h2>/i);
    const heading = decode(headingHtml);
    const items = itemsIn(bodyHtml);
    const k = key(heading);
    if (!heading || IGNORED.has(k) || items.length === 0) continue;
    if (KNOWN[k]) job[KNOWN[k]] = items;
    else job.extraSections.push({ title: heading, items });
  }

  // No intro text in Ashby: fall back to the first line of the description, then
  // to the title. The summary is also the page's meta description, which the SEO
  // check requires, so it is never left empty.
  if (!job.summary) {
    job.summary =
      job.purpose[0] ??
      job.responsibilities[0] ??
      job.requirements[0] ??
      job.extraSections[0]?.items[0] ??
      `${posting.title} at Gradiated.`;
  }
  if (job.extraSections.length === 0) delete job.extraSections;
  return job;
};

try {
  const res = await fetch(`https://api.ashbyhq.com/posting-api/job-board/${BOARD}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const { jobs = [] } = await res.json();
  // Every listed posting gets a page, however much of the description is filled
  // in. Slugs and summaries must be unique (the SEO check fails on duplicates),
  // so clashes get the title appended or a number added.
  const ashbyJobs = [];
  const slugs = new Set();
  const titles = new Set();
  const summaries = new Set();
  for (const posting of jobs.filter((p) => p.isListed !== false)) {
    const job = toJob(posting);
    if (titles.has(job.title) && job.location) job.title = `${job.title} (${job.location})`;
    titles.add(job.title);
    let slug = job.slug;
    for (let n = 2; slugs.has(slug); n++) slug = `${job.slug}-${n}`;
    job.slug = slug;
    slugs.add(slug);
    if (summaries.has(job.summary)) job.summary = `${posting.title} at Gradiated: ${job.summary}`;
    summaries.add(job.summary);
    ashbyJobs.push(job);
  }

  await writeFile(
    outputPath,
    [
      "// Generated by scripts/sync-ashby-jobs.mjs at build time. Do not edit by hand:",
      "// edit the job in Ashby, or copy it into careers.ts to manage it natively.",
      'import type { Job } from "./careers";',
      "",
      `export const ashbyJobs: Job[] = ${JSON.stringify(ashbyJobs, null, 2)};`,
      "",
    ].join("\n"),
  );
  console.log(`Synced ${ashbyJobs.length} job postings from Ashby (${BOARD}).`);
} catch (error) {
  console.warn(`Ashby job sync skipped, keeping the existing file: ${error.message}`);
}
