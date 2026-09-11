import { Check, Copy, KeyRound } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { connectSnippet, type ConnectClient } from "@/lib/connect-snippets";
import { slugifyTaskInput, taskSlugError } from "@/lib/task-slug";
import { useMockFineTuning } from "@/store/mock-fine-tuning";

/** Same shape as the docs: a language tab row, then the SDK variant inside the code block. */
const LANGUAGES: {
  label: string;
  variants: { label: string; client: ConnectClient }[];
}[] = [
  {
    label: "Python",
    variants: [
      { label: "OpenAI SDK", client: "openai-python" },
      { label: "Anthropic SDK", client: "anthropic-python" },
    ],
  },
  {
    label: "Node",
    variants: [
      { label: "OpenAI SDK", client: "openai-node" },
      { label: "Anthropic SDK", client: "anthropic-node" },
    ],
  },
  {
    label: "cURL",
    variants: [
      { label: "OpenAI", client: "curl-openai" },
      { label: "Anthropic", client: "curl-anthropic" },
    ],
  },
];

export const ConnectSnippet = () => {
  const {
    connect_api_key,
    connect_task_slug,
    createApiKey,
    setConnectTaskSlug,
  } = useMockFineTuning();
  const [language, setLanguage] = useState(LANGUAGES[0]!.label);
  const [variantIndex, setVariantIndex] = useState(0);
  const [copied, setCopied] = useState(false);
  const [keyCopied, setKeyCopied] = useState(false);

  const lang = LANGUAGES.find((l) => l.label === language) ?? LANGUAGES[0]!;
  const variant =
    lang.variants[Math.min(variantIndex, lang.variants.length - 1)]!;
  const slugError = taskSlugError(connect_task_slug);
  const code = connectSnippet(variant.client, {
    gradiatedKey: connect_api_key ?? "grad_…",
    taskSlug: connect_task_slug || "your-task",
  });

  const copy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };
  const copyKey = async () => {
    await navigator.clipboard.writeText(
      `GRADIATED_API_KEY=${connect_api_key ?? ""}`,
    );
    setKeyCopied(true);
    window.setTimeout(() => setKeyCopied(false), 1500);
  };

  return (
    <div className="min-w-0 space-y-4">
      <div className="flex items-center gap-3">
        <label htmlFor="connect-task" className="text-sm font-medium">
          Task
        </label>
        <Input
          id="connect-task"
          value={connect_task_slug}
          onChange={(e) => setConnectTaskSlug(slugifyTaskInput(e.target.value))}
          placeholder="support-triage"
          className="h-8 max-w-xs font-mono text-xs"
        />
        {slugError && connect_task_slug ? (
          <span className="text-xs text-destructive">{slugError}</span>
        ) : null}
      </div>

      {connect_api_key ? (
        <div>
          <div className="flex items-center gap-2">
            <code className="flex-1 truncate rounded-md border bg-muted px-3 py-1.5 font-mono text-xs">
              GRADIATED_API_KEY={connect_api_key}
            </code>
            <Button
              variant="outline"
              size="icon-sm"
              aria-label="Copy key"
              onClick={copyKey}
            >
              {keyCopied ? <Check /> : <Copy />}
            </Button>
          </div>
          <p className="mt-1.5 text-xs text-muted-foreground">
            Shown once — set it as an environment variable.
          </p>
        </div>
      ) : (
        <div className="flex items-center gap-3">
          <Button variant="outline" size="sm" onClick={createApiKey}>
            <KeyRound className="size-4" />
            Create API key
          </Button>
          <span className="text-xs text-muted-foreground">
            or use an existing key from{" "}
            <a href="/api-keys" className="underline">
              API keys
            </a>
          </span>
        </div>
      )}

      <Tabs
        value={language}
        onValueChange={(v) => {
          setLanguage(v);
          setVariantIndex(0);
        }}
      >
        <TabsList className="h-9">
          {LANGUAGES.map((l) => (
            <TabsTrigger
              key={l.label}
              value={l.label}
              className="h-9 px-2.5 text-xs"
            >
              {l.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      <div className="min-w-0 max-w-full overflow-hidden rounded-lg border bg-muted">
        <div className="flex items-center justify-between border-b px-3">
          <div role="tablist" className="flex gap-4">
            {lang.variants.map((v, i) => (
              <button
                key={v.label}
                type="button"
                role="tab"
                aria-selected={i === variantIndex}
                onClick={() => setVariantIndex(i)}
                className={`-mb-px border-b-2 py-2 font-mono text-[10px] font-medium uppercase tracking-[0.06em] ${
                  i === variantIndex
                    ? "border-foreground text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground"
                }`}
              >
                {v.label}
              </button>
            ))}
          </div>
          <Button
            variant="ghost"
            size="icon-xs"
            aria-label="Copy snippet"
            onClick={copy}
          >
            {copied ? <Check /> : <Copy />}
          </Button>
        </div>
        <pre className="overflow-x-auto p-3 text-[11px] leading-5">
          <code>{code}</code>
        </pre>
      </div>
    </div>
  );
};
