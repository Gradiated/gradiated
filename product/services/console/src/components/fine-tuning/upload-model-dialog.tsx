import { z } from "zod";
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { Check, FileCheck2, Loader2, Upload, X } from "lucide-react";
import { toast } from "sonner";
import {
  MAX_ADAPTER_BYTES,
  MAX_UPLOADED_ADAPTER_RANK,
  CreateModelUploadSchema,
} from "@gradiated/contracts";
import {
  catalogModel,
  type CatalogEntry,
} from "@gradiated/contracts/model-catalog";
import { createModelUpload, completeModelUpload } from "@/api/training";
import { modelsQuery } from "@/api/queries";
import { useProductContext } from "@/hooks/use-product-context";
import { trainingKey } from "@/hooks/use-training";
import { canManageOrganization } from "@/lib/roles";
import { ModelOption, modelOption } from "@/components/model-label";
import { OptionCombobox } from "@/components/option-combobox";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { TaskRow } from "@/store/fine-tuning-types";

const AdapterMetadataSchema = z.object({
  base_model_name_or_path: z.string().min(1),
  revision: z.string().nullish(),
  r: z.number().int().positive().optional(),
});

export const UploadModelDialog = ({
  task,
  onClose,
}: {
  task?: TaskRow;
  onClose: () => void;
}) => {
  const { workspaceId, selectedOrganization } = useProductContext();
  const client = useQueryClient();
  const navigate = useNavigate();
  const models = useQuery(modelsQuery());
  const picker = useRef<HTMLInputElement>(null);
  const [taskName, setTaskName] = useState(task?.name ?? "");
  const [name, setName] = useState("");
  const [baseModel, setBaseModel] = useState(task?.base_model_id ?? "");
  const [revision, setRevision] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [fileError, setFileError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState("Uploading files…");
  const config = files.find((file) => file.name === "adapter_config.json");
  const weights = files.find(
    (file) => file.name === "adapter_model.safetensors",
  );
  const canEdit = canManageOrganization(selectedOrganization);

  const selectFiles = async (incoming: File[]) => {
    setFileError(null);
    if (
      incoming.some(
        (file) =>
          !["adapter_config.json", "adapter_model.safetensors"].includes(
            file.name,
          ),
      )
    ) {
      setFileError(
        "Choose adapter_config.json and adapter_model.safetensors from your PEFT adapter folder.",
      );
      return;
    }
    if (
      incoming.some(
        (file) =>
          file.size === 0 ||
          file.size > (file.name.endsWith(".json") ? 65536 : MAX_ADAPTER_BYTES),
      )
    ) {
      setFileError(
        `Config must be at most 64 KiB and weights at most ${MAX_ADAPTER_BYTES / 1024 ** 2} MiB. Files must not be empty.`,
      );
      return;
    }
    const configFile = incoming.find(
      (file) => file.name === "adapter_config.json",
    );
    if (configFile) {
      try {
        const metadata = AdapterMetadataSchema.parse(
          JSON.parse(await configFile.text()),
        );
        if (metadata.r && metadata.r > MAX_UPLOADED_ADAPTER_RANK) {
          setFileError(
            `Adapter rank ${metadata.r} exceeds the maximum supported upload rank of ${MAX_UPLOADED_ADAPTER_RANK}.`,
          );
          return;
        }

        setRevision(
          metadata.revision && /^[0-9a-f]{40}$/.test(metadata.revision)
            ? metadata.revision
            : "",
        );

        const match = models.data?.data.find(
          (model) =>
            model.id === metadata.base_model_name_or_path ||
            (catalogModel(model.id) as CatalogEntry | undefined)?.training
              ?.model === metadata.base_model_name_or_path,
        );
        if (match) setBaseModel(match.id);
      } catch {
        setFileError(
          "The adapter config must contain valid JSON with a base model name.",
        );
        return;
      }
    }
    setFiles((current) => [
      ...current.filter(
        (file) => !incoming.some((next) => next.name === file.name),
      ),
      ...incoming,
    ]);
  };
  const draft = CreateModelUploadSchema.safeParse({
    task: task?.name ?? taskName.trim(),
    create_task: !task,
    name: name.trim(),
    base_model_id: baseModel,
    base_model_revision: revision.trim(),
    config_size: config?.size,
    weights_size: weights?.size,
  });

  const upload = useMutation({
    mutationFn: async () => {
      if (!canEdit || !config || !weights || !draft.success || fileError)
        throw new Error("Choose both adapter files to continue.");

      setProgress("Uploading files…");
      const grant = await createModelUpload(workspaceId, draft.data);
      await Promise.all(
        (
          [
            [grant.config_url, config],
            [grant.weights_url, weights],
          ] as const
        ).map(async ([url, file]) => {
          const response = await fetch(url, {
            method: "PUT",
            body: file,
            credentials: "omit",
          });
          if (!response.ok)
            throw new Error("File upload failed. Please try again.");
        }),
      );
      setProgress("Validating adapter…");
      return completeModelUpload(workspaceId, grant.id);
    },
    onSuccess: async (version) => {
      await client.invalidateQueries({ queryKey: trainingKey(workspaceId) });
      toast.success("Model version uploaded", {
        description:
          "Your adapter is saved. Serving will be available after qualification.",
      });
      onClose();
      void navigate({ to: "/tasks/$taskId", params: { taskId: version.task } });
    },
  });

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !upload.isPending) onClose();
      }}
    >
      <DialogContent
        className="max-h-[90dvh] overflow-y-auto sm:max-w-xl"
        onInteractOutside={(event) => {
          if (upload.isPending) event.preventDefault();
        }}
      >
        <DialogHeader>
          <div className="mb-2 flex size-10 items-center justify-center rounded-xl border bg-muted/50">
            <Upload className="size-5 text-muted-foreground" />
          </div>
          <DialogTitle>
            {task ? "Upload model version" : "Add a model"}
          </DialogTitle>
          <DialogDescription>
            {task ? (
              <>
                Add an externally trained LoRA adapter to{" "}
                <span className="font-medium text-foreground">{task.name}</span>
                .
              </>
            ) : (
              "Bring your own LoRA adapter. Create a task to keep its versions together."
            )}
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-5"
          onSubmit={(event) => {
            event.preventDefault();
            if (draft.success && !fileError) upload.mutate();
          }}
        >
          <fieldset
            className="space-y-5 disabled:opacity-70"
            disabled={upload.isPending}
          >
            <div className={task ? "" : "grid gap-4 sm:grid-cols-2"}>
              {!task && (
                <div className="space-y-2">
                  <Label htmlFor="upload-task">Model name</Label>
                  <Input
                    id="upload-task"
                    placeholder="e.g. support-triage"
                    value={taskName}
                    maxLength={256}
                    onChange={(event) => setTaskName(event.target.value)}
                    required
                  />
                </div>
              )}
              <div className="space-y-2">
                <Label htmlFor="upload-version">Version name</Label>
                <Input
                  id="upload-version"
                  placeholder="e.g. support-triage-v1"
                  value={name}
                  maxLength={200}
                  pattern={"[a-zA-Z0-9][a-zA-Z0-9._\\-]*"}
                  onChange={(event) => setName(event.target.value)}
                  required
                />
                <p className="text-xs text-muted-foreground">
                  A unique name for this model in your workspace.
                </p>
              </div>
            </div>
            <div className="space-y-2">
              <Label>Adapter files</Label>
              <input
                ref={picker}
                type="file"
                aria-label="Choose adapter files"
                accept=".json,.safetensors"
                multiple
                className="sr-only"
                onChange={(event) => {
                  void selectFiles(Array.from(event.target.files ?? []));
                  event.target.value = "";
                }}
              />
              <button
                type="button"
                disabled={upload.isPending}
                onClick={() => picker.current?.click()}
                onDragOver={(event) => {
                  event.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={(event) => {
                  event.preventDefault();
                  setDragging(false);
                  if (!upload.isPending)
                    void selectFiles(Array.from(event.dataTransfer.files));
                }}
                className={`flex w-full flex-col items-center rounded-lg border border-dashed px-4 py-6 text-center transition-colors hover:border-foreground/40 hover:bg-muted/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${dragging ? "border-primary bg-muted" : "border-border"}`}
              >
                {config && weights ? (
                  <FileCheck2 className="mb-2 size-6 text-[#6e7f31]" />
                ) : (
                  <Upload className="mb-2 size-6 text-muted-foreground" />
                )}
                <span className="text-sm font-medium">
                  {config && weights
                    ? "Adapter files ready"
                    : "Drop your adapter files here"}
                </span>
                <span className="mt-1 text-xs text-muted-foreground">
                  or click to browse · safetensors + JSON · up to{" "}
                  {MAX_ADAPTER_BYTES / 1024 ** 2} MiB · rank up to{" "}
                  {MAX_UPLOADED_ADAPTER_RANK}
                </span>
              </button>
              <div className="space-y-1.5">
                {files.map((file) => (
                  <div
                    key={file.name}
                    className="flex items-center gap-2 rounded-md border bg-muted/20 px-3 py-2 text-xs"
                  >
                    <Check className="size-3.5 shrink-0 text-[#6e7f31]" />
                    <span className="min-w-0 flex-1 truncate font-mono">
                      {file.name}
                    </span>
                    <span className="shrink-0 text-muted-foreground">
                      {file.size < 1024 * 1024
                        ? `${Math.ceil(file.size / 1024)} KB`
                        : `${(file.size / 1024 / 1024).toFixed(1)} MB`}
                    </span>
                    <button
                      type="button"
                      aria-label={`Remove ${file.name}`}
                      className="rounded p-1 hover:bg-muted"
                      onClick={() =>
                        setFiles((current) =>
                          current.filter((item) => item !== file),
                        )
                      }
                    >
                      <X className="size-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
            <div className="space-y-2">
              <Label>Base model</Label>
              <OptionCombobox
                label="Base model"
                value={baseModel}
                onValueChange={setBaseModel}
                options={(models.data?.data ?? []).map((model) =>
                  modelOption(model.id),
                )}
                renderOption={ModelOption}
                placeholder="Select the model you fine-tuned"
                className="w-full"
                disabled={
                  models.isPending || Boolean(models.error) || upload.isPending
                }
              />
              <p className="text-xs text-muted-foreground">
                Must match the base checkpoint used to train your adapter.
              </p>
              {models.error && (
                <p role="alert" className="text-xs text-destructive">
                  Could not load base models.{" "}
                  <button
                    type="button"
                    className="underline"
                    onClick={() => void models.refetch()}
                  >
                    Try again
                  </button>
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="upload-revision">Base checkpoint revision</Label>
              <Input
                id="upload-revision"
                className="font-mono text-xs"
                placeholder="40-character Hugging Face commit SHA"
                value={revision}
                onChange={(event) => setRevision(event.target.value)}
                pattern="[0-9a-f]{40}"
                required
              />
              <p className="text-xs text-muted-foreground">
                The exact revision your adapter was trained against.
              </p>
            </div>
          </fieldset>
          {(fileError || upload.error) && (
            <p role="alert" className="text-sm text-destructive">
              {fileError ?? upload.error?.message}
            </p>
          )}
          <DialogFooter className="flex flex-col-reverse justify-end gap-2 border-t pt-4 sm:flex-row">
            <Button
              type="button"
              variant="outline"
              disabled={upload.isPending}
              onClick={onClose}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={
                !draft.success ||
                Boolean(fileError) ||
                !canEdit ||
                upload.isPending
              }
            >
              {upload.isPending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Upload className="size-4" />
              )}
              {upload.isPending
                ? progress
                : task
                  ? "Upload version"
                  : "Create task & upload"}
            </Button>
          </DialogFooter>
          {upload.isPending && (
            <p
              role="status"
              className="text-center text-xs text-muted-foreground"
            >
              Keep this window open while your adapter uploads.
            </p>
          )}
        </form>
      </DialogContent>
    </Dialog>
  );
};
