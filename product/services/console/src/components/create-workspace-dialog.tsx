import NiceModal, { useModal } from "@ebay/nice-modal-react";
import { zodResolver } from "@hookform/resolvers/zod";
import { LoaderCircle } from "lucide-react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { createWorkspace, type Workspace } from "@/api/queries";
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

const CreateWorkspaceSchema = z.object({
  name: z.string().trim().min(1, "Enter a workspace name.").max(200),
});

type CreateWorkspaceValues = z.infer<typeof CreateWorkspaceSchema>;

interface CreateWorkspaceDialogProps {
  organizationId: string;
  onCreated: (workspace: Workspace) => void;
}

export const CreateWorkspaceDialog =
  NiceModal.create<CreateWorkspaceDialogProps>(
    ({ organizationId, onCreated }) => {
      const modal = useModal();
      const form = useForm<CreateWorkspaceValues>({
        resolver: zodResolver(CreateWorkspaceSchema),
        defaultValues: { name: "" },
      });

      const close = async () => {
        modal.resolve(null);
        await modal.hide();
        modal.remove();
      };

      const submit = async (values: CreateWorkspaceValues) => {
        try {
          const workspace = await createWorkspace(organizationId, values);
          onCreated(workspace);
          modal.resolve(workspace);
          await modal.hide();
          modal.remove();
        } catch (error) {
          form.setError("root", {
            message:
              error instanceof Error
                ? error.message
                : "The workspace could not be created.",
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
                <DialogTitle>Create a workspace</DialogTitle>
                <DialogDescription>
                  Use workspaces to organize API keys and usage.
                </DialogDescription>
              </DialogHeader>
              <Field data-invalid={Boolean(form.formState.errors.name)}>
                <FieldLabel htmlFor="new-workspace-name">
                  Workspace name
                </FieldLabel>
                <Input
                  id="new-workspace-name"
                  autoFocus
                  maxLength={200}
                  placeholder="Production"
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
                  Create workspace
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      );
    },
  );
