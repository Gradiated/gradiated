import { useNavigate } from "@tanstack/react-router";
import { LoaderCircle, Upload } from "lucide-react";
import { useId, useState, type FormEvent } from "react";

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
import { useImportFile, type ImportStage } from "@/hooks/use-grad";
import { errorMessage } from "@/lib/errors";
import { formatBytes } from "@/lib/grad/format";
import {
  DATASET_NAME_PATTERN,
  IMPORT_FILE_TYPES,
  MAX_IMPORT_BYTES,
  datasetNameFromFile,
} from "@/lib/grad/upload";

const STAGE_LABEL: Record<ImportStage, string> = {
  hashing: "Checking file…",
  uploading: "Uploading…",
  importing: "Starting import…",
};

export const ImportFileDialog = ({
  dataset,
  open,
  onOpenChange,
}: {
  dataset?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) => {
  const navigate = useNavigate();
  const fileId = useId();
  const nameId = useId();
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState(dataset ?? "");
  const [stage, setStage] = useState<ImportStage | null>(null);
  const importFile = useImportFile();
  const tooLarge = file !== null && file.size > MAX_IMPORT_BYTES;
  const nameValid = DATASET_NAME_PATTERN.test(name);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!file || tooLarge || !nameValid) return;

    importFile.mutate(
      { dataset: name, file, onStage: setStage },
      {
        onSuccess: () => {
          onOpenChange(false);
          void navigate({
            to: "/training/datasets/$datasetName",
            params: { datasetName: name },
            search: { tab: "imports" },
          });
        },
        onSettled: () => setStage(null),
      },
    );
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => !importFile.isPending && onOpenChange(next)}
    >
      <DialogContent>
        <form className="space-y-5" onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Import a file</DialogTitle>
            <DialogDescription>
              JSONL, JSON or Parquet: chat transcripts, grad trajectories or
              traces exported from Langfuse, LangSmith, Braintrust, PostHog or
              OpenTelemetry. The format is detected on import.
            </DialogDescription>
          </DialogHeader>
          <Field data-invalid={tooLarge}>
            <FieldLabel htmlFor={fileId}>File</FieldLabel>
            <Input
              id={fileId}
              type="file"
              accept={IMPORT_FILE_TYPES}
              onChange={(event) => {
                const next = event.target.files?.[0] ?? null;
                setFile(next);
                if (next && !dataset && !name)
                  setName(datasetNameFromFile(next.name));
              }}
            />
            {tooLarge ? (
              <FieldError>
                Files can be up to {formatBytes(MAX_IMPORT_BYTES)}.
              </FieldError>
            ) : file ? (
              <FieldDescription>{formatBytes(file.size)}</FieldDescription>
            ) : null}
          </Field>
          <Field data-invalid={name !== "" && !nameValid}>
            <FieldLabel htmlFor={nameId}>Dataset</FieldLabel>
            <Input
              id={nameId}
              value={name}
              disabled={Boolean(dataset)}
              autoComplete="off"
              data-1p-ignore="true"
              maxLength={64}
              placeholder="support-traces"
              onChange={(event) => setName(event.target.value)}
            />
            {name !== "" && !nameValid ? (
              <FieldError>
                Use lowercase letters, digits, '.', '_' and '-', starting with a
                letter or digit.
              </FieldError>
            ) : (
              <FieldDescription>
                {dataset
                  ? "The records become the dataset's next version."
                  : "A new dataset is created, or the records are added to an existing one."}
              </FieldDescription>
            )}
          </Field>
          {importFile.error ? (
            <FieldError>
              {errorMessage(importFile.error, "The import failed.")}
            </FieldError>
          ) : null}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={importFile.isPending}
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={!file || tooLarge || !nameValid || importFile.isPending}
            >
              {importFile.isPending ? (
                <LoaderCircle className="animate-spin" />
              ) : (
                <Upload />
              )}
              {stage ? STAGE_LABEL[stage] : "Import"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};
