import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import type { ReactElement } from "react";
import { jobs } from "../careers";

const roleLinkClass =
  "group grid grid-cols-[minmax(0,1fr)_auto] gap-8 text-ink transition-colors hover:text-accent max-site:gap-4";

export const CareersPage = (): ReactElement => (
  <main>
    <section
      className="px-7 pb-32 pt-28 max-site:px-[22px] max-site:pb-24 max-site:pt-20"
      aria-labelledby="roles-heading"
    >
      <h1
        className="mb-20 mt-0 font-newsreader text-[clamp(58px,8vw,108px)] font-normal leading-[0.9] tracking-display max-site:mb-14 max-site:text-[52px]"
        id="roles-heading"
      >
        We are hiring.
      </h1>
      <div className="grid gap-16 max-site:gap-12">
        {jobs.map((job) => (
          <Link
            className={roleLinkClass}
            key={job.slug}
            to={`/careers/${job.slug}/`}
          >
            <div>
              <h3 className="m-0 font-newsreader text-[clamp(30px,4vw,48px)] font-normal leading-none tracking-heading">
                {job.title}
              </h3>
              <p className="mb-0 mt-3 max-w-[690px] text-[15px] leading-[1.6] text-muted">
                {job.summary}
              </p>
              <div className="mt-5 flex flex-wrap gap-x-6 gap-y-2 font-libre text-label font-medium uppercase tracking-label text-muted">
                <span>{job.team}</span>
                <span>{job.location}</span>
              </div>
            </div>
            <ArrowRight
              aria-hidden="true"
              className="h-7 w-7 self-start transition-transform group-hover:translate-x-1"
              strokeWidth={1.25}
            />
          </Link>
        ))}
      </div>
    </section>
  </main>
);
