import { useCallback, useEffect, useState } from "react";
import type { ReactElement } from "react";

import { listModels, type Model } from "../../api/queries";

type PriceType = "prompt" | "cached_prompt" | "completion";

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

const Price = ({
  label,
  perMillion = false,
  value,
}: {
  label: string;
  perMillion?: boolean;
  value: string;
}) => (
  <div>
    <dt className="font-site-mono text-[10px] font-medium uppercase tracking-[0.07em] text-muted">
      {label}
    </dt>
    <dd className="mb-0 mt-1 font-site-mono text-[13px] text-ink">
      {value}
      {perMillion && value !== "—" && (
        <span className="ml-1 text-[10px] text-muted">/ 1M</span>
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

export const DocsModelCatalog = (): ReactElement => {
  const [models, setModels] = useState<Model[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">(
    "loading",
  );
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const loadModels = useCallback(async (): Promise<void> => {
    setStatus("loading");
    try {
      const result = await listModels();
      setModels(result.data);
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

  if (status === "loading") {
    return (
      <div className="my-7 rounded-xl border border-line px-5 py-8 font-libre text-[14px] text-muted">
        Loading models…
      </div>
    );
  }

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

  if (models.length === 0) {
    return (
      <div className="my-7 rounded-xl border border-line px-5 py-8 font-libre text-[14px] text-muted">
        No models are listed.
      </div>
    );
  }

  return (
    <div className="my-7 max-w-[760px]">
      <div className="hidden overflow-hidden rounded-xl border border-line min-[641px]:block">
        <table className="w-full border-collapse font-libre text-[13px]">
          <thead className="bg-[color-mix(in_srgb,var(--soft)_60%,transparent)]">
            <tr>
              {["Model", "Input", "Cached input", "Output", "Context"].map(
                (label) => (
                  <th
                    className="border-b border-line px-3 py-3.5 text-left font-site-mono text-[10px] font-medium uppercase tracking-[0.06em] text-muted first:pl-4"
                    key={label}
                    scope="col"
                  >
                    {label}
                  </th>
                ),
              )}
              <th className="border-b border-line px-3 py-3" scope="col">
                <span className="sr-only">Copy model ID</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {models.map((model) => (
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
                  <span className="ml-1 text-[10px] text-muted">/ 1M</span>
                </td>
                <td className="whitespace-nowrap px-3 py-4 font-site-mono text-[13px] text-ink">
                  {pricePerMillion(model, "cached_prompt")}
                  <span className="ml-1 text-[10px] text-muted">/ 1M</span>
                </td>
                <td className="whitespace-nowrap px-3 py-4 font-site-mono text-[13px] text-ink">
                  {pricePerMillion(model, "completion")}
                  <span className="ml-1 text-[10px] text-muted">/ 1M</span>
                </td>
                <td className="px-3 py-4 font-site-mono text-[13px] text-ink">
                  {formatContext(model)}
                </td>
                <td className="px-3 py-4 text-right">
                  <CopyModelId
                    copied={copiedId === model.id}
                    id={model.id}
                    onCopy={(id) => void copyModelId(id)}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid gap-3 min-[641px]:hidden">
        {models.map((model) => (
          <article className="rounded-xl border border-line p-4" key={model.id}>
            <div className="flex items-start justify-between gap-3">
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
            <dl className="mb-0 mt-4 grid grid-cols-2 gap-x-5 gap-y-4 border-t border-line pt-4">
              <Price
                label="Input"
                perMillion
                value={pricePerMillion(model, "prompt")}
              />
              <Price
                label="Cached input"
                perMillion
                value={pricePerMillion(model, "cached_prompt")}
              />
              <Price
                label="Output"
                perMillion
                value={pricePerMillion(model, "completion")}
              />
              <Price label="Context" value={formatContext(model)} />
            </dl>
          </article>
        ))}
      </div>
    </div>
  );
};
