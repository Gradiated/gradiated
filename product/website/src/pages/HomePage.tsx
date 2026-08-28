import { Link } from "react-router-dom";
import type { ReactElement } from "react";
import { ServiceTierSection } from "../components/ServiceTierSection";

const newsLinkClass =
  "thesis-card group grid h-[390px] min-h-[390px] grid-cols-2 items-stretch overflow-hidden text-ink max-site:h-auto max-site:min-h-0 max-site:grid-cols-1";
const newsImageClass =
  "thesis-card-image block h-full min-h-[390px] w-full object-cover saturate-[0.8] transition-[transform,filter] duration-700 ease-editorial group-hover:scale-[1.02] group-hover:saturate-[0.95] motion-reduce:transition-none max-site:aspect-square max-site:h-auto max-site:min-h-0";
const newsCopyClass =
  "thesis-card-copy flex flex-col justify-between p-[30px] transition-colors duration-200 group-hover:bg-ink group-hover:text-paper max-site:min-h-[230px] max-site:px-[22px] max-site:py-[26px]";
const newsDateClass =
  "mb-[35px] font-libre text-label font-medium uppercase tracking-label group-hover:text-line";
const newsTitleClass =
  "mb-3 font-newsreader text-[clamp(40px,4.7vw,64px)] font-normal leading-[0.95] tracking-[-0.04em]";
const newsSummaryClass = "text-sm text-muted group-hover:text-line";
const newsCtaClass =
  "self-start border-b pb-[5px] font-libre text-label font-medium uppercase tracking-label";

export const HomePage = (): ReactElement => (
  <main>
    <section className="flex min-h-[calc(100vh-76px)] flex-col px-7 pb-32 pt-[clamp(100px,16vh,175px)] max-site:min-h-0 max-site:px-5 max-site:pb-20 max-site:pt-24">
      <h1 className="mb-5 max-w-[940px] font-newsreader text-[clamp(58px,7.8vw,106px)] font-normal leading-[0.91] tracking-display max-site:mb-5 max-site:text-[52px]">
        The research lab focused on inference.
      </h1>
      <div className="max-w-copy text-left">
        <p className="m-0 text-copy leading-copy text-muted max-site:text-copy-mobile">
          We co-design hardware and software to provide the world&apos;s most
          affordable inference.
        </p>
        <div className="mt-10 flex flex-wrap items-center gap-x-8 gap-y-4">
          <a
            className="group inline-flex items-center gap-2 border border-ink px-[22px] pb-[13px] pt-3.5 font-libre text-[11px] font-medium uppercase tracking-[0.08em] text-ink transition-colors hover:bg-ink hover:text-paper"
            href="https://console.gradiated.com/"
          >
            Get API key
            <b className="font-medium transition-transform group-hover:translate-x-[3px]">
              →
            </b>
          </a>
          <Link
            className="inline-flex items-center gap-1.5 border-b border-line pb-[3px] font-libre text-[11px] font-medium uppercase tracking-[0.08em] text-muted transition-colors hover:border-ink hover:text-ink"
            to="/docs/"
          >
            View docs <b className="font-medium text-accent">→</b>
          </Link>
        </div>
      </div>
    </section>

    <ServiceTierSection />

    <section className="px-7 pb-36 pt-36 max-site:px-[22px] max-site:pb-24 max-site:pt-16">
      <div className="grid grid-cols-1">
        <Link className={newsLinkClass} to="/notes/our-thesis/">
          <img
            className={newsImageClass}
            src="/assets/editorial/thesis-v2.png"
            alt="A lone thinker facing an argument receding through successive architectural thresholds"
            width="1254"
            height="1254"
            loading="lazy"
          />
          <div
            className={`${newsCopyClass} border-l border-line max-site:border-l-0`}
          >
            <div>
              <p className={`${newsDateClass} text-accent`}>13 July 2026</p>
              <h2 className={newsTitleClass}>Thesis</h2>
              <span className={newsSummaryClass}>
                Finding the right tool for the job.
              </span>
            </div>
            <b className={`${newsCtaClass} border-accent`}>Read note →</b>
          </div>
        </Link>
        <Link
          className="group mt-10 grid grid-cols-[minmax(0,1fr)_auto] items-end gap-8 border-y border-ink py-8 text-ink transition-colors hover:text-accent max-site:grid-cols-1 max-site:gap-8"
          to="/careers/"
        >
          <div>
            <p className="mb-5 font-libre text-label font-medium uppercase tracking-label text-earth">
              Careers
            </p>
            <h2 className="m-0 font-newsreader text-[clamp(42px,4.7vw,64px)] font-normal leading-[0.95] tracking-[-0.04em]">
              We are hiring.
            </h2>
            <p className="mb-0 mt-4 text-sm text-muted">
              Founding roles in inference software and silicon.
            </p>
          </div>
          <b className="justify-self-end border-b border-earth pb-[5px] font-libre text-label font-medium uppercase tracking-label max-site:justify-self-start">
            View roles →
          </b>
        </Link>
      </div>
    </section>
  </main>
);
