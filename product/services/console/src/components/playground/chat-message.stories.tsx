import type { Meta, StoryObj } from "@storybook/react-vite";

import { ChatMessage } from "@/components/playground/chat-message";
import type { PlaygroundMessage } from "@/lib/playground";

const usage = {
  cost: 0.000021,
  prompt_tokens: 24,
  completion_tokens: 31,
  total_tokens: 55,
  prompt_tokens_details: { cached_tokens: 0 },
  completion_tokens_details: { reasoning_tokens: 14 },
};

const stats = { firstTokenMs: 180, totalMs: 820, usage };

const question: PlaygroundMessage = {
  id: "question",
  role: "user",
  content: "Write a haiku about fast inference.",
};

const reply = (
  patch: Partial<Extract<PlaygroundMessage, { role: "assistant" }>>,
): PlaygroundMessage => ({
  id: "reply",
  role: "assistant",
  content:
    "Tokens stream like rain\nfirst light reaches the answer\nbefore the thought ends",
  reasoning: "",
  status: "complete",
  ...patch,
});

const Conversation = ({ messages }: { messages: PlaygroundMessage[] }) => (
  <div className="mx-auto max-w-3xl space-y-6 p-8">
    {messages.map((message) => (
      <ChatMessage key={message.id} message={message} />
    ))}
  </div>
);

const meta = {
  title: "Pages/Playground/Blocks/Chat message",
  component: Conversation,
} satisfies Meta<typeof Conversation>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Complete: Story = {
  args: { messages: [question, reply({ stats })] },
};
export const WithEnergyEstimate: Story = {
  args: {
    messages: [
      question,
      reply({
        stats: { ...stats, usage: { ...usage, estimated_joules: 12.4 } },
      }),
    ],
  },
};
export const WithReasoning: Story = {
  args: {
    messages: [
      question,
      reply({
        reasoning:
          "A haiku needs five, seven and five syllables. Speed is the theme.",
        stats,
      }),
    ],
  },
};
export const Thinking: Story = {
  args: {
    messages: [
      question,
      reply({
        content: "",
        reasoning: "A haiku needs five, seven and five syllables.",
        status: "streaming",
      }),
    ],
  },
};
export const Streaming: Story = {
  args: {
    messages: [
      question,
      reply({
        content: "Tokens stream like rain\nfirst light",
        status: "streaming",
      }),
    ],
  },
};
export const Stopped: Story = {
  args: {
    messages: [
      question,
      reply({
        content: "Tokens stream like rain",
        status: "stopped",
        stats: { firstTokenMs: 180, totalMs: 400, usage: undefined },
      }),
    ],
  },
};
export const Failed: Story = {
  args: {
    messages: [
      question,
      reply({
        content: "",
        status: "failed",
        error:
          "The organization balance is too low. Top up in Billing to continue.",
        stats: { firstTokenMs: undefined, totalMs: 120, usage: undefined },
      }),
    ],
  },
};

export const Pirate: Story = {
  args: {
    messages: [
      {
        ...question,
        content: "Talk like a pirate and help me pick an adventure.",
      },
      reply({
        content: `So, what be our course, Captain? Say the word and this old pirate'll follow:

- 🗺️ **Chart a tale** — treasure, curses, sea monsters, or all three?
- 🎶 **Sing a shanty** — loud enough to wake the kraken!
- 🧭 **Dish out pirate wisdom** — for calm seas or stormy times?
- ⚓ **Just chat** — no destination, no hurry, just good company.

Point the compass, matey — I be right behind ye! Arrr!`,
        stats: {
          firstTokenMs: 1100,
          totalMs: 1511,
          usage: { ...usage, completion_tokens: 211, cost: 0.000735 },
        },
      }),
    ],
  },
};

