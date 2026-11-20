const userScrollEvents = ["wheel", "touchstart", "keydown", "pointerdown"];

// The rail's 650 ms slide into doc mode reflows the page, so the target is
// re-pinned on every resize until it settles or the reader scrolls.
export const pinToAnchor = (id: string): (() => void) => {
  const scroll = (): void => {
    document.getElementById(id)?.scrollIntoView({
      behavior: "instant",
      block: "start",
    });
  };

  const observer = new ResizeObserver(scroll);

  const stop = (): void => {
    observer.disconnect();
    window.clearTimeout(timeout);
    for (const type of userScrollEvents) {
      window.removeEventListener(type, stop);
    }
  };

  const timeout = window.setTimeout(stop, 1500);

  observer.observe(document.body);
  for (const type of userScrollEvents) {
    window.addEventListener(type, stop, { passive: true });
  }
  scroll();

  return stop;
};
