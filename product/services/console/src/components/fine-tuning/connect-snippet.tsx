import { Link } from "@tanstack/react-router";
import { KeyRound } from "lucide-react";
import { useState } from "react";

import { useCreateApiKey } from "@/api/queries";
import { CopyStateIcon } from "@/components/copy-state-icon";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { copyLabel, useCopyToClipboard } from "@/hooks/use-copy-to-clipboard";
import { useProductContext } from "@/hooks/use-product-context";
import { connectSnippet, type ConnectClient } from "@/lib/connect-snippets";
import { errorMessage } from "@/lib/errors";
import { slugifyTaskInput, taskSlugError } from "@/lib/task-slug";
import { useConnectFlow } from "@/store/connect-flow";

const LANGUAGES = [
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
] as const satisfies readonly {
  label: string;
  variants: readonly { label: string; client: ConnectClient }[];
}[];

export const ConnectSnippet = () => {
  const taskSlug = useConnectFlow((state) => state.taskSlug);
  const setTaskSlug = useConnectFlow((state) => state.setTaskSlug);
  const [client, setClient] = useState<ConnectClient>(
    LANGUAGES[0].variants[0].client,
  );
  const snippetCopy = useCopyToClipboard();

  const language =
    LANGUAGES.find((candidate) =>
      candidate.variants.some((variant) => variant.client === client),
    ) ?? LANGUAGES[0];
  const code = connectSnippet(client, taskSlug || "your-task");
  const slugError = taskSlugError(taskSlug);

  const selectLanguage = (label: string) => {
    const next = LANGUAGES.find((candidate) => candidate.label === label);
    if (next) setClient(next.variants[0].client);
  };

  const selectClient = (value: string) => {
    const next = language.variants.find((variant) => variant.client === value);
    if (next) setClient(next.client);
  };

  return (
    <div className="min-w-0 space-y-4">
      <div className="flex items-center gap-3">
        <label htmlFor="connect-task" className="text-sm font-medium">
          Task
        </label>
        <Input
          id="connect-task"
          value={taskSlug}
          onChange={(event) =>
            setTaskSlug(slugifyTaskInput(event.target.value))
          }
          placeholder="support-triage"
          className="h-8 max-w-xs font-mono text-xs"
        />
        {slugError && taskSlug ? (
          <span className="text-xs text-destructive">{slugError}</span>
        ) : null}
      </div>

      <ConnectApiKey />

      <Tabs value={language.label} onValueChange={selectLanguage}>
        <TabsList className="h-9">
          {LANGUAGES.map((candidate) => (
            <TabsTrigger
              key={candidate.label}
              value={candidate.label}
              className="h-9 px-2.5 text-xs"
            >
              {candidate.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      <div className="min-w-0 max-w-full overflow-hidden rounded-lg border bg-muted">
        <div className="flex items-center justify-between border-b px-3">
          <Tabs value={client} onValueChange={selectClient} className="w-auto">
            <TabsList className="h-auto gap-4 border-b-0">
              {language.variants.map((variant) => (
                <TabsTrigger
                  key={variant.client}
                  value={variant.client}
                  className="h-auto px-0 py-2 font-mono text-[10px] uppercase tracking-[0.06em]"
                >
                  {variant.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          <Button
            variant="ghost"
            size="icon-xs"
            aria-label={copyLabel(snippetCopy.state, "Copy snippet")}
            onClick={() => void snippetCopy.copy(code)}
          >
            <CopyStateIcon state={snippetCopy.state} />
          </Button>
        </div>
        <pre className="overflow-x-auto p-3 text-[11px] leading-5">
          <code>{code}</code>
        </pre>
      </div>
    </div>
  );
};

const ConnectApiKey = () => {
  const { organizationId, workspaceId } = useProductContext();
  const [secret, setSecret] = useState<string | null>(null);
  const keyCopy = useCopyToClipboard();
  const create = useCreateApiKey(organizationId, workspaceId);

  if (secret) {
    const variable = `GRADIATED_API_KEY=${secret}`;

    return (
      <div className="flex items-center gap-2">
        <code className="flex-1 truncate rounded-md border bg-muted px-3 py-1.5 font-mono text-xs">
          {variable}
        </code>
        <Button
          variant="outline"
          size="icon-sm"
          aria-label={copyLabel(keyCopy.state, "Copy key")}
          onClick={() => void keyCopy.copy(variable)}
        >
          <CopyStateIcon state={keyCopy.state} />
        </Button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3">
      <Button
        variant="outline"
        size="sm"
        disabled={!workspaceId || create.isPending}
        onClick={() =>
          create.mutate(
            { name: "Training" },
            { onSuccess: (created) => setSecret(created.secret) },
          )
        }
      >
        <KeyRound className="size-4" />
        Create API key
      </Button>
      <Link to="/api-keys" className="text-xs text-muted-foreground underline">
        API keys
      </Link>
      {create.isError ? (
        <span role="alert" className="text-xs text-destructive">
          {errorMessage(create.error, "The API key could not be created.")}
        </span>
      ) : null}
    </div>
  );
};
