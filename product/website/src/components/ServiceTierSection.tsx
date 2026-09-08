import { ArrowRight } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import type { CSSProperties, ReactElement, ReactNode } from "react";

type ServiceTier = "fast" | "default" | "flex";
type Sdk = "openai" | "anthropic";
type Language = "python" | "node";

type TierOption = {
  id: ServiceTier;
  name: string;
  priceChange: string;
  priceNote: string;
  description: string;
};

const TIER_OPTIONS: readonly TierOption[] = [
  {
    id: "fast",
    name: "Fast",
    priceChange: "2.3x",
    priceNote: "faster inference than other providers",
    description: "For interactive workloads where response time matters most.",
  },
  {
    id: "default",
    name: "Default",
    priceChange: "20%",
    priceNote: "cheaper than other providers",
    description:
      "For production workloads that need a balance of speed and cost.",
  },
  {
    id: "flex",
    name: "Flex",
    priceChange: "50%",
    priceNote: "cheaper than other providers",
    description:
      "For background agents that can trade response time for lower cost.",
  },
] as const;

const getSnippet = (
  sdk: Sdk,
  tier: ServiceTier,
  language: Language,
): string => {
  if (language === "node") {
    if (sdk === "anthropic") {
      return `import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic({
  baseURL: "https://api.gradiated.com",
  apiKey: "YOUR_GRADIATED_API_KEY",
});

const message = await client.messages.create({
  model: "YOUR_MODEL_ID",
  max_tokens: 1024,
  messages: [{
    role: "user",
    content: "Explain inference in one sentence.",
  }],
  service_tier: "${tier}",
});`;
    }

    return `import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "https://api.gradiated.com",
  apiKey: "YOUR_GRADIATED_API_KEY",
});

const response = await client.chat.completions.create({
  model: "YOUR_MODEL_ID",
  messages: [{
    role: "user",
    content: "Explain inference in one sentence.",
  }],
  service_tier: "${tier}",
});`;
  }

  if (sdk === "anthropic") {
    return `from anthropic import Anthropic

client = Anthropic(
    base_url="https://api.gradiated.com",
    api_key="YOUR_GRADIATED_API_KEY",
)

message = client.messages.create(
    model="YOUR_MODEL_ID",
    max_tokens=1024,
    messages=[{
        "role": "user",
        "content": "Explain inference in one sentence.",
    }],
    extra_body={"service_tier": "${tier}"},
)`;
  }

  return `from openai import OpenAI

client = OpenAI(
    base_url="https://api.gradiated.com",
    api_key="YOUR_GRADIATED_API_KEY",
)

response = client.chat.completions.create(
    model="YOUR_MODEL_ID",
    messages=[{
        "role": "user",
        "content": "Explain inference in one sentence.",
    }],
    extra_body={"service_tier": "${tier}"},
)`;
};

const CODE_TOKEN_PATTERN =
  /("[^"\n]*")|\b(from|import|const|new|await)\b|\b(\d+)\b|\b([A-Za-z_]\w*)(?=\()|\b([A-Za-z_]\w*)(?=\s*[:=])/g;

const highlightCode = (source: string): ReactNode[] => {
  const tokens: ReactNode[] = [];
  let cursor = 0;

  for (const match of source.matchAll(CODE_TOKEN_PATTERN)) {
    const index = match.index;
    const value = match[0];

    if (index > cursor) tokens.push(source.slice(cursor, index));

    let className = "font-medium text-[var(--code-accent)]";
    if (match[1]) className = "text-[var(--code-string)]";
    if (match[3]) className = "text-[var(--code-string)]";
    if (match[4]) className = "font-medium text-[var(--code-accent)]";
    if (match[5]) className = "text-[var(--code-muted)]";

    tokens.push(
      <span className={className} key={`${index}-${value}`}>
        {value}
      </span>,
    );
    cursor = index + value.length;
  }

  if (cursor < source.length) tokens.push(source.slice(cursor));
  return tokens;
};

