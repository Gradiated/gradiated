import NiceModal, {
  useModal,
  type NiceModalHocProps,
} from "@ebay/nice-modal-react";
import { LoaderCircle } from "lucide-react";
import { useState, type FC, type FormEvent } from "react";

import {
  OrganizationSlugField,
  useFollowingSlug,
} from "@/components/organization-slug-field";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { errorMessage } from "@/lib/errors";

interface CreateOrganizationDialogProps {
  title: string;
  submit: (organization: { name: string; slug: string }) => Promise<void>;
}

export const CreateOrganizationDialog: FC<
  CreateOrganizationDialogProps & NiceModalHocProps
> = NiceModal.create<CreateOrganizationDialogProps>(({ title, submit }) => {
  const modal = useModal();
  const [name, setName] = useState("");
  const slug = useFollowingSlug(name);
  const [pending, setPending] = useState(false);
  const [nameError, setNameError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const close = () => {
    modal.resolve();
    void modal.hide();
  };

  const create = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setNameError(name.trim() ? null : "Enter an organization name.");
    if (!name.trim() || slug.error || pending) return;

    setPending(true);
    setError(null);
    try {
      await submit({ name: name.trim(), slug: slug.slug });
      close();
    } catch (failure) {
      setError(errorMessage(failure, "The request failed."));
    } finally {
      setPending(false);
    }
  };

  return (
    <Dialog
      open={modal.visible}
      onOpenChange={(open) => {
        if (!open) close();
      }}
    >
      <DialogContent
        aria-describedby={undefined}
        onCloseAutoFocus={() => modal.remove()}
      >
        <form className="space-y-5" onSubmit={(event) => void create(event)}>
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
          </DialogHeader>
          <Field data-invalid={nameError !== null}>
            <FieldLabel htmlFor="new-organization-name">
              Organization name
            </FieldLabel>
            <Input
              id="new-organization-name"
              name="scopeLabel"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Acme Inc"
              maxLength={200}
              autoFocus
              autoComplete="off"
              data-1p-ignore="true"
              disabled={pending}
            />
            {nameError ? <FieldError>{nameError}</FieldError> : null}
          </Field>
          <OrganizationSlugField
            id="new-organization-slug"
            slug={slug}
            disabled={pending}
          />
          {error ? <FieldError>{error}</FieldError> : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={close}>
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={(name.trim() !== "" && slug.error !== null) || pending}
            >
              {pending ? (
                <LoaderCircle className="size-4 animate-spin" />
              ) : null}
              Create organization
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
});
