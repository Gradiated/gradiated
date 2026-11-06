import { useCallback, useEffect, useId, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, CheckCircle2 } from "lucide-react";
import {
  createNdaDocument,
  createNdaSession,
  getNdaDocument,
  type NdaDetails,
  type NdaDocument,
} from "../api/nda";

const sameDetails = (first: NdaDetails, second: NdaDetails) =>
  first.company.trim() === second.company.trim() &&
  first.address.trim() === second.address.trim() &&
  first.name.trim() === second.name.trim() &&
  first.title.trim() === second.title.trim() &&
  first.email.trim().toLowerCase() === second.email.trim().toLowerCase();

const sandboxRequest = async (path: string, body: unknown) => {
  const response = await fetch(`/__nda-sandbox${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const result = (await response.json()) as {
    document: NdaDocument;
    session_id?: string;
    error?: string;
  };
  if (!response.ok)
    throw new Error(result.error ?? "Sandbox signing is unavailable.");

  return result;
};

const PandaDocEmbed = ({
  sessionId,
  onVerify,
}: {
  sessionId: string;
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
      {error && (
        <p role="alert" className="gs-note">
          The signing window could not load. Close it and reopen to get a fresh
          session.
        </p>
      )}
      <div className="gs-signing-embed">
        <div id={id} />
      </div>
    </>
  );
};

export const NdaSigning = ({
  organizationId,
  details,
  initialDocumentId,
  demo,
  onDocument,
  onComplete,
  onBack,
}: {
  organizationId: string;
  details: NdaDetails;
  initialDocumentId: string | null;
  demo: boolean;
  onDocument: (id: string) => void;
  onComplete: (documentId: string) => void;
  onBack: () => void;
}) => {
  const [documentId, setDocumentId] = useState(demo ? null : initialDocumentId);
  const [document, setDocument] = useState<NdaDocument | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [demoSigned, setDemoSigned] = useState(false);
  const [sandboxEmail, setSandboxEmail] = useState("");
  const [configurationReady, setConfigurationReady] = useState(
    !import.meta.env.DEV || !demo,
  );
  const openedAutomatically = useRef(false);
  const active = useRef(true);
  const callbacks = useRef({ onComplete, onDocument, details });
  callbacks.current = { onComplete, onDocument, details };

  useEffect(() => {
    if (!import.meta.env.DEV || !demo) return;

    let cancelled = false;
    void fetch("/__nda-sandbox/")
      .then(async (response) => (response.ok ? response.json() : null))
      .then((configuration) => {
        if (!cancelled && configuration?.enabled)
          setSandboxEmail(configuration.signer_email);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setConfigurationReady(true);
      });

    return () => {
      cancelled = true;
    };
  }, [demo]);

  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);

  const verify = useCallback(async () => {
    if (!documentId || (demo && !sandboxEmail)) return null;

    const current = demo
      ? (await sandboxRequest("/status", { document_id: documentId })).document
      : await getNdaDocument(organizationId, documentId);
    if (!active.current) return null;
    if (
      !sameDetails(current.details, {
        ...callbacks.current.details,
        email: demo ? current.details.email : callbacks.current.details.email,
      })
    )
      throw new Error(
        "The NDA details have changed. Return to your details and prepare a new copy.",
      );

    setDocument(current);
    if (current.status === "completed") {
      setSessionId(null);
      callbacks.current.onComplete(current.id);
    }

    return current;
  }, [organizationId, documentId, demo, sandboxEmail]);

  useEffect(() => {
    if (
      !documentId ||
      (demo && !sandboxEmail) ||
      document?.status === "completed"
    )
      return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        await verify();
      } catch (error) {
        if (!cancelled)
          setError(
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
  }, [documentId, demo, sandboxEmail, document?.status, verify]);

  const open = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    setError("");

    try {
      if (demo && sandboxEmail) {
        const result = await sandboxRequest("/session", {
          details,
          document_id: documentId,
        });
        if (!active.current) return;

        setDocumentId(result.document.id);
        setDocument(result.document);
        callbacks.current.onDocument(result.document.id);
        if (result.document.status === "completed")
          callbacks.current.onComplete(result.document.id);
        else setSessionId(result.session_id ?? null);

        return;
      }

      let current = documentId
        ? await getNdaDocument(organizationId, documentId)
        : await createNdaDocument(organizationId, details);
      if (!active.current) return;
      if (!sameDetails(current.details, details))
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
  }, [busy, demo, sandboxEmail, documentId, organizationId, details]);

  useEffect(() => {
    if (
      !configurationReady ||
      openedAutomatically.current ||
      (demo && !sandboxEmail)
    )
      return;

    openedAutomatically.current = true;
    void open();
  }, [configurationReady, demo, sandboxEmail, open]);

  const verifyCompletion = useCallback(() => {
    void verify().catch(() =>
      setError("Could not confirm completion. Try checking again."),
    );
  }, [verify]);

  return (
    <section className="gs-signing" aria-labelledby="signing-title">
      <div className="gs-step-title">
        <h1 id="signing-title">Review & sign your NDA.</h1>
      </div>
      {!configurationReady ? (
        <p role="status">Preparing your NDA…</p>
      ) : demo && !sandboxEmail ? (
        <>
          <div className="gs-signing-demo">
            <h2>Mutual NDA</h2>
            <p>{details.company} × PostHog Inc.</p>
            <dl className="gs-summary">
              <div>
                <dt>Signer</dt>
                <dd>
                  {details.name} · {details.title}
                </dd>
              </div>
              <div>
                <dt>Email</dt>
                <dd>{details.email}</dd>
              </div>
            </dl>
            <p className="gs-note">
              The live signing window displays the complete NDA from PandaDoc,
              with its interactive signature field.
            </p>
            <button
              type="button"
              className="gr-button gs-primary"
              disabled={demoSigned}
              onClick={() => {
                setDemoSigned(true);
                onComplete("demo-nda");
              }}
            >
              {demoSigned ? "Demo signing complete" : "Simulate signing"}
              <ArrowRight size={15} />
            </button>
          </div>
          <p className="gs-note">
            Preview only. No signature is collected or agreement executed.
          </p>
        </>
      ) : (
        <>
          {demo && <p className="gs-note">Sandbox signer: {sandboxEmail}</p>}
          {document?.status === "completed" ? (
            <p role="status" className="gs-signed">
              <CheckCircle2 size={18} /> NDA completed.
            </p>
          ) : document?.customer_completed ? (
            <p role="status">You’ve signed. Waiting for PostHog’s signature.</p>
          ) : sessionId ? (
            <PandaDocEmbed sessionId={sessionId} onVerify={verifyCompletion} />
          ) : error ? (
            <button
              type="button"
              className="gr-button gs-primary"
              disabled={busy}
              onClick={() => void open()}
            >
              {busy ? "Preparing your NDA…" : "Try again"}
              <ArrowRight size={15} />
            </button>
          ) : (
            <p role="status">Preparing your NDA…</p>
          )}
          {documentId && (
            <button
              className="gs-text-button gs-signing-check"
              type="button"
              onClick={() => {
                void verify().catch((error: Error) => setError(error.message));
              }}
            >
              Check signing status
            </button>
          )}
          {error && (
            <p role="alert" className="gs-note">
              {error}
            </p>
          )}
        </>
      )}
      <button
        type="button"
        className="gs-back gs-signing-back"
        onClick={onBack}
      >
        <ArrowLeft size={14} /> Back to details
      </button>
    </section>
  );
};
