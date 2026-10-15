import NiceModal, {
  useModal,
  type NiceModalHocProps,
} from "@ebay/nice-modal-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { LoaderCircle } from "lucide-react";
import { useId, useState, type FC, type FormEvent } from "react";
import { toast } from "sonner";

import { createInvitations, type OrganizationRole } from "@/api/queries";
import { OptionSelect } from "@/components/option-select";
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
import { Textarea } from "@/components/ui/textarea";
import { parseEmails } from "@/lib/emails";
import { errorMessage } from "@/lib/errors";
import { queryKeys } from "@/lib/query-keys";
import { ROLE_OPTIONS } from "@/lib/roles";

const MAX_INVITATIONS = 20;
interface InviteMembersDialogProps {
  organizationId: string;
  organizationName: string;
}

export const InviteMembersDialog: FC<
  InviteMembersDialogProps & NiceModalHocProps
> = NiceModal.create<InviteMembersDialogProps>(
  ({ organizationId, organizationName }) => {
    const modal = useModal();
    const client = useQueryClient();
    const emailsId = useId();
    const [value, setValue] = useState("");
    const [role, setRole] = useState<OrganizationRole>("admin");
    const { emails, invalid } = parseEmails(value);
    const problem = invalid.length
      ? `Check ${invalid.join(", ")}.`
      : emails.length > MAX_INVITATIONS
        ? `Invite up to ${MAX_INVITATIONS} people at a time.`
        : null;

    const close = () => {
      modal.resolve();
      void modal.hide();
    };

    const send = useMutation({
      mutationFn: () => createInvitations(organizationId, { emails, role }),
      onSettled: () =>
        client.invalidateQueries({
          queryKey: queryKeys.invitations(organizationId),
        }),
      onSuccess: () => {
        toast.success(
          emails.length === 1
            ? `Invitation sent to ${emails[0]}.`
            : `${emails.length} invitations sent.`,
        );
        close();
      },
    });

    const submit = (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (emails.length && !problem && !send.isPending) send.mutate();
    };

    return (
      <Dialog
        open={modal.visible}
        onOpenChange={(open) => {
          if (!open) close();
        }}
      >
        <DialogContent onCloseAutoFocus={() => modal.remove()}>
          <form className="space-y-5" onSubmit={submit}>
            <DialogHeader>
              <DialogTitle>Invite members</DialogTitle>
              <DialogDescription>
                They'll get an email invitation to join {organizationName}.
              </DialogDescription>
            </DialogHeader>
            <Field data-invalid={Boolean(problem)}>
              <FieldLabel htmlFor={emailsId}>Email addresses</FieldLabel>
              <Textarea
                id={emailsId}
                value={value}
                onChange={(event) => setValue(event.target.value)}
                placeholder="morgan@acme.com, casey@acme.com"
                autoFocus
                autoComplete="off"
                data-1p-ignore="true"
                aria-invalid={Boolean(problem)}
                className="min-h-24"
              />
              {problem ? (
                <FieldError>{problem}</FieldError>
              ) : (
                <FieldDescription>
                  Separate addresses with commas, spaces or new lines.
                </FieldDescription>
              )}
            </Field>
            <Field>
              <FieldLabel>Role</FieldLabel>
              <OptionSelect
                value={role}
                options={ROLE_OPTIONS}
                onValueChange={setRole}
                label="Role"
                className="w-full"
              />
              <FieldDescription>
                Admins can invite people, manage members and billing.
              </FieldDescription>
            </Field>
            {send.error ? (
              <FieldError>
                {errorMessage(send.error, "The invitations could not be sent.")}
              </FieldError>
            ) : null}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={close}>
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={!emails.length || Boolean(problem) || send.isPending}
              >
                {send.isPending ? (
                  <LoaderCircle className="size-4 animate-spin" />
                ) : null}
                {emails.length > 1
                  ? `Send ${emails.length} invitations`
                  : "Send invitation"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    );
  },
);
