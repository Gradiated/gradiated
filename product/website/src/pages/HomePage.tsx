import { Link } from "react-router-dom";
import type { ReactElement } from "react";
import { ProductSection } from "../components/ProductSection";

type HomePageProps = {
  onWaitlist: () => void;
};

export const HomePage = ({ onWaitlist }: HomePageProps): ReactElement => (
  <main>
    <section className="hero flex min-h-[calc(100vh-76px)] flex-col border-b border-line px-7 pb-32 pt-[clamp(100px,16vh,175px)] max-site:min-h-[760px] max-site:px-5 max-site:pb-20 max-site:pt-24">
      <h1 className="mb-16 max-w-hero font-newsreader text-hero font-normal leading-hero tracking-display max-site:mb-14 max-site:text-6xl">
        The research lab focused on inference.
      </h1>
      <p className="hero-copy ml-auto max-w-copy text-copy leading-copy text-muted max-site:ml-0 max-site:text-copy-mobile">
        We codesign hardware and software to provide the world&apos;s cheapest
        inference.
      </p>
    </section>

    <ProductSection onWaitlist={onWaitlist} />

    <section className="section how px-7 pt-24 max-site:px-5 max-site:pt-16">
      <div className="api-layout grid grid-cols-2 items-end gap-[9%] border-0 pb-36 max-site:grid-cols-1 max-site:gap-16 max-site:pb-24">
        <div>
          <h2 className="max-w-api-title font-newsreader text-api-title font-normal leading-api-title tracking-heading max-site:text-[43px]">
            The harness API for controlling cost and latency.
          </h2>
          <p className="mt-8 max-w-api text-api-copy leading-api-copy text-muted">
            Submit a durable run through the SDK. Gradiated owns the planning,
            execution, and inference decisions beneath it. Each step uses the
            right model, at the right cost, for the work.
          </p>
        </div>
        <pre
          className="api-example"
          aria-label="Example Gradiated harness SDK request"
        >
          <code>
            <span className="code-key">import</span> {"{ Gradiated }"}{" "}
            <span className="code-key">from</span>{" "}
            <span className="code-string">&quot;@gradiated/sdk&quot;</span>
            {"\n\n"}
            <span className="code-key">const</span> run ={" "}
            <span className="code-key">await</span> gradiated.runs.create({"{"}
            {"\n"} task:{" "}
            <span className="code-string">
              &quot;Research and compare three vendors&quot;
            </span>
            ,{"\n"} tools: [webSearch, browser],{"\n"} profile: {"{"}
            {"\n"} budget: {"{"} max_usd: <span className="code-number">2</span>{" "}
            {"}"}, deadline:{" "}
            <span className="code-string">&quot;20m&quot;</span>, quality:{" "}
            <span className="code-string">&quot;thorough&quot;</span>
            {"\n"} {"}"}
            {"\n"}
            {"}"})
          </code>
        </pre>
      </div>
    </section>

    <section className="news">
      <div className="news-grid">
        <Link className="news-item" to="/notes/our-thesis/">
          <img
            src="/assets/editorial/thesis-v2.png"
            alt="A lone thinker facing an argument receding through successive architectural thresholds"
            width="1254"
            height="1254"
            loading="lazy"
          />
          <div className="news-copy">
            <div>
              <p>13 July 2026</p>
              <h2>Thesis</h2>
              <span>Finding the right tool for the job.</span>
            </div>
            <b>Read note →</b>
          </div>
        </Link>
        <Link className="news-secondary" to="/notes/working-with-us/">
          <div className="news-copy">
            <div>
              <p>15 July 2026</p>
              <h2>Working with us</h2>
              <span>We are hiring founding engineers.</span>
            </div>
            <b>Read note →</b>
          </div>
          <img
            src="/assets/editorial/working-with-us-v2.png"
            alt="An eroded academy interior where groups of scholars gather in debate"
            width="1254"
            height="1254"
            loading="lazy"
          />
        </Link>
      </div>
    </section>
  </main>
);
