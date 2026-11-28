import { Fragment, useEffect, useMemo, useState } from "react";
import type { ReactElement, ReactNode } from "react";

import { useSdkLanguage } from "../DocsLanguage";
import { CodeSample } from "./CodeSample";
import RECORDED_JSON from "../../../docs/training/generated/api-responses.json";
import REQUEST_EXAMPLES_JSON from "./api-examples.json";
import {
  API,
  TAG_ORDER,
  childrenOf,
  constraints,
  enumValues,
  example,
  isNullable,
  operationAnchor,
  pathExample,
  resolve,
  tagAnchor,
  typeLabel,
  variantsOf,
} from "./api-schema";
import type { Operation, Param, Schema } from "./api-schema";
import { SDK_CALLS } from "./api-sdk";
import type { SdkLanguage } from "./data";

/* Inline `code` in the spec's descriptions. */
const prose = (text: string): ReactNode[] =>
  text
    .split(/(`[^`]+`)/g)
    .map((part, index) =>
      part.startsWith("`") && part.endsWith("`") ? (
        <code key={index}>{part.slice(1, -1)}</code>
      ) : (
        <Fragment key={index}>{part}</Fragment>
      ),
    );

const sentence = (text: string): string =>
  `${text.charAt(0).toUpperCase()}${text.slice(1)}${/[.!?]$/.test(text) ? "" : "."}`;

const Field = ({
  name,
  schema,
  required,
  depth,
}: {
  name: string;
  schema: Schema;
  required: boolean;
  depth: number;
}): ReactElement => {
  const resolved = resolve(schema);
  const values = enumValues(schema);
  const limits = constraints(schema);
  const children = depth < 5 ? childrenOf(schema) : null;
  const variants = depth < 5 && !values ? variantsOf(schema) : [];
  const description = schema.description ?? resolved.description;

  return (
    <li className="gr-api-field">
      <div className="gr-api-field-head">
        <code className="gr-api-field-name">{name}</code>
        <span className="gr-api-field-type">{typeLabel(schema)}</span>
        {required ? <span className="gr-api-field-req">required</span> : null}
        {isNullable(schema) ? (
          <span className="gr-api-field-meta">nullable</span>
        ) : null}
        {limits.map((limit) => (
          <span className="gr-api-field-meta" key={limit}>
            {limit}
          </span>
        ))}
      </div>
      {description ? (
        <p className="gr-api-field-desc">{prose(description)}</p>
      ) : null}
      {resolved.pattern ? (
        <p className="gr-api-field-pattern">
          Matches <code>{resolved.pattern}</code>
        </p>
      ) : null}
      {values ? (
        <p className="gr-api-field-enum">
          {values.map((value) => (
            <code key={String(value)}>{JSON.stringify(value)}</code>
          ))}
        </p>
      ) : null}
      {children ? (
        <details className="gr-api-children">
          <summary>
            {Object.keys(children.properties).length} child fields
          </summary>
          <Fields
            depth={depth + 1}
            properties={children.properties}
            required={children.required}
          />
        </details>
      ) : null}
      {!children && variants.length > 1 ? (
        <details className="gr-api-children">
          <summary>One of {variants.length} shapes</summary>
          <ol className="gr-api-variants">
            {variants.map((variant, index) => {
              const shape = childrenOf(variant);
              return (
                <li key={index}>
                  <span className="gr-api-field-type">
                    {typeLabel(variant)}
                  </span>
                  {shape ? (
                    <Fields
                      depth={depth + 1}
                      properties={shape.properties}
                      required={shape.required}
                    />
                  ) : null}
                </li>
              );
            })}
          </ol>
        </details>
      ) : null}
    </li>
  );
};

const Fields = ({
  properties,
  required,
  depth = 0,
}: {
  properties: Record<string, Schema>;
  required: string[];
  depth?: number;
}): ReactElement => (
  <ul className="gr-api-fields">
    {Object.entries(properties).map(([name, schema]) => (
      <Field
        depth={depth}
        key={name}
        name={name}
        required={required.includes(name)}
        schema={schema}
      />
    ))}
  </ul>
);

const ParamList = ({ params }: { params: Param[] }): ReactElement => (
  <ul className="gr-api-fields">
    {params.map((param) => (
      <Field
        depth={0}
        key={param.name}
        name={param.name}
        required={param.required}
        schema={{ ...param.schema, description: param.description }}
      />
    ))}
  </ul>
);

/* Replayed against a live grad-server by grad's
   `scripts/check-docs-snippets.py --api-examples`. */
const REQUEST_EXAMPLES: Record<string, unknown> = REQUEST_EXAMPLES_JSON;

/* Responses recorded from a live grad-server by the same replay
   (`--api-examples --capture`), redacted; the schema fills the gaps. */
const RECORDED = RECORDED_JSON as {
  server: string | null;
  responses: Record<string, { status: number; body: unknown }>;
};

const bodyExample = (op: Operation): unknown =>
  REQUEST_EXAMPLES[op.id] ??
  (op.body ? example(op.body, { requiredOnly: true }) : null);

const urlOf = (op: Operation): string => {
  const path = op.path.replace(/\{(\w+)\}/g, (_, name: string) =>
    pathExample(op, name),
  );
  const query = op.params
    .filter((param) => param.in === "query" && param.required)
    .map((param) => `${param.name}=${String(example(param.schema))}`);
  return `$GRADIATED_BASE_URL${path}${query.length ? `?${query.join("&")}` : ""}`;
};

export const curlFor = (op: Operation): string => {
  const lines = [
    `curl${op.method === "GET" ? "" : ` -X ${op.method}`} "${urlOf(op)}"`,
    '  -H "Authorization: Bearer $GRADIATED_API_KEY"',
  ];
  const body = bodyExample(op);
  if (op.body && body !== null) {
    lines.push('  -H "Content-Type: application/json"');
    lines.push(
      `  -d '${JSON.stringify(body, null, 2).replace(/\n/g, "\n  ")}'`,
    );
  }
  if (op.id === "downloadArtifact") lines.push("  -o bundle.grad.tar.gz");
  return lines.join(" \\\n");
};

const SDK_PREFIX: Record<
  Exclude<SdkLanguage, "CLI">,
  (call: string) => string
> = {
  Python: (call) => `client.${call}(…)`,
  TypeScript: (call) => `await grad.${call}(…)`,
  Go: (call) =>
    /^[a-z]/.test(call) ? `${call}(ctx, …)` : `client.${call}(ctx, …)`,
  Rust: (call) => {
    const [resource, method] = call.split(".");
    return `client.${resource}().${method}(…).await?`;
  },
};

const SDK_LANG: Record<SdkLanguage, string> = {
  Python: "python",
  TypeScript: "typescript",
  Go: "go",
  Rust: "rust",
  CLI: "bash",
};

const RequestSample = ({ op }: { op: Operation }): ReactElement => {
  const language = useSdkLanguage();
  const call = SDK_CALLS[op.id]?.[language];
  const [mode, setMode] = useState<"sdk" | "http" | null>(null);
  const sdkCode = call
    ? language === "CLI"
      ? call
      : SDK_PREFIX[language](call)
    : null;
  const shown = sdkCode && mode !== "http" ? "sdk" : "http";

  return (
    <div className="gr-api-sample">
      <div className="gr-api-sample-head">
        <span className="gr-api-sample-title">Request</span>
        <div
          className="gr-api-sample-modes"
          role="group"
          aria-label="Request sample"
        >
          <button
            aria-pressed={shown === "sdk"}
            disabled={!sdkCode}
            onClick={() => setMode("sdk")}
            title={sdkCode ? undefined : `No ${language} wrapper; use HTTP`}
            type="button"
          >
            {language}
          </button>
          <button
            aria-pressed={shown === "http"}
            onClick={() => setMode("http")}
            type="button"
          >
            curl
          </button>
        </div>
      </div>
      {shown === "sdk" && sdkCode ? (
        <CodeSample code={sdkCode} label={language} lang={SDK_LANG[language]} />
      ) : (
        <CodeSample code={curlFor(op)} label="curl" lang="bash" />
      )}
    </div>
  );
};

const STATUS_TEXT: Record<number, string> = {
  200: "OK",
  201: "Created",
  202: "Accepted",
  204: "No Content",
};

const ResponseSample = ({ op }: { op: Operation }): ReactElement | null => {
  const response = op.responses[0];
  if (!response) return null;
  const recorded = RECORDED.responses[op.id];
  const json = response.contentType === "application/json" && response.schema;
  const status = recorded?.status ?? response.status;

  return (
    <div className="gr-api-sample">
      <div className="gr-api-sample-head">
        <span className="gr-api-sample-title">
          Response <span className="gr-api-status">{status}</span>{" "}
          {STATUS_TEXT[status] ?? ""}
        </span>
        <span className="gr-api-sample-source">
          {recorded
            ? `Recorded from grad-server ${RECORDED.server ?? ""}`
            : json
              ? "Generated from the schema"
              : null}
        </span>
      </div>
      {recorded || json ? (
        <CodeSample
          code={JSON.stringify(
            recorded ? recorded.body : example(response.schema ?? {}),
            null,
            2,
          )}
          label="JSON"
          lang="json"
        />
      ) : (
        <p className="gr-api-empty">
          {response.contentType
            ? `${response.contentType}: ${response.description}`
            : response.description}
        </p>
      )}
    </div>
  );
};

const Endpoint = ({ op }: { op: Operation }): ReactElement => {
  const anchor = operationAnchor(op);
  const path = op.params.filter((param) => param.in === "path");
  const query = op.params.filter((param) => param.in === "query");
  const headers = op.params.filter((param) => param.in === "header");
  const body = op.body ? childrenOf(op.body) : null;
  const response = op.responses[0];
  const returns = response?.schema ?? null;
  const returnsShape = returns ? childrenOf(returns) : null;

  return (
    <section aria-labelledby={anchor} className="gr-api-op" data-op={op.id}>
      <h3 className="gr-doc-heading gr-api-op-title" id={anchor}>
        {op.summary.replace(/\s*\(.*\)$/, "") || op.id}
        <a
          aria-label={`Link to ${op.summary}`}
          className="gr-doc-anchor"
          href={`#${anchor}`}
        >
          #
        </a>
      </h3>
      <p className="gr-api-route">
        <span className="gr-api-method" data-method={op.method}>
          {op.method}
        </span>
        <code>{op.path}</code>
      </p>
      <div className="gr-api-grid">
        <div className="gr-api-spec">
          {/\(.*\)$/.test(op.summary) ? (
            <p>{prose(sentence(op.summary.replace(/^.*\((.*)\)$/, "$1")))}</p>
          ) : null}
          {op.description ? <p>{prose(op.description)}</p> : null}
          {path.length ? (
            <>
              <h4>Path parameters</h4>
              <ParamList params={path} />
            </>
          ) : null}
          {query.length ? (
            <>
              <h4>Query parameters</h4>
              <ParamList params={query} />
            </>
          ) : null}
          {headers.length ? (
            <>
              <h4>Headers</h4>
              <ParamList params={headers} />
            </>
          ) : null}
          {body ? (
            <>
              <h4>
                Body{" "}
                {op.body?.$ref ? (
                  <span className="gr-api-field-type">{op.body.$ref}</span>
                ) : null}
              </h4>
              <Fields properties={body.properties} required={body.required} />
            </>
          ) : null}
          <h4>Returns</h4>
          {op.responses.map((variant) => (
            <p className="gr-api-returns" key={variant.status}>
              <span className="gr-api-status">{variant.status}</span>{" "}
              {variant.schema ? (
                <span className="gr-api-field-type">
                  {typeLabel(variant.schema)}
                </span>
              ) : null}{" "}
              {prose(variant.description)}
            </p>
          ))}
          {returnsShape ? (
            <details className="gr-api-children">
              <summary>
                {Object.keys(returnsShape.properties).length} fields
              </summary>
              <Fields
                properties={returnsShape.properties}
                required={returnsShape.required}
              />
            </details>
          ) : null}
          {op.errors.length ? (
            <p className="gr-api-errors">
              Errors:{" "}
              {op.errors.map((status, index) => (
                <Fragment key={status}>
                  {index ? " " : null}
                  <a href={`/docs/training/errors/#status-${status}`}>
                    {status}
                  </a>
                </Fragment>
              ))}
            </p>
          ) : null}
        </div>
        <div className="gr-api-samples">
          <RequestSample op={op} />
          <ResponseSample op={op} />
        </div>
      </div>
    </section>
  );
};

