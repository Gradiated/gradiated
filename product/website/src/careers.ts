import { ashbyJobs } from "./ashby-jobs.generated";

/**
 * A job posting. Every posting comes from Ashby: scripts/sync-ashby-jobs.ts pulls
 * the listed jobs at build time into ashby-jobs.generated.ts. To add, change or
 * take down a job, do it in Ashby and redeploy the site.
 */
export type Job = {
  /** The job posting in Ashby that applications go to. */
  ashbyJobPostingId: string;
  /** Sections from an Ashby description whose heading is not one of the standard ones. */
  extraSections?: { title: string; items: string[] }[];
  /** Sections from Ashby; when missing, the shared copy in careers-copy.ts is used. */
  about?: string[];
  pay?: string[];
  slug: string;
  datePosted?: string;
  /** schema.org employment type; full-time when absent. */
  employmentType?: string;
  foundingContext?: string;
  officeDays?: string;
  /** In person when absent. */
  workplace?: "REMOTE" | "IN_PERSON";
  howWeWork?: string[];
  interviewSteps?: string[];
  title: string;
  team?: string;
  location: string;
  summary: string;
  purpose: string[];
  responsibilities: string[];
  problems: string[];
  requirements: string[];
  notFor: string[];
};

export const jobs: Job[] = ashbyJobs;
