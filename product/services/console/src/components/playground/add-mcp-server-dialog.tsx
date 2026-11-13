import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Field,
  FieldDescription,
  FieldError,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  credentialHeaders,
  MCP_CATALOG,
  type InstalledMcpServer,
  type McpCatalogEntry,
} from "@/lib/mcp";
import { cn } from "@/lib/utils";

const customServerError = (name: string, url: string): string | null => {
  if (!name.trim()) return "Name the server.";

  try {
    const parsed = new URL(url);

    return parsed.protocol === "https:" ? null : "Use an https:// URL.";
  } catch {
    return "Enter the server's Streamable HTTP URL.";
  }
};

export const AddMcpServerDialog = ({
  open,
  installed,
  onOpenChange,
  onAdd,
}: {
  open: boolean;
  installed: readonly InstalledMcpServer[];
  onOpenChange: (open: boolean) => void;
  onAdd: (server: InstalledMcpServer) => void;
}) => {
  const [tab, setTab] = useState("catalog");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Add an MCP server</DialogTitle>
          <DialogDescription>
            The playground calls the server through Gradiated when a model uses
            its tools. Credentials stay in this browser and are cleared when you
            sign out.
          </DialogDescription>
        </DialogHeader>
        {open ? (
          <Tabs value={tab} onValueChange={setTab}>
            <TabsList>
              <TabsTrigger value="catalog">Well-known</TabsTrigger>
              <TabsTrigger value="custom">Custom</TabsTrigger>
            </TabsList>
            <TabsContent value="catalog">
              <CatalogForm installed={installed} onAdd={onAdd} />
            </TabsContent>
            <TabsContent value="custom">
              <CustomForm onAdd={onAdd} />
            </TabsContent>
          </Tabs>
        ) : null}
      </DialogContent>
    </Dialog>
  );
};

const CatalogForm = ({
  installed,
  onAdd,
}: {
  installed: readonly InstalledMcpServer[];
  onAdd: (server: InstalledMcpServer) => void;
}) => {
  const available = MCP_CATALOG.filter(
    (entry) => !installed.some(({ url }) => url === entry.url),
  );
  const [selectedId, setSelectedId] = useState(available[0]?.id);
  const [secret, setSecret] = useState("");
  const selected = available.find(({ id }) => id === selectedId);
  const credential = selected?.credential;
  const missing =
    credential?.kind === "header" && credential.required && !secret.trim();

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!selected || missing) return;

    onAdd({
      id: crypto.randomUUID(),
      name: selected.name,
      url: selected.url,
      headers: credentialHeaders(selected.credential, secret),
      enabled: true,
    });
  };

  if (!available.length)
    return (
      <p className="py-6 text-center text-sm text-muted-foreground">
        Every well-known server is already added.
      </p>
    );

  return (
    <form className="space-y-4" onSubmit={submit}>
      <div
        role="radiogroup"
        aria-label="Server"
        className="max-h-64 space-y-1 overflow-y-auto"
      >
        {available.map((entry) => (
          <CatalogOption
            key={entry.id}
            entry={entry}
            selected={entry.id === selectedId}
            onSelect={() => {
              setSelectedId(entry.id);
              setSecret("");
            }}
          />
        ))}
      </div>
      {credential?.kind === "header" ? (
        <Field>
          <FieldLabel htmlFor="mcp-server-secret">
            {credential.label}
          </FieldLabel>
          <Input
            id="mcp-server-secret"
            type="password"
            value={secret}
            autoComplete="off"
            data-1p-ignore="true"
            onChange={(event) => setSecret(event.target.value)}
          />
          <FieldDescription>{credential.help}</FieldDescription>
        </Field>
      ) : null}
      <DialogFooter>
        <Button type="submit" disabled={!selected || missing}>
          Add {selected?.name ?? "server"}
        </Button>
      </DialogFooter>
    </form>
  );
};

const CatalogOption = ({
  entry,
  selected,
  onSelect,
}: {
  entry: McpCatalogEntry;
  selected: boolean;
  onSelect: () => void;
}) => (
  <button
    type="button"
    role="radio"
    aria-checked={selected}
    className={cn(
      "w-full rounded-lg border px-3 py-2 text-left text-sm transition-colors hover:bg-muted/60",
      selected && "border-ring bg-muted/60",
    )}
    onClick={onSelect}
  >
    <span className="font-medium">{entry.name}</span>
    <span className="block text-muted-foreground">{entry.description}</span>
  </button>
);

const CustomForm = ({
  onAdd,
}: {
  onAdd: (server: InstalledMcpServer) => void;
}) => {
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [header, setHeader] = useState("Authorization");
  const [value, setValue] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const error = customServerError(name, url);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setSubmitted(true);
    if (error) return;

    onAdd({
      id: crypto.randomUUID(),
      name: name.trim(),
      url: url.trim(),
      headers: header.trim() && value ? { [header.trim()]: value } : {},
      enabled: true,
    });
  };

  return (
    <form className="space-y-4" onSubmit={submit}>
      <Field>
        <FieldLabel htmlFor="mcp-server-name">Name</FieldLabel>
        <Input
          id="mcp-server-name"
          value={name}
          maxLength={60}
          autoComplete="off"
          onChange={(event) => setName(event.target.value)}
        />
      </Field>
      <Field>
        <FieldLabel htmlFor="mcp-server-url">URL</FieldLabel>
        <Input
          id="mcp-server-url"
          type="url"
          value={url}
          placeholder="https://example.com/mcp"
          autoComplete="off"
          onChange={(event) => setUrl(event.target.value)}
        />
        <FieldDescription>
          A remote server that speaks Streamable HTTP.
        </FieldDescription>
      </Field>
      <div className="grid gap-3 sm:grid-cols-[10rem_minmax(0,1fr)]">
        <Field>
          <FieldLabel htmlFor="mcp-server-header">Header</FieldLabel>
          <Input
            id="mcp-server-header"
            value={header}
            autoComplete="off"
            onChange={(event) => setHeader(event.target.value)}
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="mcp-server-header-value">Value</FieldLabel>
          <Input
            id="mcp-server-header-value"
            type="password"
            value={value}
            placeholder="Bearer …"
            autoComplete="off"
            data-1p-ignore="true"
            onChange={(event) => setValue(event.target.value)}
          />
        </Field>
      </div>
      {submitted && error ? <FieldError>{error}</FieldError> : null}
      <DialogFooter>
        <Button type="submit">Add server</Button>
      </DialogFooter>
    </form>
  );
};
