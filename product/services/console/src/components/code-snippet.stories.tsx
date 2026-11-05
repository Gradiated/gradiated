import type { Meta, StoryObj } from "@storybook/react-vite";
import { useState } from "react";

import type { HighlightLanguage } from "@/lib/highlight";
import { Canvas } from "@/stories/states";
import { CodeSnippet } from "./code-snippet";

const samples: Record<HighlightLanguage, string> = {
  python: `from openai import OpenAI

client = OpenAI(base_url="https://api.gradiated.com/v1", api_key="gr_live_…")
response = client.chat.completions.create(
    model="z-ai/glm-5.3-flash",
    messages=[{"role": "user", "content": "Hello"}],
)`,
  typescript: `import OpenAI from "openai";

const client = new OpenAI({ baseURL: "https://api.gradiated.com/v1" });
const response = await client.chat.completions.create({
  model: "z-ai/glm-5.3-flash",
  messages: [{ role: "user", content: "Hello" }],
});`,
  bash: `curl https://api.gradiated.com/v1/chat/completions \\
  -H "Authorization: Bearer $GRADIATED_API_KEY" \\
  -d '{"model": "z-ai/glm-5.3-flash", "messages": [{"role": "user", "content": "Hello"}]}'`,
  json: `{
  "model": "z-ai/glm-5.3-flash",
  "messages": [{ "role": "user", "content": "Hello" }]
}`,
};

const options = [
  { value: "python", label: "Python" },
  { value: "typescript", label: "TypeScript" },
  { value: "bash", label: "cURL" },
  { value: "json", label: "JSON" },
] as const;

const meta = { title: "Components/Code snippet" } satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const Snippet = ({ initial }: { initial: HighlightLanguage }) => {
  const [language, setLanguage] = useState<HighlightLanguage>(initial);

  return (
    <Canvas className="max-w-3xl">
      <CodeSnippet
        code={samples[language]}
        language={language}
        value={language}
        options={options}
        onValueChange={setLanguage}
      />
    </Canvas>
  );
};

export const Python: Story = { render: () => <Snippet initial="python" /> };
export const TypeScript: Story = {
  render: () => <Snippet initial="typescript" />,
};
export const Curl: Story = { render: () => <Snippet initial="bash" /> };
export const Json: Story = { render: () => <Snippet initial="json" /> };
