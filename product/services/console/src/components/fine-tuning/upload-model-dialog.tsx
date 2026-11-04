import { z } from "zod";
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import {
  ArrowUpRight,
  Check,
  FileCheck2,
  Loader2,
  TriangleAlert,
  Upload,
  X,
} from "lucide-react";
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
import { errorMessage } from "@/lib/errors";
import { slugifyTaskInput } from "@/lib/task-slug";

const AdapterMetadataSchema = z.object({
  base_model_name_or_path: z.string().min(1),
  revision: z.string().max(300).nullish(),
  r: z.number().int().positive().optional(),
  lora_alpha: z.number().positive().optional(),
  target_modules: z.array(z.string()).optional(),
});

const fileSize = (bytes: number) =>
  bytes < 1024 ** 2
    ? `${Math.ceil(bytes / 1024)} KB`
    : `${(bytes / 1024 ** 2).toFixed(1)} MB`;

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
  const [metadata, setMetadata] = useState<z.infer<
    typeof AdapterMetadataSchema
  > | null>(null);
  const [tensorDetails, setTensorDetails] = useState<{
    precision: string;
    layers: number;
  } | null>(null);
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
      setRevision("");
      setBaseModel("");
      setMetadata(null);
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

        setRevision(metadata.revision ?? "");

        const catalog = models.data ?? (await models.refetch()).data;
        if (!catalog) {
          setFileError("Could not load supported base models. Try again.");
          return;
        }
        const match = catalog.data.find(
          (model) =>
            model.id === metadata.base_model_name_or_path ||
            (catalogModel(model.id) as CatalogEntry | undefined)?.training
              ?.model === metadata.base_model_name_or_path ||
            model.properties?.hugging_face_id ===
              metadata.base_model_name_or_path,
        );
        if (!match) {
          setFileError(
            "The adapter config does not identify a supported base model. Export it with its original Hugging Face base model repository.",
          );
          return;
        }
        if (task && match.id !== task.base_model_id) {
          setFileError(
            "The adapter base model does not match this model's existing versions.",
          );
          return;
        }
        setBaseModel(match.id);
        setMetadata(metadata);
      } catch {
        setFileError(
          "The adapter config must contain valid JSON with a base model name.",
        );
        return;
      }
    }
    const weightsFile = incoming.find(
      (file) => file.name === "adapter_model.safetensors",
    );
    if (weightsFile) {
      setTensorDetails(null);
      try {
        const prefix = new DataView(
          await weightsFile.slice(0, 8).arrayBuffer(),
        );
        const headerBytes = Number(prefix.getBigUint64(0, true));
        if (
          headerBytes > 0 &&
          headerBytes <= 1024 * 1024 &&
          headerBytes + 8 <= weightsFile.size
        ) {
          const header = z
            .record(z.string(), z.unknown())
            .parse(
              JSON.parse(await weightsFile.slice(8, 8 + headerBytes).text()),
            );
          const tensors = Object.entries(header).filter(
            ([key]) => key !== "__metadata__",
          );
          const precisions = [
            ...new Set(
              tensors.map(
                ([, value]) =>
                  z.object({ dtype: z.string() }).parse(value).dtype,
              ),
            ),
          ];
          const layers = new Set(
            tensors
              .map(([key]) => /(?:^|\.)layers\.(\d+)\./.exec(key)?.[1])
              .filter((value) => value !== undefined),
          );
          setTensorDetails({
            precision: precisions
              .map((dtype) =>
                dtype === "F16" ? "FP16" : dtype === "F32" ? "FP32" : dtype,
              )
              .join(" / "),
            layers: layers.size,
          });
        }
      } catch {
        setTensorDetails(null);
      }
    }
    setFiles((current) => [
      ...current.filter(
        (file) => !incoming.some((next) => next.name === file.name),
      ),
      ...incoming,
    ]);
  };
  const draft = CreateModelUploadSchema.omit({
    base_model_revision: true,
  }).safeParse({
    task: task?.name ?? taskName.trim(),
    create_task: !task,
    name: name.trim(),
    base_model_id: baseModel,
    config_size: config?.size,
    weights_size: weights?.size,
  });

  const expectedRevision = (catalogModel(baseModel) as CatalogEntry | undefined)
    ?.training?.revision;
  const revisionIsImmutable = /^[0-9a-f]{40}$/.test(revision);
  const checkpointWarning = !revisionIsImmutable
    ? "Training checkpoint is unknown. Results may differ."
    : expectedRevision && revision !== expectedRevision
      ? "Trained on a different checkpoint. Results may differ."
      : null;

  const adapterDetails = [
    ["Rank", metadata?.r],
    ["Alpha", metadata?.lora_alpha],
    ["Precision", tensorDetails?.precision],
    ["Layers", tensorDetails?.layers],
    ["Size", weights && fileSize(weights.size)],
  ].filter((detail): detail is [string, string | number] => Boolean(detail[1]));
  const huggingFaceRepo = /^[\w.-]+\/[\w.-]+$/.test(
    metadata?.base_model_name_or_path ?? "",
  )
    ? metadata?.base_model_name_or_path
    : undefined;

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
      setProgress("Checking adapter compatibility…");
      return completeModelUpload(workspaceId, grant.id);
    },
    onSuccess: async (version) => {
      await client.invalidateQueries({ queryKey: trainingKey(workspaceId) });
      toast.success("Model version uploaded", {
        description:
          "Adapter compatibility checks passed. Your model version is saved.",
      });
      onClose();
      void navigate({ to: "/tasks/$taskId", params: { taskId: version.task } });
    },
    onError: (error) =>
      toast.error(errorMessage(error, "The model could not be uploaded.")),
  });

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !upload.isPending) onClose();
      }}
    >
      <DialogContent
        className="max-h-[90dvh] gap-4 overflow-y-auto p-5 pb-0 sm:max-w-xl sm:gap-5 sm:p-6"
        onInteractOutside={(event) => {
          if (upload.isPending) event.preventDefault();
        }}
      >
        <DialogHeader>
          <div className="mb-2 hidden size-10 items-center justify-center rounded-xl border bg-muted/50 sm:flex">
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
              "Bring your own LoRA adapter."
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
                    onChange={(event) =>
                      setTaskName(slugifyTaskInput(event.target.value))
                    }
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
                  onChange={(event) =>
                    setName(slugifyTaskInput(event.target.value))
                  }
                  required
                />
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
                className={`flex w-full rounded-lg border border-dashed px-4 transition-colors ${config && weights ? "items-center gap-3 py-3 text-left" : "flex-col items-center py-5 text-center sm:py-6"} hover:border-foreground/40 hover:bg-muted/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${dragging ? "border-primary bg-muted" : "border-border"}`}
              >
                {config && weights ? (
                  <>
                    <FileCheck2 className="size-5 shrink-0 text-[#6e7f31]" />
                    <span className="flex-1 text-sm font-medium">
                      Adapter files ready
                    </span>
                    <span className="text-xs text-muted-foreground">
                      Replace
                    </span>
                  </>
                ) : (
                  <>
                    <Upload className="mb-2 size-6 text-muted-foreground" />
                    <span className="text-sm font-medium">
                      Drop your adapter files here
                    </span>
                    <span className="mt-1 text-xs text-muted-foreground">
                      or click to browse · safetensors + JSON · up to{" "}
                      {MAX_ADAPTER_BYTES / 1024 ** 2} MiB · rank up to{" "}
                      {MAX_UPLOADED_ADAPTER_RANK}
                    </span>
                  </>
                )}
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
                      {fileSize(file.size)}
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
            {config && metadata && baseModel && (
              <div className="space-y-3 border-t pt-4">
                <dl className="grid grid-cols-3 gap-x-6 gap-y-3 text-sm sm:grid-cols-5">
                  <div className="col-span-3">
                    <dt className="text-xs text-muted-foreground">
                      Base model
                    </dt>
                    <dd className="mt-1">
                      <ModelOption {...modelOption(baseModel)} />
                    </dd>
                  </div>
                  <div className="col-span-3 sm:col-span-2">
                    <dt className="text-xs text-muted-foreground">
                      Checkpoint
                    </dt>
                    <dd className="mt-1">
                      {revision && huggingFaceRepo ? (
                        <a
                          href={`https://huggingface.co/${huggingFaceRepo}/tree/${revision}`}
                          target="_blank"
                          rel="noreferrer"
                          title={revision}
                          className="inline-flex items-center gap-1 font-mono text-xs underline decoration-border underline-offset-4 hover:decoration-foreground"
                        >
                          {revisionIsImmutable
                            ? revision.slice(0, 12)
                            : revision}
                          <ArrowUpRight aria-hidden className="size-3" />
                        </a>
                      ) : (
                        <span
                          className={
                            revision
                              ? "font-mono text-xs"
                              : "text-muted-foreground"
                          }
                        >
                          {revision || "Not recorded"}
                        </span>
                      )}
                    </dd>
                  </div>
                  {adapterDetails.map(([label, value]) => (
                    <div key={label}>
                      <dt className="text-xs text-muted-foreground">{label}</dt>
                      <dd className="mt-1 tabular-nums">{value}</dd>
                    </div>
                  ))}
                  {metadata.target_modules && (
                    <div className="col-span-3 sm:col-span-5">
                      <dt className="text-xs text-muted-foreground">
                        Target modules
                      </dt>
                      <dd className="mt-1.5 flex flex-wrap gap-1">
                        {metadata.target_modules.map((module) => (
                          <code
                            key={module}
                            className="rounded bg-muted px-1.5 py-0.5 text-xs"
                          >
                            {module}
                          </code>
                        ))}
                      </dd>
                    </div>
                  )}
                </dl>
                {checkpointWarning && (
                  <p
                    role="status"
                    className="flex items-start gap-1.5 text-xs text-amber-700 dark:text-amber-400"
                  >
                    <TriangleAlert
                      aria-hidden
                      className="mt-px size-3.5 shrink-0"
                    />
                    {checkpointWarning}
                  </p>
                )}
              </div>
            )}
            {models.error && (
              <p role="alert" className="text-xs text-destructive">
                Could not load supported models.{" "}
                <button
                  type="button"
                  className="underline"
                  onClick={() => void models.refetch()}
                >
                  Try again
                </button>
              </p>
            )}
          </fieldset>
          {fileError && (
            <p role="alert" className="text-sm text-destructive">
              {fileError}
            </p>
          )}
          {upload.isPending && (
            <p
              role="status"
              className="text-center text-xs text-muted-foreground"
            >
              Keep this window open while your adapter uploads.
            </p>
          )}
          <DialogFooter className="sticky bottom-0 z-10 -mx-5 flex justify-end gap-2 border-t bg-card px-5 py-4 sm:static sm:mx-0 sm:bg-transparent sm:px-0 sm:pb-0">
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
              className="flex-1 sm:flex-none"
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
        </form>
      </DialogContent>
    </Dialog>
  );
};
