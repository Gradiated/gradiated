import type { Meta, StoryObj } from "@storybook/react-vite";

import {
  glm_5_3_flash,
  qwen3_0_6b,
  qwen3_32b,
} from "@/stories/base-model-configs";
import {
  AdapterLayerMap,
  adapterLayerModules,
  baseModelStructure,
} from "./adapter-layer-map";

const tensors = (layers: Iterable<number>, modules: string[]) =>
  [...layers].flatMap((layer) =>
    modules.flatMap((module) =>
      ["lora_A", "lora_B"].map(
        (part) =>
          `base_model.model.model.layers.${layer}.${module}.${part}.weight`,
      ),
    ),
  );
const range = (start: number, end: number) =>
  Array.from({ length: end - start }, (_, index) => start + index);
const attention = ["q_proj", "k_proj", "v_proj", "o_proj"].map(
  (module) => `self_attn.${module}`,
);
const mlp = ["gate_proj", "up_proj", "down_proj"].map(
  (module) => `mlp.${module}`,
);

const meta = {
  title: "Pages/Training/Blocks/Adapter layer map",
  parameters: { layout: "fullscreen" },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const story = (config: unknown, names: string[]): Story => ({
  render: () => (
    <div className="min-h-screen bg-background p-8">
      <div className="max-w-[33rem]">
        <AdapterLayerMap
          adapted={adapterLayerModules(names)}
          base={config ? baseModelStructure(config) : undefined}
        />
      </div>
    </div>
  ),
});

export const QwenAttentionOnly = story(
  qwen3_0_6b,
  tensors(range(0, 28), attention),
);
export const QwenAllProjections = story(
  qwen3_0_6b,
  tensors(range(0, 28), [...attention, ...mlp]),
);
export const Qwen32BTopHalf = story(
  qwen3_32b,
  tensors(range(32, 64), [...attention, ...mlp]),
);
export const Qwen32BEveryFourthLayer = story(
  qwen3_32b,
  tensors(
    range(0, 64).filter((layer) => layer % 4 === 0),
    ["self_attn.q_proj", "self_attn.v_proj"],
  ),
);
export const GlmSparseAttentionLayers = story(
  glm_5_3_flash,
  tensors(
    glm_5_3_flash.layer_types.flatMap((type, layer) =>
      type === "deepseek_sparse_attention" ? [layer] : [],
    ),
    ["self_attn.q_b_proj", "self_attn.kv_b_proj"],
  ),
);
export const GlmAllAttention = story(glm_5_3_flash, [
  ...tensors(
    glm_5_3_flash.layer_types.flatMap((type, layer) =>
      type === "linear_attention" ? [layer] : [],
    ),
    attention,
  ),
  ...tensors(
    glm_5_3_flash.layer_types.flatMap((type, layer) =>
      type === "deepseek_sparse_attention" ? [layer] : [],
    ),
    [
      "self_attn.q_a_proj",
      "self_attn.q_b_proj",
      "self_attn.kv_a_proj_with_mqa",
      "self_attn.kv_b_proj",
      "self_attn.o_proj",
    ],
  ),
]);
export const ManyLayers = story(
  { ...qwen3_32b, num_hidden_layers: 128 },
  tensors(range(0, 128), attention),
);
export const UnknownBaseStructure = story(
  undefined,
  tensors(range(0, 40), ["self_attn.q_b_proj"]),
);
export const UnknownModuleLayout = story(
  { num_hidden_layers: 61, model_type: "deepseek_v4" },
  tensors(range(0, 20), ["self_attn.q_b_proj"]),
);
export const Loading: Story = {
  render: () => (
    <div className="min-h-screen bg-background p-8">
      <div className="max-w-[33rem]">
        <AdapterLayerMap
          adapted={new Map([["self_attn.q_proj", new Set([0])]])}
          loading
        />
      </div>
    </div>
  ),
};
