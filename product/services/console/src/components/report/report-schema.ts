import Markdoc, {
  type Config,
  type Node,
  type RenderableTreeNode,
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
          { level, id: headingId(textOf(node)) },
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
  },
};

export type ParsedReport = {
  content: RenderableTreeNode;
  errors: ValidateError[];
  headings: { id: string; title: string }[];
  dataFiles: string[];
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

  return {
    content: Markdoc.transform(ast, reportConfig),
    errors,
    headings: nodes
      .filter((node) => node.type === "heading" && node.attributes.level === 2)
      .map((node) => ({ id: headingId(textOf(node)), title: textOf(node) })),
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
    title: frontmatter?.[1]?.trim().replace(/^["']|["']$/g, ""),
  };
};
