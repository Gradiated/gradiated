import Markdoc, {
  type Config,
  type Node,
  type RenderableTreeNode,
  type SchemaAttribute,
  type ValidateError,
} from "@markdoc/markdoc";

const textOf = (node: Node): string =>
  [...node.walk()]
    .filter((child) => child.type === "text")
    .map((child) => String(child.attributes.content ?? ""))
    .join("");

export const headingId = (text: string) =>
  text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");

const TONES = ["positive", "negative", "neutral"];
const FORMATS = ["number", "percent", "usd"];

const dataTag = {
  data: { type: String, required: true },
  title: { type: String },
  caption: { type: String },
};

const evalTag = (
  render: string,
  attributes: Record<string, SchemaAttribute> = {},
) => ({
  render,
  selfClosing: true,
  attributes: {
    eval: { type: String, required: true },
    models: { type: Array },
    metric: { type: String },
    title: { type: String },
    caption: { type: String },
    ...attributes,
  },
});

export const reportConfig: Config = {
  nodes: {
    document: {
      render: "ReportDocument",
      attributes: { frontmatter: { render: false } },
    },
    heading: {
      children: ["inline"],
      attributes: { level: { type: Number, required: true } },
      transform(node, config) {
        const level = Number(node.attributes.level);

        return new Markdoc.Tag(
          "Heading",
          { level, id: node.attributes.id ?? headingId(textOf(node)) },
          node.transformChildren(config),
        );
      },
    },
    link: {
      children: ["strong", "em", "s", "code", "text", "tag"],
      attributes: {
        href: { type: String, required: true },
        title: { type: String },
      },
      render: "ReportLink",
    },
    image: {
      attributes: {
        src: { type: String, required: true },
        alt: { type: String },
        title: { type: String },
      },
      render: "ReportImage",
    },
  },
  tags: {
    metrics: { render: "MetricGrid", children: ["tag"] },
    metric: {
      render: "Metric",
      selfClosing: true,
      attributes: {
        label: { type: String, required: true },
        value: { type: String, required: true },
        change: { type: String },
        tone: { type: String, matches: TONES, default: "positive" },
        data: { type: String },
        y: { type: String },
      },
    },
    callout: {
      render: "Callout",
      attributes: {
        type: {
          type: String,
          matches: ["note", "recommendation", "success", "warning"],
          default: "note",
        },
        title: { type: String },
      },
    },
    columns: {
      render: "Columns",
      children: ["tag"],
      attributes: { count: { type: Number } },
    },
    card: { render: "Card", attributes: { title: { type: String } } },
    badge: {
      render: "Badge",
      inline: true,
      attributes: {
        tone: { type: String, matches: [...TONES, "info"], default: "neutral" },
      },
    },
    chart: {
      render: "ReportChart",
      selfClosing: true,
      attributes: {
        ...dataTag,
        type: {
          type: String,
          required: true,
          matches: ["bar", "line", "area", "donut"],
        },
        x: { type: String, required: true },
        y: { type: Array, required: true },
        stacked: { type: Boolean },
        format: { type: String, matches: FORMATS },
      },
    },
    "bar-list": {
      render: "BarList",
      selfClosing: true,
      attributes: {
        ...dataTag,
        label: { type: String, required: true },
        value: { type: String, required: true },
        format: { type: String, matches: FORMATS },
        max: { type: Number },
      },
    },
    heatmap: {
      render: "Heatmap",
      selfClosing: true,
      attributes: {
        ...dataTag,
        row: { type: String, required: true },
        column: { type: String, required: true },
        value: { type: String, required: true },
      },
    },
    "data-table": {
      render: "DataTable",
      selfClosing: true,
      attributes: {
        ...dataTag,
        columns: { type: Array },
        limit: { type: Number },
      },
    },
    comparison: {
      render: "Comparison",
      children: ["tag"],
      attributes: {
        title: { type: String },
        verdict: { type: String, matches: ["better", "same", "worse"] },
      },
    },
    side: { render: "Side", attributes: { title: { type: String } } },
    facts: { render: "Facts", children: ["tag"] },
    fact: {
      render: "Fact",
      selfClosing: true,
      attributes: {
        label: { type: String, required: true },
        value: { type: String, required: true },
      },
    },
    timeline: { render: "Timeline", children: ["tag"] },
    event: {
      render: "TimelineEvent",
      attributes: {
        title: { type: String, required: true },
        date: { type: String },
      },
    },
    details: {
      render: "Details",
      attributes: { summary: { type: String, required: true } },
    },
    tabs: { render: "Tabs", children: ["tag"] },
    tab: {
      render: "Tab",
      attributes: { title: { type: String, required: true } },
    },
    "eval-summary": evalTag("EvalSummary", { by: { type: String } }),
    "eval-breakdown": evalTag("EvalBreakdown", { by: { type: String } }),
    "eval-head-to-head": evalTag("EvalHeadToHead", { by: { type: String } }),
    "eval-case-grid": evalTag("EvalCaseGrid", { by: { type: String } }),
    "eval-examples": evalTag("EvalExamples", {
      where: { type: String, matches: ["better", "worse"], default: "better" },
      limit: { type: Number },
    }),
    "eval-cases": evalTag("EvalCases"),
  },
};

