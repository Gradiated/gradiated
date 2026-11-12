import { useMutation } from "@tanstack/react-query";
import { useId, useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Field,
  FieldDescription,
  FieldError,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { errorMessage } from "@/lib/errors";
import { organizationSlugError, privateModelName } from "@/lib/model-name";

export const SlugSetting = ({
  savedSlug,
  canEdit,
  onSave,
}: {
  savedSlug: string;
  canEdit: boolean;
  onSave: (slug: string) => Promise<void>;
}) => {
  const id = useId();
  const descriptionId = useId();
  const [slug, setSlug] = useState(savedSlug);
  const save = useMutation({
    mutationFn: onSave,
    onSuccess: () => toast.success("Organization slug changed."),
  });

  const value = slug.trim().toLowerCase();
  const invalid = value === savedSlug ? null : organizationSlugError(value);
  const error =
    invalid ??
    (save.isError && save.variables === value
      ? errorMessage(save.error, "The slug could not be saved.")
      : null);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (canEdit && !invalid && value !== savedSlug && !save.isPending)
      save.mutate(value);
  };

  return (
    <form
      className="max-w-xl space-y-5 rounded-xl border bg-card p-6"
      onSubmit={submit}
    >
      <Field data-invalid={error !== null}>
        <FieldLabel htmlFor={id}>Organization slug</FieldLabel>
        <Input
          id={id}
          name="organizationSlug"
          value={slug}
          onChange={(event) => setSlug(event.target.value)}
          maxLength={39}
          required
          spellCheck={false}
          autoComplete="off"
          data-1p-ignore="true"
          aria-invalid={error !== null}
          aria-describedby={descriptionId}
          disabled={!canEdit || save.isPending}
        />
        <FieldDescription id={descriptionId}>
          Prefixes your model names, as in{" "}
          <code className="font-mono text-xs">
            {privateModelName(
              organizationSlugError(value) ? savedSlug : value,
              "support-triage",
            )}
          </code>
          . Previous slugs keep working.
        </FieldDescription>
        {error ? <FieldError>{error}</FieldError> : null}
      </Field>
      <Button
        type="submit"
        disabled={
          !canEdit || save.isPending || invalid !== null || value === savedSlug
        }
      >
        {save.isPending ? "Saving…" : "Save changes"}
      </Button>
    </form>
  );
};
