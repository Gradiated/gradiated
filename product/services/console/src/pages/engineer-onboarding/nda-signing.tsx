import { ArrowLeft, ArrowRight, CheckCircle2 } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";

import {
  createNdaDocument,
  createNdaSession,
  getNdaDocument,
  type NdaDetails,
  type NdaDocument,
} from "@/api/engineer-onboarding";
import { Button } from "@/components/ui/button";
import { FieldError } from "@/components/ui/field";
import { httpStatus } from "@/lib/errors";

const detailsChanged = (bound: NdaDetails | null, expected: NdaDetails) =>
  bound !== null &&
  (bound.company.trim() !== expected.company.trim() ||
    bound.address.trim() !== expected.address.trim() ||
    bound.name.trim() !== expected.name.trim() ||
    bound.title.trim() !== expected.title.trim() ||
    bound.email.trim().toLowerCase() !== expected.email.trim().toLowerCase());

const ndaEmail = (details: NdaDetails) =>
  `mailto:team@gradiated.com?subject=${encodeURIComponent(
    `Mutual NDA for ${details.company}`,
  )}&body=${encodeURIComponent(
    [
      "Please send us the mutual NDA to sign.",
      "",
      `Company: ${details.company}`,
      `Address: ${details.address}`,
      `Signer: ${details.name}, ${details.title}`,
      `Email: ${details.email}`,
    ].join("\n"),
  )}`;

const EmailFallback = ({ details }: { details: NdaDetails }) => (
  <a
    className="font-medium underline underline-offset-4"
    href={ndaEmail(details)}
  >
    Email us your NDA details
  </a>
);

const PandaDocEmbed = ({
  sessionId,
  details,
  onVerify,
}: {
  sessionId: string;
  details: NdaDetails;
  onVerify: () => void;
}) => {
  const id = useId();
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    let signing: import("pandadoc-signing").Signing | undefined;

    void import("pandadoc-signing")
      .then(async ({ Signing }) => {
        if (!active) return;

        signing = new Signing(
          id,
          { sessionId, height: 650 },
          { region: "com" },
        );
        signing.on("document.completed", onVerify);
        signing.on("document.exception", () => setError(true));
        await signing.open();
      })
      .catch(() => {
        if (active) setError(true);
      });

    return () => {
      active = false;
      signing?.destroy();
    };
  }, [id, sessionId, onVerify]);

  return (
    <>
      {error ? (
        <FieldError>
          The signing window could not load. Close it and reopen to get a fresh
          session, or <EmailFallback details={details} />.
        </FieldError>
      ) : null}
      <div className="min-h-[650px] overflow-hidden rounded-lg border">
        <div id={id} />
      </div>
    </>
  );
};

