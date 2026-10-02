import { useEffect, useRef } from "react";

export const useInfiniteScroll = ({
  hasNextPage,
  isFetching,
  isError,
  fetchNextPage,
  enabled = true,
  autoLoad = true,
}: {
  hasNextPage: boolean;
  isFetching: boolean;
  isError: boolean;
  fetchNextPage: (options: { cancelRefetch: boolean }) => Promise<unknown>;
  enabled?: boolean;
  autoLoad?: boolean;
}) => {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const target = ref.current;
    if (!target || !enabled || !hasNextPage || isFetching || isError) return;

    let visible = false;
    let requested = false;
    const loadMore = () => {
      if (!visible || requested) return;

      requested = true;
      void fetchNextPage({ cancelRefetch: false });
    };
    const observer = new IntersectionObserver(([entry]) => {
      visible = Boolean(entry?.isIntersecting);
      if (autoLoad) loadMore();
    });
    const onWheel = (event: WheelEvent) => {
      if (event.deltaY > 0 && !event.defaultPrevented) loadMore();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (
        !event.defaultPrevented &&
        ["ArrowDown", "PageDown", "End"].includes(event.key) &&
        !(
          event.target instanceof HTMLElement &&
          event.target.closest("input, textarea, select, [contenteditable]")
        )
      )
        loadMore();
    };
    observer.observe(target);
    window.addEventListener("wheel", onWheel, { passive: true });
    window.addEventListener("touchmove", loadMore, { passive: true });
    window.addEventListener("keydown", onKeyDown);

    return () => {
      observer.disconnect();
      window.removeEventListener("wheel", onWheel);
      window.removeEventListener("touchmove", loadMore);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [enabled, autoLoad, hasNextPage, isFetching, isError, fetchNextPage]);

  return ref;
};
