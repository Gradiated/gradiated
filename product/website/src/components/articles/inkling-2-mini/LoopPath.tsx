import type { ReactElement } from "react";
import "./article.css";
import "./loop-path.css";

const LAYERS_PER_BLOCK = 6;
const LOOPED = new Set([2, 3]);

const STORED = [[1], [2, 3], [4]];
const RUN = [[1], [2, 3], [2, 3], [2, 3], [4]];

const Block = ({ block }: { block: number }): ReactElement => (
  <span
    className={
      LOOPED.has(block) ? "ipath-block ipath-block--looped" : "ipath-block"
    }
  >
    <span className="ipath-ticks">
      {Array.from({ length: LAYERS_PER_BLOCK }, (_, i) => (
        <span className="ipath-tick" key={i} />
      ))}
    </span>
    <span className="ipath-num">{block}</span>
  </span>
);

const Row = ({ groups }: { groups: number[][] }): ReactElement => (
  <span className="ipath-row">
    {groups.map((group, i) => (
      <span className="ipath-group" key={i}>
        {group.map((block) => (
          <Block block={block} key={block} />
        ))}
      </span>
    ))}
  </span>
);

export const LoopPath = (): ReactElement => (
  <figure className="ipath">
    <p className="gr-visually-hidden">
      Inkling 2 Mini stores 24 layers in four blocks. When it runs, a token goes
      through block 1, then blocks 2 and 3 three times, then block 4: 48 layer
      passes in all.
    </p>

    <div className="ipath-grid" aria-hidden="true">
      <span className="ipath-label">Stored</span>
      <span className="ipath-stored">
        <Row groups={STORED} />
      </span>
      <span className="ipath-count">24 layers</span>

      <span className="ipath-label">Run</span>
      <Row groups={RUN} />
      <span className="ipath-count">48 layer passes</span>
    </div>
  </figure>
);
