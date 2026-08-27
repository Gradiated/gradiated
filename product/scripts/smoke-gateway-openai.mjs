import OpenAI from "openai";

const apiKey = process.env.GRADIATED_API_KEY;
if (!apiKey) {
  throw new Error("GRADIATED_API_KEY is required");
}

const baseURL =
  process.env.GRADIATED_BASE_URL ?? "https://api.gradiated.com/openai/v1";
const requestedModel = process.env.GRADIATED_MODEL;
const prompt = "Reply with exactly: production-chat-ready";
const client = new OpenAI({ apiKey, baseURL });

const models = await client.models.list();
const availableModels = models.data.filter((model) => model.is_ready !== false);
const model = requestedModel ?? availableModels[0]?.id ?? models.data[0]?.id;

if (!model) {
  throw new Error("The gateway returned no models");
}

const nonStreaming = await client.chat.completions.create({
  model,
  messages: [{ role: "user", content: prompt }],
  max_tokens: 32,
  temperature: 0,
});
const nonStreamingText = nonStreaming.choices[0]?.message?.content?.trim();

if (!nonStreamingText) {
  throw new Error("The non-streaming completion returned no message content");
}

const streaming = await client.chat.completions.create({
  model,
  messages: [{ role: "user", content: prompt }],
  max_tokens: 32,
  temperature: 0,
  stream: true,
});
let streamingText = "";
let streamingChunks = 0;

for await (const chunk of streaming) {
  streamingChunks += 1;
  streamingText += chunk.choices[0]?.delta?.content ?? "";
}

if (!streamingText.trim()) {
  throw new Error("The streaming completion returned no message content");
}

console.log(
  JSON.stringify(
    {
      status: "passed",
      base_url: baseURL,
      model,
      advertised_models: models.data.map((item) => item.id),
      non_streaming: {
        id: nonStreaming.id,
        finish_reason: nonStreaming.choices[0]?.finish_reason,
        text: nonStreamingText,
        usage: nonStreaming.usage,
      },
      streaming: {
        chunks: streamingChunks,
        text: streamingText.trim(),
      },
    },
    null,
    2,
  ),
);
