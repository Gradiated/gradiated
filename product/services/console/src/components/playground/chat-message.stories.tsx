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
  title: "Playground/Chat message",
  component: Conversation,
} satisfies Meta<typeof Conversation>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Complete: Story = {
  args: { messages: [question, reply({ stats })] },
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
