import type { Meta, StoryObj } from "@storybook/react-vite";
import { QueryClientProvider } from "@tanstack/react-query";
import { delay, http, HttpResponse } from "msw";
import { useRef, useState } from "react";
import { userEvent, within } from "storybook/test";

import type { getAdapterConfiguration } from "@/api/training";
import { handlers } from "@/stories/handlers";
import {
  deepseekAttentionWeights,
  deepseekHeadWeights,
  deepseekStructure,
  glmAttentionWeights,
  glmStructure,
  kimiStructure,
  kimiWeights,
  qwen32bStructure,
  qwen32bWeights,
} from "@/stories/adapter-weights-fixture";
import { createStoryQueryClient } from "@/stories/query-client";
import AdapterExplorer from "./explorer";
import type { AdapterWeights, BaseStructure } from "./model";
import { adapterWeightsQuery, baseStructureQuery } from "./queries";

type Configuration = Awaited<ReturnType<typeof getAdapterConfiguration>>;

type Args = {
  title: string;
  baseModelId: string;
  weights?: AdapterWeights;
  structure?: BaseStructure;
};

const Explorer = ({ title, baseModelId, weights, structure }: Args) => {
  const target = {
    workspaceId: "storybook-workspace",
    task: "story",
    versionId: "story-version",
    baseModelId,
  };
  const [client] = useState(() => {
    const queryClient = createStoryQueryClient();
    if (weights)
      queryClient.setQueryData(adapterWeightsQuery(target).queryKey, weights);
    if (structure)
      queryClient.setQueryData(
        baseStructureQuery(target).queryKey,
        structure as Configuration,
      );
    return queryClient;
  });
  const escape = useRef(() => false);

  return (
    <QueryClientProvider client={client}>
      <div className="h-screen bg-[#0b0d10] p-4">
        <div className="relative h-full overflow-hidden rounded-2xl border border-white/10">
          <AdapterExplorer
            target={target}
            title={title}
            baseModelId={baseModelId}
            escape={escape}
          />
        </div>
      </div>
    </QueryClientProvider>
  );
};

// Every story's adapter is synthetic (see adapter-weights-fixture.ts); layer
// counts, expert layouts and matrix shapes follow the real configs.
const meta = {
  title: "Pages/Training/Adapter explorer",
  component: Explorer,
  render: (args, { id }) => <Explorer key={id} {...args} />,
} satisfies Meta<typeof Explorer>;

export default meta;
type Story = StoryObj<typeof meta>;

const deepseek = {
  baseModelId: "deepseek/deepseek-v4.1-flash-1017",
  structure: deepseekStructure,
};

export const DeepSeekV41FlashHeadAdapter: Story = {
  args: {
    ...deepseek,
    title: "support-bot/flash-head",
    weights: deepseekHeadWeights,
  },
};

export const DeepSeekV41FlashAttention: Story = {
  args: {
    ...deepseek,
    title: "support-bot/flash-attention",
    weights: deepseekAttentionWeights,
  },
};

export const Glm53FlashAttention: Story = {
  args: {
    title: "triage/glm-v3",
    baseModelId: "z-ai/glm-5.3-flash",
    structure: glmStructure,
    weights: glmAttentionWeights,
  },
};

export const KimiK31ProScale: Story = {
  args: {
    title: "research/kimi-attention",
    baseModelId: "moonshotai/kimi-k3.1-pro",
    structure: kimiStructure,
    weights: kimiWeights,
  },
};

export const Qwen3_32BAllProjections: Story = {
  args: {
    title: "summaries/qwen-v2",
    baseModelId: "Qwen/Qwen3-32B",
    structure: qwen32bStructure,
    weights: qwen32bWeights,
  },
};

export const LayerFocused: Story = {
  args: DeepSeekV41FlashAttention.args,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(
      await canvas.findByRole("button", { name: /^Layer 27:/ }),
    );
    await canvas.findByRole("heading", { name: "Layer 27" });
  },
};

export const ProjectionSelected: Story = {
  args: Glm53FlashAttention.args,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(
      await canvas.findByRole("button", { name: /^Layer 19:/ }),
    );
    await userEvent.click(
      await canvas.findByRole("button", { name: /q_b_proj/ }),
    );
    await canvas.findByText("Update directions");
  },
};

export const HeadSelected: Story = {
  args: DeepSeekV41FlashHeadAdapter.args,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(
      await canvas.findByRole("button", { name: /lm_head/ }),
    );
    await canvas.findByText("Where in the matrix");
  },
};

const weightsPath =
  "/api/v1/workspaces/:workspaceId/tasks/:task/versions/:versionId/adapter/weights";
const configurationPath =
  "/api/v1/workspaces/:workspaceId/adapter-configurations/:modelId";

export const ReadingWeights: Story = {
  args: { ...deepseek, title: "support-bot/flash-head" },
  parameters: {
    msw: [
      http.get(weightsPath, async () => {
        await delay("infinite");
        return HttpResponse.json({});
      }),
      http.get(configurationPath, () => HttpResponse.json(deepseekStructure)),
      ...handlers,
    ],
  },
};

export const WeightsUnavailable: Story = {
  args: { ...deepseek, title: "support-bot/flash-head" },
  tags: ["request-failure"],
  parameters: {
    msw: [
      http.get(weightsPath, () =>
        HttpResponse.json(
          {
            type: "about:blank",
            title: "Service Unavailable",
            status: 503,
            detail:
              "The adapter weights could not be summarized. Please try again.",
          },
          {
            status: 503,
            headers: { "content-type": "application/problem+json" },
          },
        ),
      ),
      http.get(configurationPath, () => HttpResponse.json(deepseekStructure)),
      ...handlers,
    ],
  },
};
