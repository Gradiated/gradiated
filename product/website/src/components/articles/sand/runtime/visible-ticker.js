export const mountVisibleTicker = (element, ticker, frame, onPause, motion) => {
  const page = element.ownerDocument;
  const view = page.defaultView;
  let intersecting = false;
  let running = false;
  let disposed = false;
  let pending = 0;

  const visible = () => intersecting && page.visibilityState === "visible";
  const cancelPending = () => {
    if (pending) view.cancelAnimationFrame(pending);
    pending = 0;
  };
  const invalidate = () => {
    if (disposed || !visible() || !motion?.matches || pending) return;

    pending = view.requestAnimationFrame(() => {
      pending = 0;
      if (!disposed && visible()) frame(0, 0);
    });
  };
  const update = () => {
    if (disposed) return;

    const continuous = visible() && !motion?.matches;
    if (continuous !== running) {
      running = continuous;
      if (running) ticker.add(frame);
      else {
        ticker.remove(frame);
        onPause();
      }
    }

    if (visible() && motion?.matches) invalidate();
    else cancelPending();
  };
  const observer = new view.IntersectionObserver((entries) => {
    const entry = entries[entries.length - 1];
    intersecting = entry.isIntersecting && entry.intersectionRatio > 0;
    update();
  });

  observer.observe(element);
  page.addEventListener("visibilitychange", update);
  motion?.addEventListener("change", update);

  return {
    invalidate,
    destroy: () => {
      disposed = true;
      observer.disconnect();
      page.removeEventListener("visibilitychange", update);
      motion?.removeEventListener("change", update);
      cancelPending();
      ticker.remove(frame);
      if (running) onPause();
      running = false;
    },
  };
};
