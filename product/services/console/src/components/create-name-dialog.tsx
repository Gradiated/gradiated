import NiceModal, { useModal } from "@ebay/nice-modal-react";
import { zodResolver } from "@hookform/resolvers/zod";
import { LoaderCircle } from "lucide-react";
import { useId } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

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

const MAX_NAME_LENGTH = 200;

interface CreateNameDialogProps {
  title: string;
  label: string;
  placeholder: string;
  submitLabel: string;
  emptyMessage: string;
  submit: (name: string) => Promise<void>;
}

export const CreateNameDialog = NiceModal.create<CreateNameDialogProps>(
  ({ title, label, placeholder, submitLabel, emptyMessage, submit }) => {
    const modal = useModal();
    const inputId = useId();
    const form = useForm({
      resolver: zodResolver(
        z.object({
          name: z.string().trim().min(1, emptyMessage).max(MAX_NAME_LENGTH),
        }),
      ),
      defaultValues: { name: "" },
    });

    const close = () => {
      modal.resolve();
      void modal.hide();
    };

    const create = async ({ name }: { name: string }) => {
      try {
        await submit(name);
      } catch (error) {
        form.setError("root", {
          message: errorMessage(error, "The request failed."),
        });
        return;
      }

      close();
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
          <form className="space-y-5" onSubmit={form.handleSubmit(create)}>
            <DialogHeader>
              <DialogTitle>{title}</DialogTitle>
            </DialogHeader>
            <Field data-invalid={Boolean(form.formState.errors.name)}>
              <FieldLabel htmlFor={inputId}>{label}</FieldLabel>
              <Input
                id={inputId}
                autoFocus
                maxLength={MAX_NAME_LENGTH}
                placeholder={placeholder}
                {...form.register("name")}
              />
              {form.formState.errors.name ? (
                <FieldError errors={[form.formState.errors.name]} />
              ) : null}
            </Field>
            {form.formState.errors.root?.message ? (
              <FieldError>{form.formState.errors.root.message}</FieldError>
            ) : null}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={close}>
                Cancel
              </Button>
              <Button type="submit" disabled={form.formState.isSubmitting}>
                {form.formState.isSubmitting ? (
                  <LoaderCircle className="size-4 animate-spin" />
                ) : null}
                {submitLabel}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    );
  },
);
