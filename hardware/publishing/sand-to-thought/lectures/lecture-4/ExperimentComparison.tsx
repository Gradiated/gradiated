import type { ReactNode } from "react";
import { MechanismDetail } from "../../articles/fpga/figures/MeasurementMechanism";
import { laterComparisons, type ComparisonScene } from "../../articles/fpga/figures/laterComparisons";
import { measurementStepFor } from "../../articles/fpga/figures/scenes";

function ArticleDetail({ step }: { step: number }) {
  // The article places this inset immediately below its own miniature chip.
  return (
    <div className="lecture-article-detail fpga-measurement-panel">
      <svg viewBox="4 80 188 94" role="group" aria-label="Circuit detail"><MechanismDetail step={step} /></svg>
    </div>
  );
}

function BuildPair({ before, after }: { before: ReactNode; after: ReactNode }) {
  return (
    <div className="lecture-build-pair">
      <div><strong>Before</strong>{before}</div>
      <span aria-hidden="true">→</span>
      <div><strong>After</strong>{after}</div>
    </div>
  );
}

function ClockCount({ count, label }: { count: number; label: string }) {
  return (
    <div className="lecture-clock-count">
      <span className="lecture-count-cells" aria-hidden="true">
        {Array.from({ length: count }, (_, i) => <i key={i} />)}
      </span>
      {label}
    </div>
  );
}

function Jobs({ jobs, timed = false }: { jobs: readonly (readonly string[])[]; timed?: boolean }) {
  return (
    <div className="lecture-job-slots" data-timed={timed}>
      {jobs.map((slot, i) => (
        <div key={i}>
          {timed && <small>Tick {i + 1}</small>}
          {slot.map(job => <span key={job}>{job}</span>)}
        </div>
      ))}
    </div>
  );
}

const earlyLabels: Record<string, [string, string]> = {
  "measure-skip": ["Score every prompt token", "Score the final prompt token"],
  "measure-two-lanes": ["1 scoring lane", "2 scoring lanes"],
  "measure-four-lanes": ["1 scoring lane", "4 scoring lanes"],
  "measure-eight-lanes": ["4 scoring lanes", "8 scoring lanes"],
  "measure-feedforward-divide": ["Calculate every digit", "Skip known leading zeros"],
  "measure-attention-divide": ["Calculate every digit", "Skip known leading zeros"],
  "measure-exp-pair": ["One score at a time", "Two scores together"],
};

export function ExperimentComparison({ scene, closeup }: { scene: string; closeup?: ReactNode }) {
  const early = measurementStepFor(scene);
  const late = laterComparisons[scene as ComparisonScene];
  let drawing = closeup;
  const labels = earlyLabels[scene] ?? (late && [late.before, late.after]);
  // These article figures already label both builds. The baseline has only one.
  if (early >= 0 && !closeup) drawing = <ArticleDetail step={early} />;
  if (scene === "measure-autonomous") {
    return <BuildPair before={<ArticleDetail step={0} />} after={<ArticleDetail step={1} />} />;
  }
  if (scene === "measure-projection-reads") return <ArticleDetail step={5} />;
  if (scene === "measure-clock-rate") return closeup;
  if (scene === "measure-ddr-prefetch") {
    return <BuildPair
      before={<><Jobs jobs={[["Fill A"], ["Score from A"]]} />{late.before}</>}
      after={<><Jobs jobs={[["Fill B", "Score from A"]]} />{late.after}</>}
    />;
  }
  if (scene === "measure-value-pair") {
    return <BuildPair
      before={<><Jobs timed jobs={[["¼ × value 1"], ["¼ × value 2"]]} />{late.before}</>}
      after={<><Jobs timed jobs={[["¼ × value 1", "¼ × value 2"]]} />{late.after}</>}
    />;
  }
  if (scene === "measure-ddr-scores") {
    return <BuildPair
      before={<><Jobs jobs={[["BRAM"]]} />All 20 KiB on-chip</>}
      after={<><Jobs jobs={[["DDR4"], ["Buffer"]]} />512-byte buffer on-chip</>}
    />;
  }
  if (scene === "measure-probability-div" || scene === "measure-feedforward-multiply") {
    const division = scene === "measure-probability-div";
    return <BuildPair
      before={<ClockCount count={division ? 32 : 16} label={late.before} />}
      after={<ClockCount count={division ? 8 : 5} label={late.after} />}
    />;
  }
  return <>{drawing}{labels && <BuildPair before={labels[0]} after={labels[1]} />}</>;
}
