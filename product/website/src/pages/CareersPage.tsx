import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import type { ReactElement } from "react";
import { jobs } from "../careers";

const roleLinkClass =
  "group grid grid-cols-[minmax(0,1fr)_auto] gap-8 border-b border-line py-8 text-ink transition-colors hover:text-accent max-site:gap-4 max-site:py-7";

export const CareersPage = (): ReactElement => (
  <main>
    <section className="border-b border-line px-7 pb-24 pt-28 max-site:px-[22px] max-site:pb-16 max-site:pt-20">
      <p className="eyebrow">Careers</p>
      <h1 className="mb-10 mt-6 max-w-[980px] font-newsreader text-[clamp(58px,8vw,108px)] font-normal leading-[0.9] tracking-display max-site:text-[52px]">
        Build inference from model to silicon.
      </h1>
      <div className="flex max-w-[630px] flex-col gap-8 text-copy leading-copy text-muted max-site:gap-6 max-site:text-copy-mobile">
        <p className="m-0">Our goal is to maximize intelligence per joule.</p>
        <p className="m-0">
          We build software and hardware to make open-weight model inference as
          efficient as possible.
        </p>
        <p className="m-0">
          We want people who can go deep across the abstraction stack, and want
          to understand what can be achieved by optimizing software and hardware
          together.
        </p>
      </div>
    </section>

    <section
      className="grid grid-cols-[minmax(220px,0.45fr)_minmax(0,1fr)] gap-16 border-b border-line px-7 py-24 max-site:grid-cols-1 max-site:gap-8 max-site:px-[22px] max-site:py-16"
      aria-labelledby="work-heading"
    >
      <div>
        <p className="eyebrow">How we work</p>
        <h2
          className="mb-0 mt-5 font-newsreader text-[clamp(40px,5vw,64px)] font-normal leading-[0.95] tracking-heading"
          id="work-heading"
        >
          Depth across the stack.
        </h2>
      </div>
      <div className="max-w-[700px] text-[17px] leading-[1.7] text-muted max-site:text-[15px]">
        <p className="m-0">
          We work from first principles. We start by thinking about the model as
          a mathematical function, and map that out onto hardware and then build
          software on top of that which is custom to each model. This maximises
          performance and removes wasted abstractions.
        </p>
        <p className="mb-0 mt-10 max-site:mt-8">
          We pay at the top of the market because talent density is what allows
          us to build the most efficient inference. A small team of exceptional
          people can move faster, make better decisions, and solve harder
          problems.
        </p>
      </div>
    </section>

    <section
      className="px-7 py-24 max-site:px-[22px] max-site:py-16"
      aria-labelledby="roles-heading"
    >
      <p className="eyebrow">Open roles</p>
      <h2
        className="mb-12 mt-5 font-newsreader text-[clamp(45px,6vw,76px)] font-normal leading-[0.92] tracking-heading"
        id="roles-heading"
      >
        We are hiring.
      </h2>
      <div className="border-t border-line">
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