const matches = (op: Operation, query: string): boolean => {
  if (!query) return true;
  const haystack =
    `${op.method} ${op.path} ${op.summary} ${op.id} ${op.tag}`.toLowerCase();
  return query
    .toLowerCase()
    .split(/\s+/)
    .every((word) => haystack.includes(word));
};

export const DocsApiReference = (): ReactElement => {
  const [query, setQuery] = useState("");
  const groups = useMemo(
    () =>
      [...new Set(API.operations.map((op) => op.tag))]
        .sort((a, b) => TAG_ORDER.indexOf(a) - TAG_ORDER.indexOf(b))
        .map((tag) => ({
          tag,
          operations: API.operations.filter((op) => op.tag === tag),
        })),
    [],
  );
  const visible = API.operations.filter((op) => matches(op, query)).length;

  /* The page keeps settling after hydration (the rail, the contents, the
     samples in the reader's language); land a deep link on its endpoint
     again once it has, unless the reader has started moving. */
  useEffect(() => {
    const anchor = window.location.hash.slice(1);
    if (!anchor) return;

    let moved = false;
    const onIntent = () => {
      moved = true;
    };
    const intents = ["wheel", "touchstart", "keydown", "mousedown"] as const;
    intents.forEach((type) => window.addEventListener(type, onIntent));

    const land = () => {
      if (!moved) document.getElementById(anchor)?.scrollIntoView();
    };
    const frame = window.requestAnimationFrame(land);
    const later = window.setTimeout(land, 1000);
    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(later);
      intents.forEach((type) => window.removeEventListener(type, onIntent));
    };
  }, []);

  return (
    <div className="gr-api">
      <div className="gr-api-filter">
        <label className="gr-api-filter-label" htmlFor="gr-api-filter">
          Filter {API.operations.length} endpoints
        </label>
        <input
          autoComplete="off"
          className="gr-api-filter-input"
          id="gr-api-filter"
          onChange={(event) => setQuery(event.target.value)}
          placeholder="runs cancel, POST /v1/evals, artifact…"
          type="search"
          value={query}
        />
        <span aria-live="polite" className="gr-api-filter-count">
          {query
            ? `${visible} match${visible === 1 ? "" : "es"}`
            : `spec ${API.version}`}
        </span>
      </div>
      <nav aria-label="Endpoints" className="gr-api-index">
        {groups.map(({ tag, operations }) => (
          <div className="gr-api-index-group" key={tag}>
            <a className="gr-api-index-tag" href={`#${tagAnchor(tag)}`}>
              {tag}
            </a>
            <ul>
              {operations.map((op) => (
                <li hidden={!matches(op, query)} key={op.id}>
                  <a href={`#${operationAnchor(op)}`}>
                    <span className="gr-api-method" data-method={op.method}>
                      {op.method}
                    </span>
                    <code>{op.path}</code>
                  </a>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>
      {groups.map(({ tag, operations }) => {
        const shown = operations.filter((op) => matches(op, query));
        return (
          <div hidden={!shown.length} key={tag}>
            <h2 className="gr-doc-heading" id={tagAnchor(tag)}>
              {tag}
              <a
                aria-label={`Link to ${tag}`}
                className="gr-doc-anchor"
                href={`#${tagAnchor(tag)}`}
              >
                #
              </a>
            </h2>
            {operations.map((op) => (
              <div hidden={!matches(op, query)} key={op.id}>
                <Endpoint op={op} />
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
};
