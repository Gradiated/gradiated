/**
 * Service tiers and their code samples.
 *
 * MIRRORS src/components/ServiceTierSection.tsx, which is the live site's
 * version of this section and does not export its data. The claims here —
 * 2.3x, 20%, 50% — are commercial statements, so the two copies must not be
 * allowed to drift: when the live section is replaced by this one, delete this
 * file and export from a single place instead.
 *
 * One deliberate difference already: the descriptions drop the leading "For",
 * because here they sit under a "Best suited for" label and the live ones do
 * not. Carry that back if the label goes with them.
 */

export type Tier = {
  /** The multiplier or percentage, set large. */
  claim: string;
  /** What that number is a claim about. */
  claimNote: string;
  description: string;
  id: "default" | "fast" | "flex";
  name: string;
};

export const TIERS: readonly Tier[] = [
  {
    claim: "2.3x",
    claimNote: "faster inference than other providers",
    description: "Interactive workloads where response time matters most.",
    id: "fast",
    name: "Faster",
  },
  {
    claim: "20%",
    claimNote: "cheaper than other providers",
    description: "Production workloads that need a balance of speed and cost.",
    id: "default",
    name: "Default",
  },
  {
    claim: "50%",
    claimNote: "cheaper than other providers",
    description:
      "Background agents that can trade response time for lower cost.",
    id: "flex",
    name: "Flex",
  },
] as const;

export type Sdk = "anthropic" | "openai";
export type Language = "node" | "python";

/** The snippet for one combination. The tier is the only part that varies. */
export const snippetFor = (
  sdk: Sdk,
  language: Language,
  tier: Tier["id"],
): string => {
  if (language === "node") {
    return sdk === "anthropic"
      ? `import Anthropic from "@anthropic-ai/sdk";

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
});`
      : `import OpenAI from "openai";

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

  return sdk === "anthropic"
    ? `from anthropic import Anthropic

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
)`
    : `from openai import OpenAI

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
