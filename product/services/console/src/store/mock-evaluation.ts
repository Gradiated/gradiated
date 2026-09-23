import type {
  AssistantReply,
  EvaluationResultLine,
  EvaluationSummary,
  TraceGenerationRow,
  TraceMessage,
  VersionView,
} from "@/store/fine-tuning-types";
import { seededRandom } from "@/store/mock-values";

const EVALUATION_RESULTS_SHOWN = 12;

const replyText = (reply: AssistantReply) =>
  "tool_call" in reply
    ? `${reply.tool_call.name}(${reply.tool_call.arguments})`
    : reply.content;

const degradedReplyText = (reply: AssistantReply) =>
  "tool_call" in reply
    ? `${reply.tool_call.name}(${reply.tool_call.arguments.replace(/"priority":"[a-z]+"/, '"priority":"low"')})`
    : `${reply.content.split(". ")[0]}.`;

const verdictFor = (
  draw: number,
  { win, tie, loss }: EvaluationSummary["vs_comparison"],
): EvaluationResultLine["verdict"] => {
  if (draw < win) return "better";
  if (draw < win + tie) return "equivalent";
  if (draw < win + tie + loss) return "worse";

  return "unresolved";
};

export const evaluationResults = ({
  version,
  conversations,
  traces,
  taskSlug,
  limit = EVALUATION_RESULTS_SHOWN,
}: {
  version: VersionView;
  conversations: Readonly<Record<string, readonly TraceMessage[]>>;
  traces: readonly TraceGenerationRow[];
  taskSlug: string;
  limit?: number;
}): EvaluationResultLine[] => {
  const traceIds = new Set(
    traces.filter((row) => row.task === taskSlug).map((row) => row.trace_id),
  );
  const examples = [...traceIds].flatMap((traceId) => {
    const messages = conversations[traceId] ?? [];
    const request = messages.find((message) => message.role === "user");
    const reply = messages.find((message) => message.role === "assistant");

    return request?.role === "user" && reply?.role === "assistant"
      ? [{ request: request.content, reply }]
      : [];
  });
  const random = seededRandom(version.model.id);
  const count = Math.min(limit, version.summary.holdout_examples);

  return Array.from(
    { length: count },
    (_, index) => examples[index % examples.length],
  ).flatMap((example, index) => {
    if (!example) return [];

    const verdict = verdictFor(random(), version.summary.vs_comparison);
    const canonical = replyText(example.reply);
    const degraded = degradedReplyText(example.reply);

    return [
      {
        index: index + 1,
        request_preview: example.request,
        comparison_response: verdict === "better" ? degraded : canonical,
        fine_tuned_response: verdict === "worse" ? degraded : canonical,
        verdict,
      },
    ];
  });
};