export type ParsedReport = {
  content: RenderableTreeNode;
  errors: ValidateError[];
  headings: { id: string; title: string }[];
  dataFiles: string[];
  evalFiles: string[];
  title: string | undefined;
};

export const parseReport = (source: string): ParsedReport => {
  const ast = Markdoc.parse(source);
  const nodes = [...ast.walk()];
  const errors = Markdoc.validate(ast, reportConfig).filter(
    (error) => error.error.level !== "debug",
  );
  const frontmatter = /^title:\s*(.+)$/m.exec(
    String(ast.attributes.frontmatter ?? ""),
  );

  for (const node of nodes) {
    const definition =
      node.type === "tag"
        ? reportConfig.tags?.[node.tag ?? ""]
        : reportConfig.nodes?.[node.type];
    for (const [name, attribute] of Object.entries(
      definition?.attributes ?? {},
    )) {
      const value = node.attributes[name];
      if (value === undefined) continue;

      const type = attribute.type;
      const validType =
        type === String
          ? typeof value === "string"
          : type === Number
            ? typeof value === "number" && Number.isFinite(value)
            : type === Boolean
              ? typeof value === "boolean"
              : type === Array
                ? Array.isArray(value)
                : true;
      const validChoice =
        !Array.isArray(attribute.matches) || attribute.matches.includes(value);
      if (!validType || !validChoice) {
        if (attribute.default === undefined) delete node.attributes[name];
        else node.attributes[name] = attribute.default;
      }
    }
  }

  const usedIds = new Set<string>();
  for (const node of nodes.filter((node) => node.type === "heading")) {
    const base = headingId(textOf(node)) || "section";
    let id = base;
    for (let suffix = 2; usedIds.has(id); suffix++) id = `${base}-${suffix}`;
    usedIds.add(id);
    node.attributes.id = id;
  }

  return {
    content: Markdoc.transform(ast, reportConfig),
    errors,
    headings: nodes
      .filter((node) => node.type === "heading" && node.attributes.level === 2)
      .map((node) => ({ id: String(node.attributes.id), title: textOf(node) })),
    dataFiles: [
      ...new Set(
        nodes
          .filter(
            (node) =>
              node.type === "tag" && typeof node.attributes.data === "string",
          )
          .map((node) => String(node.attributes.data)),
      ),
    ],
    evalFiles: [
      ...new Set(
        nodes
          .filter(
            (node) =>
              node.type === "tag" && typeof node.attributes.eval === "string",
          )
          .map((node) => String(node.attributes.eval)),
      ),
    ],
    title: frontmatter?.[1]?.trim().replace(/^["']|["']$/g, ""),
  };
};