export const ServiceTierSection = (): ReactElement => {
  const [tierIndex, setTierIndex] = useState(2);
  const [sdk, setSdk] = useState<Sdk>("openai");
  const [language, setLanguage] = useState<Language>("python");
  const [copiedSdk, setCopiedSdk] = useState<Sdk | null>(null);
  const tier = TIER_OPTIONS[tierIndex] ?? TIER_OPTIONS[1];
  const snippet = getSnippet(sdk, tier.id, language);
  const sliderStyle = {
    "--tier-progress": `${tierIndex * 50}%`,
  } as CSSProperties;

  const copySnippet = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(snippet);
      setCopiedSdk(sdk);
      window.setTimeout(() => setCopiedSdk(null), 1600);
    } catch {
      setCopiedSdk(null);
    }
  };

  const controlButtonClass =
    "cursor-pointer border-0 bg-transparent font-libre text-label font-medium uppercase tracking-label";
  const sdkButtonClass =
    "cursor-pointer border-0 bg-transparent font-libre text-[11px] font-medium uppercase tracking-[0.08em]";

  return (
    <section
      className="relative left-1/2 w-screen -translate-x-1/2 border-y border-line bg-soft"
      aria-labelledby="service-tier-title"
    >
      <div className="mx-auto max-w-content px-7 py-36 max-site:px-[22px] max-site:py-24">
        <header>
          <h2
            className="m-0 max-w-[680px] font-newsreader text-[clamp(44px,5vw,68px)] font-normal leading-[0.96] tracking-[-0.045em] max-site:text-[44px]"
            id="service-tier-title"
          >
            Lower cost when your request can wait.
          </h2>
        </header>

        <div className="mt-[78px] grid grid-cols-[minmax(330px,0.82fr)_minmax(0,1.18fr)] border-b border-b-line max-site:mt-[58px] max-site:grid-cols-1">
          <div className="min-w-0 border-r border-line py-[42px] pr-12 max-site:border-r-0 max-site:border-b max-site:px-0 max-site:py-[34px] max-site:pb-[38px]">
            <p
              className="m-0 flex items-baseline gap-[13px]"
              aria-live="polite"
            >
              <strong className="font-newsreader text-[clamp(48px,5vw,68px)] font-normal leading-[0.94] tracking-[-0.045em] max-site:text-[56px]">
                {tier.priceChange}
              </strong>
              <span className="text-sm text-muted">{tier.priceNote}</span>
            </p>
            <p className="mt-6 min-h-[50px] max-w-[440px] text-sm leading-[1.65] text-muted max-site:min-h-0">
              {tier.description}
            </p>

            <div className="mt-[46px]">
              <div
                className="mb-[15px] flex justify-between font-libre text-[9px] font-medium uppercase tracking-[0.09em] text-muted"
                aria-hidden="true"
              >
                <span>Faster</span>
                <span>Lower cost</span>
              </div>
              <input
                aria-label="Service tier"
                aria-valuetext={`${tier.name}, ${tier.priceChange} ${tier.priceNote}`}
                className="m-0 h-[30px] w-full cursor-pointer appearance-none rounded-none bg-transparent bg-[linear-gradient(var(--ink),var(--ink)),linear-gradient(var(--line),var(--line))] [background-position:0_50%,0_50%] [background-repeat:no-repeat] [background-size:var(--tier-progress)_1px,100%_1px] focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-4 focus-visible:outline-accent [&::-moz-range-thumb]:h-[18px] [&::-moz-range-thumb]:w-[18px] [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border [&::-moz-range-thumb]:border-ink [&::-moz-range-thumb]:bg-ink [&::-moz-range-thumb]:shadow-[inset_0_0_0_5px_var(--paper)] [&::-webkit-slider-thumb]:h-5 [&::-webkit-slider-thumb]:w-5 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:border [&::-webkit-slider-thumb]:border-ink [&::-webkit-slider-thumb]:bg-paper [&::-webkit-slider-thumb]:shadow-[inset_0_0_0_5px_var(--ink)]"
                max="2"
                min="0"
                onChange={(event) => setTierIndex(Number(event.target.value))}
                step="1"
                style={sliderStyle}
                type="range"
                value={tierIndex}
              />
              <div className="mt-1.5 flex justify-between">
                {TIER_OPTIONS.map((option, index) => (
                  <button
                    aria-pressed={index === tierIndex}
                    className={`${controlButtonClass} border-b px-0 pb-1.5 pt-1 ${
                      index === tierIndex
                        ? "border-ink text-ink"
                        : "border-transparent text-muted hover:text-ink"
                    }`}
                    key={option.id}
                    onClick={() => setTierIndex(index)}
                    type="button"
                  >
                    {option.name}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="min-w-0 pb-[38px] pl-12 pt-[42px] max-site:px-0 max-site:pb-[22px] max-site:pt-[38px]">
            <div className="flex min-h-[27px] items-start justify-between gap-5">
              <div className="flex gap-7" role="tablist" aria-label="SDK">
                {(["openai", "anthropic"] as const).map((option) => (
                  <button
                    aria-controls="service-tier-snippet"
                    aria-selected={sdk === option}
                    className={`${sdkButtonClass} border-b px-0 pb-[7px] ${
                      sdk === option
                        ? "border-ink text-ink"
                        : "border-transparent text-muted hover:text-ink"
                    }`}
                    key={option}
                    onClick={() => setSdk(option)}
                    role="tab"
                    type="button"
                  >
                    {option === "openai" ? "OpenAI SDK" : "Anthropic SDK"}
                  </button>
                ))}
              </div>
              <Link
                className="inline-flex shrink-0 items-center gap-1.5 border-b border-line pb-[7px] font-libre text-[11px] font-medium uppercase tracking-[0.08em] text-muted hover:border-ink hover:text-ink"
                to="/docs/quickstart/"
              >
                View docs
                <ArrowRight
                  aria-hidden="true"
                  className="h-3.5 w-3.5"
                  strokeWidth={1.5}
                />
              </Link>
            </div>
            <div
              aria-label={`${sdk === "openai" ? "OpenAI" : "Anthropic"} ${language === "python" ? "Python" : "Node"} example`}
              className="mt-6 overflow-hidden rounded-[12px] border border-[var(--code-border)] bg-[var(--code-bg)] text-[var(--code-fg)] shadow-[var(--code-shadow)]"
              id="service-tier-snippet"
              role="tabpanel"
            >
              <div className="flex h-[46px] items-center justify-between border-b border-[var(--code-border)] px-5">
                <div
                  className="flex h-full items-center gap-5"
                  aria-label="Language"
                >
                  {(["python", "node"] as const).map((option) => (
                    <button
                      aria-pressed={language === option}
                      className={`h-full cursor-pointer border-0 border-b-2 bg-transparent px-0 font-libre text-[10px] font-medium uppercase tracking-[0.08em] ${
                        language === option
                          ? "border-[var(--code-fg)] text-[var(--code-fg)]"
                          : "border-transparent text-[var(--code-muted)] hover:text-[var(--code-fg)]"
                      }`}
                      key={option}
                      onClick={() => setLanguage(option)}
                      type="button"
                    >
                      {option === "python" ? "Python" : "Node"}
                    </button>
                  ))}
                </div>
                <button
                  className="cursor-pointer border-0 bg-transparent py-2 pl-4 font-libre text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--code-muted)] hover:text-[var(--code-fg)]"
                  onClick={copySnippet}
                  type="button"
                >
                  {copiedSdk === sdk ? "Copied" : "Copy"}
                </button>
              </div>
              <pre className="m-0 min-h-[344px] overflow-x-auto px-5 pb-6 pt-6 font-site-mono text-[12.5px] leading-[1.72] text-[var(--code-fg)] [tab-size:2] max-site:min-h-0 max-site:text-[11px]">
                <code className="font-[inherit]">{highlightCode(snippet)}</code>
              </pre>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
