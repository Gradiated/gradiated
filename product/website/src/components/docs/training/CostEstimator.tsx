import { useId, useState } from "react";
import type { ReactElement } from "react";

import {
  CATALOG,
  catalogModel,
  compact,
  estimatePlan,
  thousands,
  usd,
} from "./data";

/* qwen3-32b is in the catalog as a teacher and judge, but doesn't fit one
   80 GB GPU, so it isn't trained in v0. */
const LLMS = CATALOG.filter(
  (model) => model.id.startsWith("qwen/") && model.id !== "qwen/qwen3-32b",
);

const NumberField = ({
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
  hint,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min: number;
  max: number;
  step?: number;
  hint?: string;
}): ReactElement => {
  const id = useId();

  return (
    <div className="gr-dx-field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        inputMode="decimal"
        max={max}
        min={min}
        onChange={(event) => {
          const next = Number(event.target.value);
          if (Number.isFinite(next)) {
            onChange(Math.min(max, Math.max(min, next)));
          }
        }}
        step={step}
        type="number"
        value={value}
      />
      {hint ? <span className="gr-dx-field-hint">{hint}</span> : null}
    </div>
  );
};

export const CostEstimator = (): ReactElement => {
  const [modelId, setModelId] = useState("qwen/qwen3-8b");
  const [records, setRecords] = useState(5000);
  const [tokensPerRecord, setTokensPerRecord] = useState(600);
  const [epochs, setEpochs] = useState(1);
  const [batchSize, setBatchSize] = useState(128);
  const [evalFraction, setEvalFraction] = useState(0.1);
  const [cap, setCap] = useState(20);
  const modelField = useId();

  const model = catalogModel(modelId);
  const plan = estimatePlan({
    records,
    tokensPerRecord,
    epochs,
    batchSize,
    evalFraction,
    price: model.price,
    maxCostUsd: cap > 0 ? cap : null,
  });
  const costs = LLMS.map((candidate) => ({
    model: candidate,
    cost: (plan.tokens / 1_000_000) * candidate.price,
  }));
  const most = Math.max(...costs.map((row) => row.cost), 0.0001);

  return (
    <section aria-label="Training cost estimate" className="gr-dx gr-dx-cost">
      <div className="gr-dx-cost-inputs">
        <div className="gr-dx-field gr-dx-field--wide">
          <label htmlFor={modelField}>Base model</label>
          <select
            id={modelField}
            onChange={(event) => setModelId(event.target.value)}
            value={modelId}
          >
            {LLMS.map((option) => (
              <option key={option.id} value={option.id}>
                {option.id} · {usd(option.price)}/1M
              </option>
            ))}
          </select>
        </div>
        <NumberField
          label="Records"
          max={5_000_000}
          min={1}
          onChange={setRecords}
          value={records}
        />
        <NumberField
          hint="rendered, per record"
          label="Tokens"
          max={32_768}
          min={1}
          onChange={setTokensPerRecord}
          value={tokensPerRecord}
        />
        <NumberField
          label="Epochs"
          max={20}
          min={1}
          onChange={setEpochs}
          value={epochs}
        />
        <NumberField
          label="Batch size"
          max={4096}
          min={1}
          onChange={setBatchSize}
          value={batchSize}
        />
        <NumberField
          label="Held out"
          max={0.9}
          min={0}
          onChange={setEvalFraction}
          step={0.05}
          value={evalFraction}
        />
        <NumberField
          hint="0 for none"
          label="max_cost_usd"
          max={100_000}
          min={0}
          onChange={setCap}
          value={cap}
        />
      </div>

      <pre aria-live="polite" className="gr-dx-plan">
        <span className="gr-dx-plan-title">
          Plan for support-sft (sft on {model.id})
        </span>
        {"\n"}
        {`  split     : ~${thousands(plan.trainRecords)} train / ${thousands(plan.evalRecords)} eval (by_session, ${Math.round(evalFraction * 100)}% held out)\n`}
        {`  steps     : ${thousands(plan.steps)} (batch ${batchSize}, ${epochs} epoch${epochs === 1 ? "" : "s"})\n`}
        {`  tokens    : ~${compact(plan.tokens)}\n`}
        {"  est. cost : "}
        <strong>{usd(plan.costUsd)}</strong>
        {` at ${usd(model.price)}/1M tokens${cap > 0 ? ` (cap ${usd(cap)})` : ""}\n`}
        {plan.warnings.length ? "  warnings:\n" : ""}
        {plan.warnings.map((warning) => (
          <span className="gr-dx-plan-warn" key={warning}>
            {`    - ${warning}\n`}
          </span>
        ))}
      </pre>

      <p className="gr-dx-cost-math">
        {thousands(plan.trainRecords)} train records ×{" "}
        {thousands(tokensPerRecord)} tokens × {epochs} epoch
        {epochs === 1 ? "" : "s"} = {compact(plan.tokens)} tokens, ×{" "}
        {usd(model.price)} per million = <strong>{usd(plan.costUsd)}</strong>
      </p>

      <div className="gr-dx-cost-compare">
        <p className="gr-dx-small-label">The same tokens on each base model</p>
        <ul>
          {costs.map((row) => (
            <li
              aria-current={row.model.id === modelId ? "true" : undefined}
              key={row.model.id}
            >
              <button onClick={() => setModelId(row.model.id)} type="button">
                <span className="gr-dx-cost-name">{row.model.id}</span>
                <span className="gr-dx-cost-bar" aria-hidden="true">
                  <span style={{ width: `${(row.cost / most) * 100}%` }} />
                </span>
                <span className="gr-dx-cost-value">{usd(row.cost)}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>

      <p className="gr-dx-caption">
        The arithmetic of <code>runs.plan()</code> at the catalog rates the
        usage ledger records (<code>grad models list</code>). The server counts
        tokens from your rendered records, so run <code>--dry-run</code> for the
        real number. Not included: a router's labeling eval and a distillation
        teacher's tokens, which the plan adds. Training on Gradiated Cloud isn't
        open yet; a self-hosted server records the same ledger and charges
        nothing.
      </p>
    </section>
  );
};

export default CostEstimator;
