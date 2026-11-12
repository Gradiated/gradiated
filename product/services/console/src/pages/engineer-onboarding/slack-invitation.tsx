import { CheckCircle2 } from "lucide-react";
import { useState } from "react";
import { z } from "zod";

import {
  createSlackInvitation,
  type EngineerOnboarding,
} from "@/api/engineer-onboarding";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import {
  Field,
  FieldDescription,
  FieldError,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  SLACK_CHANNEL_PATTERN,
  proposedSlackChannel,
  slackInvitationProblem,
  slackInvited,
  type OnboardingAccount,
  type OnboardingDraft,
} from "@/lib/engineer-onboarding";

export const SlackInvitation = ({
  account,
  server,
  draft,
  patch,
  onInvited,
}: {
  account: OnboardingAccount;
  server: EngineerOnboarding;
  draft: OnboardingDraft;
  patch: (values: Partial<OnboardingDraft>) => void;
  onInvited: () => Promise<unknown>;
}) => {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const recipient = (draft.slackEmail ?? account.email).trim().toLowerCase();
  const validRecipient = z.email().safeParse(recipient).success;
  const renaming = !server.slack && draft.slackChannelName !== null;
  const channel =
    server.slack?.channel_name ??
    draft.slackChannelName ??
    proposedSlackChannel(account.company);
  const validChannel =
    SLACK_CHANNEL_PATTERN.test(channel) && channel.length <= 80;
  const sent =
    slackInvited(server) &&
    server.slack?.invited_email?.toLowerCase() === recipient;

  const send = async () => {
    if (busy || !validRecipient || !validChannel) return;

    setBusy(true);
    setError("");
    try {
      await createSlackInvitation(account.organizationId, {
        email: recipient,
        channelName: renaming ? channel : undefined,
      });
      await onInvited();
    } catch (cause) {
      const problem = slackInvitationProblem(
        cause instanceof ApiError ? cause.code : undefined,
      );
      if (problem?.renameChannel) patch({ slackChannelName: channel });

      setError(
        problem?.message ??
          (cause instanceof Error
            ? cause.message
            : "Could not send the Slack invitation. You can continue and try again later."),
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="flex flex-col gap-3 rounded-lg border p-4">
      <h2 className="font-semibold">Work with us in Slack</h2>
      <Field>
        <FieldLabel htmlFor="slack-email">Slack invite email</FieldLabel>
        <Input
          id="slack-email"
          type="email"
          maxLength={200}
          value={draft.slackEmail ?? account.email}
          disabled={busy}
          onChange={(event) => {
            setError("");
            patch({ slackEmail: event.target.value });
          }}
          autoComplete="email"
        />
      </Field>
      {sent ? (
        <p role="status" className="flex items-center gap-2 text-sm">
          <CheckCircle2 className="size-4 text-emerald-600" /> Invite sent · #
          {channel}
        </p>
      ) : (
        <>
          {renaming ? (
            <Field>
              <FieldLabel htmlFor="slack-channel">
                Slack channel name
              </FieldLabel>
              <Input
                id="slack-channel"
                type="text"
                maxLength={80}
                value={channel}
                disabled={busy}
                onChange={(event) => {
                  patch({ slackChannelName: event.target.value });
                  setError("");
                }}
                autoCapitalize="none"
                autoCorrect="off"
                spellCheck={false}
              />
              <FieldDescription>
                Use ext-your-team-gradiated with lowercase letters, numbers and
                hyphens.
              </FieldDescription>
            </Field>
          ) : null}
          <p className="text-sm">
            We’ll {server.slack ? "use" : "create"} <strong>#{channel}</strong>{" "}
            and invite <strong>{recipient}</strong>.
          </p>
          <Button
            type="button"
            variant="outline"
            className="self-start"
            disabled={busy || !validRecipient || !validChannel}
            onClick={() => void send()}
          >
            {busy ? "Sending invite…" : "Send Slack invite"}
          </Button>
        </>
      )}
      <p className="text-sm text-muted-foreground">
        {sent
          ? "Accept the invitation in Slack or your inbox. Your workspace may require admin approval. You can continue below."
          : "Slack is our preferred way to work."}
      </p>
      {error ? <FieldError>{error}</FieldError> : null}
    </section>
  );
};
