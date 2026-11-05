import { useState } from "react";
import { CheckCircle2 } from "lucide-react";
import { z } from "zod";
import { createSlackInvitation } from "../api/slack";
import type { OnboardingDraft } from "../onboarding";

export const SlackConnectInvite = ({
  draft,
  organizationId,
  demo,
  onInvited,
}: {
  draft: OnboardingDraft;
  organizationId: string;
  demo: boolean;
  onInvited: (values: Partial<OnboardingDraft>) => void;
}) => {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const recipient = (draft.slackEmail ?? draft.email).trim().toLowerCase();
  const validRecipient = z.email().safeParse(recipient).success;
  const slug =
    draft.company
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 66)
      .replace(/-$/g, "") || "customer";
  const channel =
    draft.slackStatus === "not_sent" ? `ext-${slug}-gradiated` : draft.slack;

  const send = async () => {
    if (busy || !validRecipient) return;
    setBusy(true);
    setError("");
    try {
      if (demo) {
        onInvited({
          slack: channel,
          slackEmail: recipient,
          slackStatus: "invited",
        });
        return;
      }
      if (!draft.ndaDocumentId)
        throw new Error("Complete the mutual NDA first.");

      const result = await createSlackInvitation(
        organizationId,
        draft.ndaDocumentId,
        recipient,
      );
      onInvited({
        slack: result.channel_name,
        slackEmail: result.email,
        slackStatus: result.status,
      });
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Could not send the Slack invitation. You can continue and try again later.",
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
          value={draft.slackEmail ?? draft.email}
          disabled={busy}
          onChange={(event) => {
            setError("");
            onInvited({
              slackEmail: event.target.value,
              slackStatus: "not_sent",
            });
          }}
          autoComplete="email"
        />
      </label>
      {draft.slackStatus === "not_sent" ? (
        <>
          <p>
            We’ll create <strong>#{channel}</strong> and invite{" "}
            <strong>{recipient}</strong>.
          </p>
          <button
            type="button"
            className="gr-button"
            disabled={busy || !validRecipient}
            onClick={() => void send()}
          >
            {busy ? "Sending invite…" : "Send Slack invite"}
          </button>
        </>
      ) : (
        <p role="status">
          <CheckCircle2 size={16} />{" "}
          {demo
            ? "Preview: invite sent"
            : draft.slackStatus === "joined"
              ? "Already connected"
              : "Invite sent"}{" "}
          · #{channel}
        </p>
      )}
      <p className="gs-note">
        {draft.slackStatus === "not_sent"
          ? "Slack is our preferred way to work."
          : "Accept the invitation in Slack or your inbox. Your workspace may require admin approval. You can continue below."}
      </p>
      {demo && (
        <p className="gs-note">
          Preview only · no channel or invitation is created.
        </p>
      )}
      {error && (
        <p role="alert" className="gs-note">
          {error}
        </p>
      )}
    </div>
  );
};
