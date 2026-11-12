import { CheckCircle2 } from "lucide-react";
import { useEffect, useState } from "react";
import { z } from "zod";

import {
  createSlackInvitation,
  type EngineerOnboarding,
} from "@/api/engineer-onboarding";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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

const RESEND_AFTER_MS = 30_000;

const useResendCountdown = (invitedAt: string | null | undefined) => {
  const [now, setNow] = useState(() => Date.now());
  const availableAt = invitedAt ? Date.parse(invitedAt) + RESEND_AFTER_MS : 0;
  const seconds = Math.max(0, Math.ceil((availableAt - now) / 1000));

  useEffect(() => {
    if (seconds === 0) return;

    const timer = window.setTimeout(() => setNow(Date.now()), 1000);
    return () => window.clearTimeout(timer);
  }, [seconds, now]);

  return seconds;
};

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
  const resendIn = useResendCountdown(server.slack?.invited_at);

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

  if (draft.channel === "email")
    return (
      <div className="flex flex-col gap-4">
        <p className="text-sm leading-6 text-muted-foreground">
          We’ll email{" "}
          <strong className="font-medium text-foreground">
            {account.email}
          </strong>
          . If you can use Slack later, tell your researcher and we’ll open a
          channel.
        </p>
        <EmailFallback draft={draft} patch={patch} />
      </div>
    );

  return (
    <div className="flex flex-col gap-4">
      {sent ? (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p role="status" className="flex items-center gap-2 text-sm">
              <CheckCircle2 className="size-4 text-emerald-600" /> Invite sent
              to {recipient} ·{" "}
              <strong className="font-medium">#{channel}</strong>
            </p>
            <Button
              type="button"
              variant="link"
              className="h-auto p-0"
              disabled={busy || resendIn > 0}
              onClick={() => void send()}
            >
              {busy
                ? "Resending…"
                : resendIn > 0
                  ? `Resend in ${resendIn}s`
                  : "Resend invite"}
            </Button>
          </div>
          <p className="text-sm text-muted-foreground">
            Accept the invitation in Slack or your inbox. Your workspace may
            require admin approval.
          </p>
        </div>
      ) : (
        <p className="text-sm leading-6 text-muted-foreground">
          We’ll {server.slack ? "use" : "open"}{" "}
          <strong className="font-medium text-foreground">#{channel}</strong> in
          Slack Connect and invite you.
        </p>
      )}
      {renaming ? (
        <Field>
          <FieldLabel htmlFor="slack-channel">Slack channel name</FieldLabel>
          <Input
            id="slack-channel"
            type="text"
            maxLength={80}
            value={channel}
            disabled={busy}
            aria-invalid={Boolean(error) || !validChannel}
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
      <div className="flex flex-wrap items-end gap-2">
        <Field className="min-w-60 flex-1">
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
        {sent ? null : (
          <Button
            type="button"
            variant="secondary"
            disabled={busy || !validRecipient || !validChannel}
            onClick={() => void send()}
          >
            {busy ? "Sending invite…" : "Send invite"}
          </Button>
        )}
      </div>
      {error ? <FieldError>{error}</FieldError> : null}
      <EmailFallback draft={draft} patch={patch} />
    </div>
  );
};

const EmailFallback = ({
  draft,
  patch,
}: {
  draft: OnboardingDraft;
  patch: (values: Partial<OnboardingDraft>) => void;
}) => (
  <Field orientation="horizontal">
    <Checkbox
      id="email-fallback"
      checked={draft.channel === "email"}
      onCheckedChange={(checked) =>
        patch({ channel: checked === true ? "email" : "slack" })
      }
    />
    <FieldLabel htmlFor="email-fallback" className="font-normal">
      Our team can’t use Slack, so use email instead.
    </FieldLabel>
  </Field>
);
