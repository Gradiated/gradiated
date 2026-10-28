import { ArrowUp, Square } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

export const ChatComposer = ({
  disabled,
  streaming,
  placeholder,
  onSend,
  onStop,
}: {
  disabled: boolean;
  streaming: boolean;
  placeholder: string;
  onSend: (content: string) => void;
  onStop: () => void;
}) => {
  const [draft, setDraft] = useState("");
  const content = draft.trim();

  const submit = () => {
    if (!content || disabled || streaming) return;

    onSend(content);
    setDraft("");
  };

  return (
    <form
      className="relative rounded-xl border bg-background shadow-xs focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/50"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <Textarea
        aria-label="Message"
        value={draft}
        placeholder={placeholder}
        disabled={disabled}
        rows={2}
        className="max-h-48 min-h-20 resize-none border-0 pr-14 shadow-none focus-visible:ring-0"
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => {
          if (
            event.key !== "Enter" ||
            event.shiftKey ||
            event.nativeEvent.isComposing
          )
            return;

          event.preventDefault();
          submit();
        }}
      />
      <div className="absolute right-2 bottom-2">
        {streaming ? (
          <Button
            type="button"
            size="icon-sm"
            variant="outline"
            aria-label="Stop generating"
            onClick={onStop}
          >
            <Square className="fill-current" />
          </Button>
        ) : (
          <Button
            type="submit"
            size="icon-sm"
            aria-label="Send message"
            disabled={disabled || !content}
          >
            <ArrowUp />
          </Button>
        )}
      </div>
    </form>
  );
};
