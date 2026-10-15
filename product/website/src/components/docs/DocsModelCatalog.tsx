import { useCallback, useEffect, useState } from "react";
import type { ReactElement } from "react";

import { listModels, type Model } from "../../api/queries";

type PriceType = "prompt" | "cached_prompt" | "completion";

const MODEL_COLUMNS = [
  "Model",
  "Input",
  "Cached input",
  "Output",
  "Context",
] as const;

// The hosted catalog also lists training bases that cannot serve requests.
const isInferenceModel = (model: Model): boolean =>
  "supported_uses" in model.properties &&
  model.properties.supported_uses.includes("serving");

const pricePerMillion = (model: Model, type: PriceType): string => {
  const entries =
    type === "completion"
      ? model.properties.output_modalities[0]?.pricing
      : model.properties.input_modalities[0]?.pricing;
  const price = entries?.find((entry) => entry.type === type);
  if (!price) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(price.cost / 1_000);
};

const formatContext = (model: Model): string => {
  const tokens =
    model.properties.input_modalities[0]?.supported_inputs.max_context_length
      .value;
  if (!tokens) return "—";
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(tokens);
};

const ModelMetric = ({
  label,
  perMillion = false,
  value,
}: {
  label: string;
  perMillion?: boolean;
  value: string;
}) => (
  <div className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-4 border-b border-line py-3 last:border-b-0">
    <dt className="font-site-mono text-[10px] font-medium uppercase tracking-[0.07em] text-muted">
      {label}
    </dt>
    <dd className="m-0 whitespace-nowrap text-right font-site-mono text-[13px] text-ink">
      {value}
      {perMillion && value !== "—" && (
        <span data-price-unit className="ml-1 text-[10px] text-muted">
          / 1M
        </span>
      )}
    </dd>
  </div>
);

const CopyModelId = ({
  copied,
  id,
  onCopy,
}: {
  copied: boolean;
  id: string;
  onCopy: (id: string) => void;
}): ReactElement => (
  <button
    aria-label={`Copy model ID ${id}`}
    className="shrink-0 cursor-pointer rounded-md border border-line bg-transparent px-3 py-2 font-site-mono text-[10px] font-medium uppercase tracking-[0.06em] text-muted hover:border-ink hover:text-ink"
    onClick={() => onCopy(id)}
    type="button"
  >
    {copied ? "Copied" : "Copy ID"}
  </button>
);

const ModelTableHead = (): ReactElement => (
  <thead className="bg-[color-mix(in_srgb,var(--soft)_60%,transparent)]">
    <tr>
      {MODEL_COLUMNS.map((label) => (
        <th
          className="border-b border-line px-3 py-3.5 text-left font-site-mono text-[10px] font-medium uppercase tracking-[0.06em] text-muted first:pl-4"
          key={label}
          scope="col"
        >
          {label}
        </th>
      ))}
      <th className="border-b border-line px-3 py-3" scope="col">
        <span className="sr-only">Copy model ID</span>
      </th>
    </tr>
  </thead>
);

const ModelTableSkeletonRow = (): ReactElement => (
  <tr aria-hidden="true" className="animate-pulse">
    {["w-28", "w-14", "w-14", "w-14", "w-8"].map((width, index) => (
      <td className="px-3 py-4 first:pl-4" key={`${width}-${index}`}>
        <span className={`block h-3.5 ${width} max-w-full bg-line`} />
      </td>
    ))}
    <td className="px-3 py-4 pr-4 text-right align-middle">
      <span className="ml-auto block h-[34px] w-[66px] bg-line" />
    </td>
  </tr>
);

const ModelCardSkeleton = (): ReactElement => (
  <article aria-hidden="true" className="animate-pulse border-y border-line">
    <div className="flex items-center justify-between gap-4 py-4">
      <span className="block h-3.5 w-32 bg-line" />
      <span className="block h-[34px] w-[66px] bg-line" />
    </div>
    <div className="border-t border-line">
      {MODEL_COLUMNS.slice(1).map((label) => (
        <div
          className="flex items-center justify-between border-b border-line py-3 last:border-b-0"
          key={label}
        >
          <span className="block h-2.5 w-16 bg-line" />
          <span className="block h-3.5 w-12 bg-line" />
        </div>
      ))}
    </div>
  </article>
);

