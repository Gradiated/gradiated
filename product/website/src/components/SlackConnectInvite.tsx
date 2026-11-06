import { useState } from "react";
import { CheckCircle2 } from "lucide-react";
import { z } from "zod";
import type { EngineerOnboarding } from "../api/engineer-onboarding";
import { createSlackInvitation } from "../api/slack";
import {
  ndaReference,
  slackInvitationProblem,
  slackInvited,
} from "../onboarding";
import type { OnboardingAccount, OnboardingDraft } from "../onboarding";

const channelPattern = /^ext-[a-z0-9]+(?:-[a-z0-9]+)*-gradiated$/;

const proposedChannel = (company: string) => {
  const slug =
    company
      .normalize("NFKD")
      .replace(/[̀-ͯ]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 66)
      .replace(/-$/g, "") || "customer";

  return `ext-${slug}-gradiated`;
};

export const SlackConnectInvite = ({
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
  onInvited: () => Promise<void>;
}) => {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const recipient = (draft.slackEmail ?? account.email).trim().toLowerCase();
  const validRecipient = z.email().safeParse(recipient).success;
  const renaming = !server.slack && draft.slackChannelName !== null;
  const channel =
    server.slack?.channel_name ??
    draft.slackChannelName ??
    proposedChannel(account.company);
  const validChannel = channelPattern.test(channel) && channel.length <= 80;
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
        ndaDocumentId: ndaReference(server, draft),
      });
      await onInvited();
    } catch (cause) {
      const code =
        cause instanceof Error && "code" in cause
          ? String(cause.code)
          : undefined;
      const problem = slackInvitationProblem(code);
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
    <div className="gs-slack-invite">
      <h2>Work with us in Slack</h2>
      <label className="gs-field">
        <span>Slack invite email</span>
        <input
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
      </label>
      {sent ? (
        <p role="status">
          <CheckCircle2 size={16} /> Invite sent · #{channel}
        </p>
      ) : (
        <>
          {renaming && (
            <label className="gs-field">
              <span>Slack channel name</span>
              <input
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
                aria-describedby="slack-channel-hint"
              />
              <small id="slack-channel-hint">
                Use ext-your-team-gradiated with lowercase letters, numbers and
                hyphens.
              </small>
            </label>
          )}
          <p>
            We’ll {server.slack ? "use" : "create"} <strong>#{channel}</strong>{" "}
            and invite <strong>{recipient}</strong>.
          </p>
          <button
            type="button"
            className="gr-button"
            disabled={busy || !validRecipient || !validChannel}
            onClick={() => void send()}
          >
            {busy ? "Sending invite…" : "Send Slack invite"}
          </button>
        </>
      )}
      <p className="gs-note">
        {sent
          ? "Accept the invitation in Slack or your inbox. Your workspace may require admin approval. You can continue below."
          : "Slack is our preferred way to work."}
      </p>
      {error && (
        <p role="alert" className="gs-note">
          {error}
        </p>
      )}
    </div>
  );
};
