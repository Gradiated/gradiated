import { Check, Link } from "lucide-react";
import { Children, isValidElement, useEffect, useRef, useState } from "react";
import type {
  ComponentPropsWithoutRef,
  MouseEvent,
  ReactElement,
  ReactNode,
} from "react";

const textOf = (node: ReactNode): string =>
  Children.toArray(node)
    .map((child) => {
      if (typeof child === "string" || typeof child === "number") {
        return String(child);
      }
      if (isValidElement<{ children?: ReactNode }>(child)) {
        return textOf(child.props.children);
      }
      return "";
    })
    .join("");

const slugify = (text: string): string =>
  text
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9\s-]/g, "")
    .trim()
    .replace(/[\s-]+/g, "-");

type Level = "h2" | "h3" | "h4";

const userScrollEvents = ["wheel", "touchstart", "keydown", "pointerdown"];

const makeHeading = (Tag: Level) => {
  const Heading = ({
    children,
    id,
    ...props
  }: ComponentPropsWithoutRef<Level>): ReactElement => {
    const anchor = id ?? slugify(textOf(children));
    const [copied, setCopied] = useState(false);
    const timer = useRef<number | undefined>(undefined);

    useEffect(() => () => window.clearTimeout(timer.current), []);

    useEffect(() => {
      let hash = "";
      try {
        hash = decodeURIComponent(window.location.hash.slice(1));
      } catch {
        return;
      }
      if (hash !== anchor) return;

      const scroll = (): void => {
        document.getElementById(anchor)?.scrollIntoView({
          behavior: "instant",
          block: "start",
        });
      };

      // The rail's 650 ms slide into doc mode reflows the page, so the heading
      // is re-pinned on every resize until it settles or the reader scrolls.
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
    }, [anchor]);

    const copy = (event: MouseEvent<HTMLAnchorElement>): void => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
        return;
      }
      event.preventDefault();
      const url = new URL(window.location.href);
      url.hash = anchor;
      window.history.replaceState(null, "", url);
      void navigator.clipboard?.writeText(url.toString()).then(() => {
        setCopied(true);
        window.clearTimeout(timer.current);
        timer.current = window.setTimeout(() => setCopied(false), 1500);
      });
    };

    return (
      <Tag {...props} className="gr-heading-anchor" id={anchor}>
        {children}
        <a
          aria-label={copied ? "Link copied" : "Copy link to this section"}
          className="gr-heading-anchor__link"
          data-copied={copied || undefined}
          href={`#${anchor}`}
          onClick={copy}
          title={copied ? "Link copied" : "Copy link"}
        >
          {copied ? (
            <Check aria-hidden="true" className="gr-heading-anchor__icon" />
          ) : (
            <Link aria-hidden="true" className="gr-heading-anchor__icon" />
          )}
        </a>
      </Tag>
    );
  };
  Heading.displayName = `HeadingLink(${Tag})`;
  return Heading;
};

export const H2 = makeHeading("h2");
export const H3 = makeHeading("h3");
export const H4 = makeHeading("h4");
