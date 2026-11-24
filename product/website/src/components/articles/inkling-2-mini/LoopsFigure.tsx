import "./article.css";
import "./loops-figure.css";

const TOKENS_PER_LINE = 24;
const source =
  "https://thinkingmachines.ai/news/inkling-2-mini/#monitorability-of-looped-transformers";

const Lines = ({ tokens }: { tokens: number }) => {
  const count = Math.round(tokens / TOKENS_PER_LINE);

  return (
    <div className="lf-cot" aria-hidden>
      {Array.from({ length: count }, (_, i) => (
        <span
          className="lf-line"
          key={i}
          style={{ width: `${i === count - 1 ? 45 : 72 + ((i * 37) % 26)}%` }}
        />
      ))}
    </div>
  );
};

const Column = ({ loops, tokens }: { loops: number; tokens: number }) => (
  <div>
    <p className="lf-title">
      {loops} {loops === 1 ? "loop" : "loops"}
    </p>
    <p className="lf-count">{tokens} tokens of written reasoning</p>
    <Lines tokens={tokens} />
    <p className="lf-answer">Answer: Friday</p>
  </div>
);

export const LoopsFigure = () => {
  return (
    <figure className="lf">
      <div className="lf-prompt">
        <p className="lf-prompt-label">Prompt</p>
        <p className="lf-question">
          March 1 falls on a Tuesday in a year that is not a leap year. What day
          of the week is May 20?
        </p>
      </div>

      <div className="lf-cols">
        <Column loops={1} tokens={582} />
        <Column loops={5} tokens={240} />
      </div>

      <figcaption>
        <a href={source} rel="noreferrer" target="_blank">
          Thinking Machines
        </a>
      </figcaption>
    </figure>
  );
};
