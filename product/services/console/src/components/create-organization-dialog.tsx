import NiceModal, { useModal } from "@ebay/nice-modal-react";
import { zodResolver } from "@hookform/resolvers/zod";
import { LoaderCircle } from "lucide-react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { createOrganization } from "@/api/queries";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";

const CreateOrganizationSchema = z.object({
  name: z.string().trim().min(1, "Enter an organization name.").max(200),
});

type CreateOrganizationValues = z.infer<typeof CreateOrganizationSchema>;

interface CreateOrganizationDialogProps {
  onCreated: (organizationId: string, defaultWorkspaceId: string) => void;
}

export const CreateOrganizationDialog =
  NiceModal.create<CreateOrganizationDialogProps>(({ onCreated }) => {
    const modal = useModal();
    const form = useForm<CreateOrganizationValues>({
      resolver: zodResolver(CreateOrganizationSchema),
      defaultValues: { name: "" },
    });

    const close = async () => {
      modal.resolve(null);
      await modal.hide();
      modal.remove();
    };

    const submit = async (values: CreateOrganizationValues) => {
      try {
        const organization = await createOrganization(values);
        onCreated(organization.id, organization.default_workspace_id);
        modal.resolve(organization);
        await modal.hide();
        modal.remove();
      } catch (error) {
        form.setError("root", {
          message:
            error instanceof Error
              ? error.message
              : "The organization could not be created.",
        });
      }
    };

    return (
      <Dialog
        open={modal.visible}
        onOpenChange={(open) => {
          if (!open) void close();
        }}
      >
        <DialogContent>
          <form className="space-y-5" onSubmit={form.handleSubmit(submit)}>
            <DialogHeader>
              <DialogTitle>Create an organization</DialogTitle>
              <DialogDescription>
                Create an organization for your team. We’ll also create a
                default workspace for you.
              </DialogDescription>
            </DialogHeader>
            <Field data-invalid={Boolean(form.formState.errors.name)}>
              <FieldLabel htmlFor="new-organization-name">
                Organization name
              </FieldLabel>
              <Input
                id="new-organization-name"
                autoFocus
                maxLength={200}
                placeholder="Acme Inc"
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
              <Button
                type="button"
                variant="outline"
                onClick={() => void close()}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={form.formState.isSubmitting}>
                {form.formState.isSubmitting ? (
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
