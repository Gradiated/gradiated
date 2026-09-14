import { ArrowLeft, ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import type { ReactElement, ReactNode } from "react";
import type { Job } from "../careers";
import {
  aboutGradiated,
  applyHrefFor,
  howWeWork,
  interviewSteps,
  payAndEquity,
} from "../careers-copy";

type JobPageProps = {
  job: Job;
};

type JobSectionProps = {
  children: ReactNode;
  title: string;
};

const JobSection = ({ children, title }: JobSectionProps): ReactElement => (
  <section className="grid grid-cols-[220px_minmax(0,1fr)] gap-12 border-t border-line py-14 max-site:grid-cols-1 max-site:gap-7 max-site:py-11">
    <h2 className="m-0 pt-1.5 font-newsreader text-[30px] font-normal leading-none tracking-heading max-site:pt-0">
      {title}
    </h2>
    <div className="max-w-[690px] text-[16px] leading-[1.72] text-muted max-site:text-[15px]">
      {children}
    </div>
  </section>
);

const JobList = ({ items }: { items: string[] }): ReactElement => (
  <ul className="m-0 list-none space-y-3.5 p-0">
    {items.map((item) => (
      <li className="grid grid-cols-[18px_minmax(0,1fr)] gap-3" key={item}>
        <span
          aria-hidden="true"
          className="mt-[0.82em] block h-px w-3 bg-accent"
        />
        <span>{item}</span>
      </li>
    ))}
  </ul>
);

export const JobPage = ({ job }: JobPageProps): ReactElement => {
  const applyHref = applyHrefFor(job.title);

  return (
    <main className="px-7 pb-28 pt-20 max-site:px-[22px] max-site:pb-20 max-site:pt-14">
      <div className="mx-auto max-w-[1040px]">
        <Link
          className="eyebrow inline-flex items-center gap-2 transition-colors hover:text-accent"
          to="/careers/"
        >
          <ArrowLeft aria-hidden="true" className="h-3 w-3" strokeWidth={1.5} />
          Careers
        </Link>

        <header className="pb-16 pt-12 max-site:pb-12 max-site:pt-9">
          <p className="eyebrow text-accent">{job.team}</p>
          <h1 className="mb-9 mt-5 max-w-[900px] font-newsreader text-[clamp(48px,6vw,76px)] font-normal leading-[0.92] tracking-display max-site:text-[46px]">
            {job.title}
          </h1>
          <p className="m-0 max-w-[700px] font-newsreader text-[clamp(20px,2.2vw,28px)] font-normal leading-[1.25] tracking-[-0.02em] text-muted">
            {job.summary}
          </p>
        </header>

        <dl className="grid grid-cols-3 border-y border-line max-site:grid-cols-1">
          <div className="border-r border-line py-6 pr-7 max-site:border-b max-site:border-r-0 max-site:py-5">
            <dt className="eyebrow">Location</dt>
            <dd className="mb-0 ml-0 mt-3 text-[15px] leading-[1.5]">
              {job.location}
            </dd>
          </div>
          <div className="border-r border-line px-7 py-6 max-site:border-b max-site:border-r-0 max-site:px-0 max-site:py-5">
            <dt className="eyebrow">Office</dt>
            <dd className="mb-0 ml-0 mt-3 text-[15px] leading-[1.5]">
              Mon, Wed, Fri
            </dd>
          </div>
          <div className="py-6 pl-7 max-site:py-5 max-site:pl-0">
            <dt className="eyebrow">Compensation</dt>
            <dd className="mb-0 ml-0 mt-3 text-[15px] leading-[1.5]">
              £240,000-£420,000 base + significant equity
            </dd>
          </div>
        </dl>

        <div className="pt-16 max-site:pt-12">
          <JobSection title="About Gradiated">
            <JobList items={aboutGradiated} />
          </JobSection>

          <JobSection title="Why this role exists">
            <JobList items={job.purpose} />
          </JobSection>

          <JobSection title="What you will do">
            <JobList items={job.responsibilities} />
          </JobSection>

          <JobSection title="Problems you may work on">
            <JobList items={job.problems} />
          </JobSection>

          <JobSection title="What we are looking for">
            <JobList items={job.requirements} />
          </JobSection>

          <JobSection title="This role is not for you if">
            <JobList items={job.notFor} />
          </JobSection>

          <JobSection title="How we work">
            <div className="space-y-5">
              {howWeWork.map((line) => (
                <p className="m-0" key={line}>
                  {line}
                </p>
              ))}
            </div>
          </JobSection>

          <JobSection title="Pay and equity">
            <div className="space-y-5">
              {payAndEquity.map((line) => (
                <p className="m-0" key={line}>
                  {line}
                </p>
              ))}
            </div>
          </JobSection>

          <JobSection title="Interview process">
            <ol className="m-0 list-none space-y-4 p-0">
              {interviewSteps.map((step, index) => (
                <li
                  className="grid grid-cols-[32px_minmax(0,1fr)] items-center gap-3"
                  key={step}
                >
                  <span
                    aria-hidden="true"
                    className="font-site-mono text-[10px] leading-none tracking-[0.04em] text-accent"
                  >
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <span>{step}</span>
                </li>
              ))}
            </ol>
          </JobSection>
        </div>

        <section className="mt-8 border-y border-ink py-14 text-center">
          <p className="eyebrow">Apply</p>
          <h2 className="mb-7 mt-5 font-newsreader text-[clamp(38px,5vw,60px)] font-normal leading-[0.95] tracking-heading">
            Let&apos;s talk.
          </h2>
          <p className="mx-auto mb-8 mt-0 max-w-[620px] text-[15px] leading-[1.65] text-muted">
            If this sounds interesting to you, we&apos;d like to hear from you.
            There&apos;s no need to prepare anything, we'll start with a
            conversation.
          </p>
          <a
            className="inline-flex items-center gap-2 border border-ink px-6 pb-[13px] pt-3.5 font-libre text-[11px] font-medium uppercase tracking-label transition-colors hover:bg-ink hover:text-paper"
            href={applyHref}
          >
            Start a conversation
            <ArrowRight
              aria-hidden="true"
              className="h-3.5 w-3.5"
              strokeWidth={1.5}
            />
          </a>
        </section>
      </div>
    </main>
  );
};
