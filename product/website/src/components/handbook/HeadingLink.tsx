import { Check, Link } from "lucide-react";
import { Children, isValidElement, useEffect, useRef, useState } from "react";
import type {
  ComponentPropsWithoutRef,
  MouseEvent,
  ReactElement,
  ReactNode,
} from "react";
import { pinToAnchor } from "../../pin-to-anchor";

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

      return pinToAnchor(anchor);
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
