import { useEffect, useRef, useState } from "react";
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
  const [customChannel, setCustomChannel] = useState<string | null>(null);
  const [livePreview, setLivePreview] = useState(false);
  const [checkingPreview, setCheckingPreview] = useState(
    import.meta.env.DEV && demo,
  );
  const callbacks = useRef({ onInvited, draft });
  callbacks.current = { onInvited, draft };

  useEffect(() => {
    if (!import.meta.env.DEV || !demo) return;

    let cancelled = false;
    void fetch("/__slack-preview/")
      .then(async (response) => (response.ok ? response.json() : null))
      .then((configuration) => {
        if (cancelled) return;

        const enabled = configuration?.enabled === true;
        setLivePreview(enabled);
        if (enabled && callbacks.current.draft.slackDeliveryMode !== "live")
          callbacks.current.onInvited({ slackStatus: "not_sent" });
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setCheckingPreview(false);
      });

    return () => {
      cancelled = true;
    };
  }, [demo]);
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
    draft.slackStatus === "not_sent"
      ? (customChannel ?? `ext-${slug}-gradiated`)
      : draft.slack;
  const validChannel =
    /^ext-[a-z0-9]+(?:-[a-z0-9]+)*-gradiated$/.test(channel) &&
    channel.length <= 80;

  const send = async () => {
    if (busy || checkingPreview || !validRecipient || !validChannel) return;
    setBusy(true);
    setError("");
    try {
      if (demo && !livePreview) {
        onInvited({
          slack: channel,
          slackEmail: recipient,
          slackStatus: "invited",
          slackDeliveryMode: "simulated",
        });
        return;
      }
      if (demo && livePreview) {
        const response = await fetch("/__slack-preview/invitations", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            organizationId,
            company: draft.company,
            email: recipient,
            ...(customChannel === null ? {} : { channelName: channel }),
          }),
        });
        const result = await response.json();
        if (!response.ok)
          throw new Error(
            result.error ?? "The Slack invitation could not be confirmed.",
          );

        onInvited({
          slack: result.channel_name,
          slackEmail: result.email,
          slackStatus: result.status,
          slackDeliveryMode: "live",
        });
        return;
      }
      if (!draft.ndaDocumentId)
        throw new Error("Complete the mutual NDA first.");

      const result = await createSlackInvitation(
        organizationId,
        draft.ndaDocumentId,
        recipient,
        customChannel === null ? undefined : channel,
      );
      onInvited({
        slack: result.channel_name,
        slackEmail: result.email,
        slackStatus: result.status,
        slackDeliveryMode: "live",
      });
    } catch (error) {
      if (
        error instanceof Error &&
        error.message.includes("channel name is already in use")
      )
        setCustomChannel(channel);
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
          {customChannel !== null && (
            <label className="gs-field">
              <span>Slack channel name</span>
              <input
                type="text"
                maxLength={80}
                value={customChannel}
                disabled={busy}
                onChange={(event) => {
                  setCustomChannel(event.target.value);
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
            We’ll create <strong>#{channel}</strong> and invite{" "}
            <strong>{recipient}</strong>.
          </p>
          {customChannel === null && (
            <button
              type="button"
              className="gs-text-button"
              disabled={busy}
              onClick={() => setCustomChannel(channel)}
            >
              Change channel name
            </button>
          )}
          <button
            type="button"
            className="gr-button"
            disabled={
              busy || checkingPreview || !validRecipient || !validChannel
            }
            onClick={() => void send()}
          >
            {busy
              ? "Sending invite…"
              : checkingPreview
                ? "Loading…"
                : "Send Slack invite"}
          </button>
        </>
      ) : (
        <p role="status">
          <CheckCircle2 size={16} />{" "}
          {demo && !livePreview
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
      {demo && !livePreview && (
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
