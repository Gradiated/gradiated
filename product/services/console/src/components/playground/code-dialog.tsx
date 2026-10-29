import { Code } from "lucide-react";
import { useState } from "react";

import { CodeSnippet } from "@/components/code-snippet";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import type { HighlightLanguage } from "@/lib/highlight";
import {
  CODE_LANGUAGES,
  requestSnippet,
  type CodeLanguage,
  type PlaygroundRequest,
} from "@/lib/playground";

const CODE_HIGHLIGHT: Record<CodeLanguage, HighlightLanguage> = {
  curl: "bash",
  python: "python",
  typescript: "typescript",
};

export const CodeDialog = ({
  request,
  disabled,
}: {
  request: PlaygroundRequest;
  disabled: boolean;
}) => {
  const [language, setLanguage] = useState<CodeLanguage>("curl");
  const snippet = requestSnippet(language, request);

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline" disabled={disabled}>
          <Code />
          Code
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Code</DialogTitle>
          <DialogDescription>
            Send this conversation from your application with a workspace API
            key in <code className="font-mono">GRADIATED_API_KEY</code>.
          </DialogDescription>
        </DialogHeader>
        <CodeSnippet
          code={snippet}
          language={CODE_HIGHLIGHT[language]}
          value={language}
          options={CODE_LANGUAGES}
          onValueChange={setLanguage}
          copyText="Copy code"
        />
      </DialogContent>
    </Dialog>
  );
};
