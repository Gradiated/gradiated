import { Fragment, useEffect, useState } from "react";
import type { ReactElement, ReactNode } from "react";

import generated from "../../../docs/training/generated/error-codes.json";
import {
  AREA_ORDER,
  CLIENT_ERROR_DOCS,
  ERROR_DOCS,
  STATUS_MEANING,
} from "./error-docs";
import type { ErrorDoc } from "./error-docs";

type Entry = ErrorDoc & { code: string; statuses: number[] };

const SERVER_CODES = (generated as { codes: Record<string, number[]> }).codes;

export const ERROR_ENTRIES: Entry[] = [
  ...Object.entries(SERVER_CODES).map(([code, statuses]) => ({
    code,
    statuses,
    ...(ERROR_DOCS[code] ?? {
      area: "Server and capacity" as const,
      means: "",
    }),
  })),
  ...Object.entries(CLIENT_ERROR_DOCS).map(([code, doc]) => ({ code, ...doc })),
].sort((a, b) => a.code.localeCompare(b.code));

/* `code`, and [links](/docs/...), in the short texts above. */
const inline = (text: string): ReactNode[] =>
  text.split(/(`[^`]+`|\[[^\]]+\]\([^)]+\))/g).map((part, index) => {
    if (part.startsWith("`"))
      return <code key={index}>{part.slice(1, -1)}</code>;
    const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(part);
    if (link) {
      return (
        <a href={link[2]} key={index}>
          {link[1]}
        </a>
      );
    }
    return <Fragment key={index}>{part}</Fragment>;
  });

const matches = (entry: Entry, query: string): boolean => {
  const words = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  const text =
    `${entry.code} ${entry.statuses.join(" ")} ${entry.means} ${entry.fix ?? ""}`.toLowerCase();
  return words.every((word) => text.includes(word));
};

export const DocsErrorCodes = (): ReactElement => {
  const [query, setQuery] = useState("");

  /* A problem's `type` (https://gradiated.com/problems/<code>) redirects
     here with ?code=<code>; #<code> links land on the entry too. */
  useEffect(() => {
    const code =
      new URLSearchParams(window.location.search).get("code") ??
      window.location.hash.slice(1);
    if (!ERROR_ENTRIES.some((entry) => entry.code === code)) return;

    const element = document.getElementById(code);
    element?.scrollIntoView();
    element?.setAttribute("data-current", "true");
  }, []);

  const visible = ERROR_ENTRIES.filter((entry) => matches(entry, query));
  const statuses = [
    ...new Set(ERROR_ENTRIES.flatMap((entry) => entry.statuses)),
  ].sort();

  return (
    <div className="gr-errors">
      <div className="gr-api-filter">
        <label className="gr-api-filter-label" htmlFor="gr-errors-filter">
          Find a code
        </label>
        <input
          autoComplete="off"
          className="gr-api-filter-input"
          id="gr-errors-filter"
          onChange={(event) => setQuery(event.target.value)}
          placeholder="artifact_pinned, 409, secret…"
          type="search"
          value={query}
        />
        <span aria-live="polite" className="gr-api-filter-count">
          {query
            ? `${visible.length} of ${ERROR_ENTRIES.length}`
            : `${ERROR_ENTRIES.length} codes`}
        </span>
      </div>

      <p className="gr-errors-statuses">
        {statuses.map((status) => (
          <a href={`#status-${status}`} key={status}>
            {status}
          </a>
        ))}
      </p>

      {AREA_ORDER.map((area) => {
        const entries = visible.filter((entry) => entry.area === area);
        if (!entries.length) return null;
        return (
          <section key={area}>
            <h2
              className="gr-doc-heading"
              id={area.toLowerCase().replace(/\W+/g, "-")}
            >
              {area}
            </h2>
            <dl className="gr-errors-list">
              {entries.map((entry) => (
                <div
                  className="gr-errors-entry"
                  id={entry.code}
                  key={entry.code}
                >
                  <dt>
                    <a className="gr-errors-code" href={`#${entry.code}`}>
                      <code>{entry.code}</code>
                    </a>
                    {entry.statuses.map((status) => (
                      <span className="gr-api-status" key={status}>
                        {status}
                      </span>
                    ))}
                  </dt>
                  <dd>
                    <p>{inline(entry.means)}</p>
                    {entry.fix ? (
                      <p className="gr-errors-fix">
                        <span>Fix</span> {inline(entry.fix)}
                      </p>
                    ) : null}
                  </dd>
                </div>
              ))}
            </dl>
          </section>
        );
      })}

      <h2 className="gr-doc-heading" id="by-status">
        By HTTP status
      </h2>
      <dl className="gr-errors-bystatus">
        {statuses.map((status) => (
          <div id={`status-${status}`} key={status}>
            <dt>
              <span className="gr-api-status">{status}</span>{" "}
              {STATUS_MEANING[status] ?? ""}
            </dt>
            <dd>
              {ERROR_ENTRIES.filter((entry) =>
                entry.statuses.includes(status),
              ).map((entry, index) => (
                <Fragment key={entry.code}>
                  {index ? ", " : null}
                  <a href={`#${entry.code}`}>
                    <code>{entry.code}</code>
                  </a>
                </Fragment>
              ))}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
};
