export const mountVisibleTicker = (element, ticker, frame, onPause) => {
  const page = element.ownerDocument;
  let intersecting = false;
  let running = false;
  let disposed = false;

  const update = () => {
    if (disposed) return;

    const visible = intersecting && page.visibilityState === "visible";
    if (visible === running) return;

    running = visible;
    if (running) ticker.add(frame);
    else {
      ticker.remove(frame);
      onPause();
    }
  };
  const observer = new page.defaultView.IntersectionObserver((entries) => {
    const entry = entries[entries.length - 1];
    intersecting = entry.isIntersecting && entry.intersectionRatio > 0;
    update();
  });

  observer.observe(element);
  page.addEventListener("visibilitychange", update);

  return () => {
    disposed = true;
    observer.disconnect();
    page.removeEventListener("visibilitychange", update);
    ticker.remove(frame);
    if (running) onPause();
    running = false;
  };
};
