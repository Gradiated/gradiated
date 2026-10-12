export const createProbeDeadline = (
  parent: AbortSignal,
  milliseconds: number,
) => {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;

  const dispose = () => {
    clearTimeout(timer);
    parent.removeEventListener("abort", abortFromParent);
  };
  const abortFromParent = () => {
    controller.abort(parent.reason);
    dispose();
  };

  if (parent.aborted) {
    abortFromParent();
  } else {
    parent.addEventListener("abort", abortFromParent, { once: true });
    // Node 22.23.2 retains expired AbortSignal.any([parent, timeout]) signals.
    timer = setTimeout(() => {
      controller.abort(
        new DOMException("Probe deadline exceeded", "TimeoutError"),
      );
      dispose();
    }, milliseconds);
    timer.unref();
  }

  return { signal: controller.signal, dispose };
};
