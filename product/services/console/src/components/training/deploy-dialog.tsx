import { Link } from "@tanstack/react-router";
import { CircleCheck, Clock, LoaderCircle } from "lucide-react";
import { useId, useState, type FormEvent } from "react";

import { DeployUnavailableError } from "@/api/grad";
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
import { usePublishArtifact } from "@/hooks/use-grad";
import { errorMessage } from "@/lib/errors";
import type { Artifact } from "@/lib/grad/types";

export const DeployDialog = ({
  artifact,
  open,
  onOpenChange,
}: {
  artifact: Pick<Artifact, "id" | "name" | "version">;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) => {
  const modelId = useId();
  const versionId = useId();
  const [model, setModel] = useState(artifact.name);
  const [version, setVersion] = useState(artifact.version);
  const publish = usePublishArtifact();
  const unavailable = publish.error instanceof DeployUnavailableError;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    publish.mutate({
      model: model.trim(),
      artifactId: artifact.id,
      version: version.trim(),
    });
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) publish.reset();
        onOpenChange(next);
      }}
    >
      <DialogContent>
        {publish.isSuccess ? (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <CircleCheck className="size-5 text-[#6e7f31]" />
                Published
              </DialogTitle>
              <DialogDescription>
                {model} / {publish.data.name} is a new version of the model. It
                can serve requests once it qualifies on serving capacity.
                Promote it on the model page to send it production traffic.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                Close
              </Button>
              <Button asChild>
                <Link to="/tasks/$taskId" params={{ taskId: model }}>
                  Open model
                </Link>
              </Button>
            </DialogFooter>
          </>
        ) : unavailable ? (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Clock className="size-5 text-muted-foreground" />
                Deploy is not available yet
              </DialogTitle>
              <DialogDescription>
                Publishing trained artifacts as model versions is still rolling
                out. Download the artifact to serve it with vLLM or SGLang in
                the meantime.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button onClick={() => onOpenChange(false)}>Close</Button>
            </DialogFooter>
          </>
        ) : (
          <form className="space-y-5" onSubmit={submit}>
            <DialogHeader>
              <DialogTitle>Deploy {artifact.name}</DialogTitle>
              <DialogDescription>
                Publishes the artifact as a version of a model. The model is
                created if it does not exist; promoting it is a separate step.
              </DialogDescription>
            </DialogHeader>
            <Field>
              <FieldLabel htmlFor={modelId}>Model</FieldLabel>
              <Input
                id={modelId}
                value={model}
                autoComplete="off"
                data-1p-ignore="true"
                required
                maxLength={64}
                onChange={(event) => setModel(event.target.value)}
              />
              <FieldDescription>
                Callers use the model name in requests.
              </FieldDescription>
            </Field>
            <Field>
              <FieldLabel htmlFor={versionId}>Version</FieldLabel>
              <Input
                id={versionId}
                value={version}
                autoComplete="off"
                data-1p-ignore="true"
                required
                maxLength={64}
                onChange={(event) => setVersion(event.target.value)}
              />
            </Field>
            {publish.error ? (
              <FieldError>
                {errorMessage(publish.error, "Could not publish the artifact.")}
              </FieldError>
            ) : null}
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={publish.isPending || !model.trim() || !version.trim()}
              >
                {publish.isPending ? (
                  <LoaderCircle className="animate-spin" />
                ) : null}
                Publish version
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
};