export const DocsModelCatalog = ({
  variant = "docs",
}: {
  variant?: "docs" | "site";
}): ReactElement => {
  const [models, setModels] = useState<Model[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">(
    "loading",
  );
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const loadModels = useCallback(async (): Promise<void> => {
    setStatus("loading");
    try {
      const result = await listModels();
      setModels(result.data.filter(isInferenceModel));
      setStatus("ready");
    } catch {
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    void loadModels();
  }, [loadModels]);

  const copyModelId = async (id: string): Promise<void> => {
    await navigator.clipboard.writeText(id);
    setCopiedId(id);
    window.setTimeout(() => setCopiedId(null), 1600);
  };

  if (status === "error") {
    return (
      <div className="my-7 flex items-center justify-between gap-4 rounded-xl border border-line px-5 py-5">
        <p className="m-0 font-libre text-[14px] text-ink">
          The model catalog is not available.
        </p>
        <button
          className="cursor-pointer rounded-md border border-ink bg-ink px-3 py-2 font-site-mono text-[9px] font-medium uppercase tracking-[0.06em] text-paper hover:bg-transparent hover:text-ink"
          onClick={() => void loadModels()}
          type="button"
        >
          Try again
        </button>
      </div>
    );
  }

  if (status === "ready" && models.length === 0) {
    return (
      <div className="my-7 rounded-xl border border-line px-5 py-8 font-libre text-[14px] text-muted">
        No models are listed.
      </div>
    );
  }

  return (
    <div
      className={`@container my-7 ${variant === "site" ? "gr-model-catalog w-full max-w-none" : "max-w-[760px]"}`}
    >
      {status === "loading" && (
        <p className="sr-only" role="status">
          Loading models
        </p>
      )}
      <div
        data-model-table-frame
        className="hidden overflow-hidden rounded-xl border border-line @min-[700px]:block"
      >
        <table
          aria-busy={status === "loading"}
          data-model-table
          className="w-full table-fixed border-collapse font-libre text-[13px]"
        >
          <colgroup>
            <col className="w-[26%]" />
            <col className="w-[14%]" />
            <col className="w-[18%]" />
            <col className="w-[14%]" />
            <col className="w-[10%]" />
            <col className="w-[18%]" />
          </colgroup>
          <ModelTableHead />
          <tbody>
            {status === "loading" ? (
              <ModelTableSkeletonRow />
            ) : (
              models.map((model) => (
                <tr
                  className="border-b border-line last:border-b-0"
                  key={model.id}
                >
                  <td className="px-3 py-4 pl-4 align-middle">
                    <strong className="font-libre text-[15px] font-semibold text-ink">
                      {model.name}
                    </strong>
                  </td>
                  <td className="whitespace-nowrap px-3 py-4 font-site-mono text-[13px] text-ink">
                    {pricePerMillion(model, "prompt")}
                    <span
                      data-price-unit
                      className="ml-1 text-[10px] text-muted"
                    >
                      / 1M
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-3 py-4 font-site-mono text-[13px] text-ink">
                    {pricePerMillion(model, "cached_prompt")}
                    <span
                      data-price-unit
                      className="ml-1 text-[10px] text-muted"
                    >
                      / 1M
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-3 py-4 font-site-mono text-[13px] text-ink">
                    {pricePerMillion(model, "completion")}
                    <span
                      data-price-unit
                      className="ml-1 text-[10px] text-muted"
                    >
                      / 1M
                    </span>
                  </td>
                  <td className="px-3 py-4 font-site-mono text-[13px] text-ink">
                    {formatContext(model)}
                  </td>
                  <td className="px-3 py-4 pr-4 text-right align-middle">
                    <CopyModelId
                      copied={copiedId === model.id}
                      id={model.id}
                      onCopy={(id) => void copyModelId(id)}
                    />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="grid gap-6 @min-[700px]:hidden" data-model-cards>
        {status === "loading" ? (
          <ModelCardSkeleton />
        ) : (
          models.map((model) => (
            <article
              className="border-y border-line"
              data-model-card
              key={model.id}
            >
              <div className="flex items-center justify-between gap-4 py-4">
                <div className="min-w-0">
                  <strong className="font-libre text-[15px] font-semibold text-ink">
                    {model.name}
                  </strong>
                </div>
                <CopyModelId
                  copied={copiedId === model.id}
                  id={model.id}
                  onCopy={(id) => void copyModelId(id)}
                />
              </div>
              <dl className="m-0 border-t border-line">
                <ModelMetric
                  label="Input"
                  perMillion
                  value={pricePerMillion(model, "prompt")}
                />
                <ModelMetric
                  label="Cached input"
                  perMillion
                  value={pricePerMillion(model, "cached_prompt")}
                />
                <ModelMetric
                  label="Output"
                  perMillion
                  value={pricePerMillion(model, "completion")}
                />
                <ModelMetric label="Context" value={formatContext(model)} />
              </dl>
            </article>
          ))
        )}
      </div>
    </div>
  );
};
