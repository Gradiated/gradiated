import { useState } from "react";

import {
  Field,
  FieldDescription,
  FieldError,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  organizationSlugError,
  privateModelName,
  slugFromName,
} from "@/lib/model-name";

/** A slug that follows a slugified organization name until the owner edits it. */
export const useFollowingSlug = (name: string) => {
  const [edited, setEdited] = useState<string | null>(null);
  const input = edited ?? slugFromName(name);
  const slug = input.trim().toLowerCase();
  const error = organizationSlugError(slug);

  return {
    input,
    slug,
    error,
    // An untouched, empty form shows no error.
    shownError: edited !== null || name.trim() !== "" ? error : null,
    edit: setEdited,
  };
};

export const OrganizationSlugField = ({
  id,
  slug,
  disabled,
}: {
  id: string;
  slug: ReturnType<typeof useFollowingSlug>;
  disabled: boolean;
}) => (
  <Field data-invalid={slug.shownError !== null}>
    <FieldLabel htmlFor={id}>Organization slug</FieldLabel>
    <Input
      id={id}
      name="organizationSlug"
      value={slug.input}
      onChange={(event) => slug.edit(event.target.value)}
      maxLength={39}
      required
      spellCheck={false}
      autoComplete="off"
      data-1p-ignore="true"
      aria-invalid={slug.shownError !== null}
      disabled={disabled}
    />
    <FieldDescription>
      Prefixes your model names, as in{" "}
      <code className="font-mono text-xs">
        {privateModelName(slug.slug || "acme", "support-triage")}
      </code>
      . It can&apos;t change once your organization has a model.
    </FieldDescription>
    {slug.shownError ? <FieldError>{slug.shownError}</FieldError> : null}
  </Field>
);