export const NdaSigning = ({
  organizationId,
  details,
  initialDocumentId,
  onDocument,
  onComplete,
  onBack,
}: {
  organizationId: string;
  details: NdaDetails;
  initialDocumentId: string | null;
  onDocument: (id: string) => void;
  onComplete: (documentId: string) => void;
  onBack: () => void;
}) => {
  const [documentId, setDocumentId] = useState(initialDocumentId);
  const [document, setDocument] = useState<NdaDocument | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [pollError, setPollError] = useState("");
  const [checked, setChecked] = useState(false);
  const openedAutomatically = useRef(false);
  const active = useRef(true);
  const callbacks = useRef({ onComplete, onDocument, details });
  callbacks.current = { onComplete, onDocument, details };

  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);

  const verify = useCallback(async () => {
    if (!documentId) return null;

    const current = await getNdaDocument(organizationId, documentId);
    if (!active.current) return null;
    if (detailsChanged(current.details, callbacks.current.details))
      throw new Error(
        "The NDA details have changed. Return to your details and prepare a new copy.",
      );

    setDocument(current);
    if (current.status === "completed") {
      setSessionId(null);
      callbacks.current.onComplete(current.id);
    }

    return current;
  }, [organizationId, documentId]);

  useEffect(() => {
    if (!documentId || document?.status === "completed") return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        await verify();
        if (!cancelled) setPollError("");
      } catch (error) {
        if (!cancelled)
          setPollError(
            error instanceof Error
              ? error.message
              : "Could not check signing status.",
          );
      }
      if (!cancelled) timer = setTimeout(() => void poll(), 5000);
    };
    void poll();

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [documentId, document?.status, verify]);

  const open = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    setError("");
    setChecked(false);

    try {
      // A stored copy that is gone or can no longer be signed (voided,
      // declined) is replaced rather than retried forever.
      const stored = documentId
        ? await getNdaDocument(organizationId, documentId).catch(
            (error: unknown) => {
              if (httpStatus(error) === 404) return null;
              throw error;
            },
          )
        : null;
      if (!active.current) return;
      let current =
        stored && stored.status !== "unavailable"
          ? stored
          : await createNdaDocument(organizationId, details);
      if (!active.current) return;
      if (detailsChanged(current.details, details))
        throw new Error("The NDA details have changed. Prepare a new copy.");

      setDocumentId(current.id);
      callbacks.current.onDocument(current.id);
      setDocument(current);
      for (
        let attempt = 0;
        current.status === "preparing" && attempt < 10;
        attempt++
      ) {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        if (!active.current) return;
        current = await getNdaDocument(organizationId, current.id);
        if (!active.current) return;
        setDocument(current);
      }

      if (detailsChanged(current.details, details))
        throw new Error("The NDA details have changed. Prepare a new copy.");

      if (current.status === "completed") {
        callbacks.current.onComplete(current.id);
        return;
      }
      if (current.customer_completed) return;
      if (current.status !== "ready")
        throw new Error(
          "The NDA is still being prepared or needs attention. Try opening it again shortly.",
        );

      const session = await createNdaSession(organizationId, current.id);
      if (active.current) setSessionId(session.session_id);
    } catch (error) {
      if (active.current)
        setError(
          error instanceof Error ? error.message : "Could not open the NDA.",
        );
    } finally {
      if (active.current) setBusy(false);
    }
  }, [busy, documentId, organizationId, details]);

  useEffect(() => {
    if (openedAutomatically.current) return;

    openedAutomatically.current = true;
    void open();
  }, [open]);

  const checkStatus = useCallback(() => {
    setChecked(false);
    void verify()
      .then(() => setChecked(true))
      .catch((error: Error) => setPollError(error.message));
  }, [verify]);

  const verifyCompletion = useCallback(() => {
    void verify().catch(() =>
      setError("Could not confirm completion. Try checking again."),
    );
  }, [verify]);

  return (
    <section className="flex flex-col gap-4" aria-labelledby="signing-title">
      <h1 id="signing-title" className="text-2xl font-bold tracking-tight">
        Review & sign your NDA
      </h1>
      {document?.status === "completed" ? (
        <p role="status" className="flex items-center gap-2 text-sm">
          <CheckCircle2 className="size-4 text-emerald-600" /> NDA completed.
        </p>
      ) : document?.customer_completed ? (
        <p role="status" className="text-sm text-muted-foreground">
          You’ve signed. Waiting for PostHog’s signature.
        </p>
      ) : sessionId ? (
        <PandaDocEmbed
          sessionId={sessionId}
          details={details}
          onVerify={verifyCompletion}
        />
      ) : error ? (
        <Button
          type="button"
          className="self-start"
          disabled={busy}
          onClick={() => void open()}
        >
          {busy ? "Preparing your NDA…" : "Try again"}
          <ArrowRight />
        </Button>
      ) : (
        <p role="status" className="text-sm text-muted-foreground">
          Preparing your NDA…
        </p>
      )}
      {error ? (
        <FieldError>
          {error} <EmailFallback details={details} />
        </FieldError>
      ) : pollError ? (
        <FieldError>{pollError}</FieldError>
      ) : null}
      {checked &&
      document &&
      document.status !== "completed" &&
      !document.customer_completed ? (
        <p role="status" className="text-sm text-muted-foreground">
          {sessionId
            ? "Not signed yet. Sign in the window above."
            : "Not signed yet. Open the NDA to sign it."}
        </p>
      ) : null}
      <div className="flex items-center justify-between gap-3">
        <Button type="button" variant="ghost" onClick={onBack}>
          <ArrowLeft /> Back to details
        </Button>
        {documentId ? (
          <Button type="button" variant="link" onClick={checkStatus}>
            Check signing status
          </Button>
        ) : null}
      </div>
    </section>
  );
};