export const RichText: Story = {
  args: {
    messages: [
      reply({
        content: `# A field guide to fast replies

Use **bold for emphasis**, *italics for nuance*, and ~~strikethrough for old ideas~~. Keep model IDs like \`example/model\` easy to spot.

## Before you sail

1. Pick your model.
2. Set a token budget.
   - Start small for quick experiments.
   - Increase it for longer answers.
3. Send your first message.

> The first token starts the conversation.
> A useful answer keeps it going.

### Read more

Visit the [Gradiated docs](https://gradiated.com/docs) for API details.

---

A new paragraph gives the next idea room to breathe.`,
        stats,
      }),
    ],
  },
};

export const CodeBlocks: Story = {
  args: {
    messages: [
      {
        ...question,
        content:
          "Show me a Python example, a JSON result, and a shell command.",
      },
      reply({
        content: `Call the API with \`client.chat.completions.create\`:

\`\`\`python
from openai import OpenAI

client = OpenAI(base_url="https://api.gradiated.com/v1")
response = client.chat.completions.create(
    model="example/model",
    messages=[{"role": "user", "content": "Hello, Captain!"}],
)
print(response.choices[0].message.content)
\`\`\`

The result is ordinary JSON:

\`\`\`json
{
  "role": "assistant",
  "content": "Ahoy, matey!"
}
\`\`\`

An unlabelled block preserves whitespace too:

\`\`\`
ship     destination
Aurora   Treasure Island
\`\`\`

\`\`\`bash
printf '%s\\n' 'A deliberately long line stays inside the code block and scrolls horizontally on small screens instead of widening the entire conversation.'
\`\`\``,
        stats,
      }),
    ],
  },
};

export const TablesAndTasks: Story = {
  args: {
    messages: [
      reply({
        content: `## Voyage checklist

- [x] Choose a destination
- [x] Pack the compass
- [ ] Recruit a crew

| Route | Conditions | Days at sea |
| :--- | :--- | ---: |
| **Coastal** | Calm waters | 2 |
| Open ocean | *Strong winds* | 5 |
| Northern passage | Ice and fog | 8 |

**Recommendation:** take the coastal route for your first voyage.`,
        stats,
      }),
    ],
  },
};

export const StreamingMarkdown: Story = {
  args: {
    messages: [
      reply({
        status: "streaming",
        content: `## Building your example

Here is the **first step**. The code block is still arriving:

\`\`\`typescript
const crew = ["Captain", "Navigator"];
for (const member of crew) {
  console.log(member`,
      }),
    ],
  },
};

export const LiteralPromptAndSafeContent: Story = {
  args: {
    messages: [
      {
        ...question,
        content:
          "Explain **bold** and `<script>` literally.\nKeep my prompt as typed.",
      },
      reply({
        content: `**This is formatted**, while \`<script>\` is just code.

<script>alert("never execute model output")</script>

[An unsafe link](javascript:alert%281%29) has no active destination.

![Remote images show their description without loading](https://example.com/tracker.png)`,
        stats,
      }),
    ],
  },
};

export const NarrowFormatting: Story = {
  ...CodeBlocks,
  tags: ["mobile"],
  decorators: [
    (Story) => (
      <div className="mx-auto max-w-[390px]">
        <Story />
      </div>
    ),
  ],
};
export const ToolCalls: Story = {
  args: {
    messages: [
      {
        id: "question",
        role: "user",
        content: "Which tasks are in production?",
      },
      reply({
        id: "calls",
        content: "",
        toolCalls: [
          {
            id: "call_1",
            name: "gradiated__list_tasks",
            server: "Gradiated",
            tool: "list_tasks",
            arguments: "{}",
            status: "complete",
            result: JSON.stringify({ data: [{ name: "support-assistant" }] }),
          },
          {
            id: "call_2",
            name: "github__search_issues",
            server: "GitHub",
            tool: "search_issues",
            arguments: '{"query":"label:bug"}',
            status: "failed",
            result: "The GitHub token is missing the issues scope.",
          },
          {
            id: "call_3",
            name: "deepwiki__ask_question",
            server: "DeepWiki",
            tool: "ask_question",
            arguments: '{"repoName":"modelcontextprotocol/specification"}',
            status: "running",
          },
        ],
      }),
    ],
  },
};
