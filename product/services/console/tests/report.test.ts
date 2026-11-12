import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import { parseReport } from "../src/components/report/report-schema";
import { TrainingReport } from "../src/components/report/training-report";
import {
  Heatmap,
  ReportDataContext,
} from "../src/components/report/report-blocks";
import { parseReportData } from "../src/lib/report-data";

const render = (markdown: string) =>
  renderToStaticMarkup(
    createElement(
      QueryClientProvider,
      { client: new QueryClient() },
      createElement(TrainingReport, {
        report: parseReport(markdown),
        source: {
          files: [],
          queryKey: ["report-test"],
          readText: async () => "",
          downloadUrl: async () => "",
        },
      }),
    ),
  );

describe("training report rendering", () => {
  it.each([
    '{% fact label={foo: "x"} value="x" /%}',
    '{% callout title={foo: "x"} type="wrong" %}\nText\n{% /callout %}',
    '{% tabs %}\n{% tab title={foo: "x"} %}\nText\n{% /tab %}\n{% /tabs %}',
    "[link]({% $missing %})",
    "{% unknown /%}",
    '{% chart type="line" data="metrics.csv" x="step" y={foo: "x"} /%}',
  ])("renders malformed attributes safely: %s", (markdown) => {
    expect(() => render(markdown)).not.toThrow();
  });

  it("keeps validation errors for staff while falling back safely", () => {
    const source = '{% fact label={foo: "x"} value="Value" /%}';
    expect(parseReport(source).errors).not.toHaveLength(0);
    expect(render(source)).toContain("Value");
  });

  it("escapes HTML and never renders executable links or remote images", () => {
    const html = render(
      "<script>alert(1)</script>\n\n[Click](javascript:alert%281%29)\n\n![Remote](https://tracker.invalid/a.png)",
    );
    expect(html).not.toContain("<script");
    expect(html).not.toContain('href="javascript:');
    expect(html).not.toContain('src="https://tracker.invalid');
  });

  it("uses one unique anchor per repeated heading", () => {
    const report = parseReport("## Results\n\nA\n\n## Results\n\nB");
    expect(report.headings.map(({ id }) => id)).toEqual([
      "results",
      "results-2",
    ]);
    const html = render("## Results\n\nA\n\n## Results\n\nB");
    expect(html).toContain('id="results-2"');
  });
});

describe("report data", () => {
  it("discards blank records without materializing a file worth of row arrays", () => {
    expect(parseReportData("blank.csv", "\n".repeat(2 * 1024 * 1024))).toEqual(
      [],
    );
    expect(
      parseReportData("blank.jsonl", "\n".repeat(2 * 1024 * 1024)),
    ).toEqual([]);
    expect(parseReportData("data.csv", "\n \nvalue\n\n1\n \n2\n")).toEqual([
      { value: 1 },
      { value: 2 },
    ]);
  });

  it("stops at row and column limits before parsing any subsequent content", () => {
    expect(() =>
      parseReportData("data.csv", `value\n${"1\n".repeat(10001)}"unterminated`),
    ).toThrow("10,000 rows");
    expect(() =>
      parseReportData(
        "data.csv",
        `${Array.from({ length: 101 }, (_, i) => `c${i}`).join(",")}\n"unterminated`,
      ),
    ).toThrow("100 columns");
    expect(() =>
      parseReportData("data.jsonl", `${'{"value":1}\n'.repeat(10001)}{invalid`),
    ).toThrow("10,000 rows");
    expect(
      parseReportData("data.csv", `value\n${"1\n\n".repeat(10000)}`),
    ).toHaveLength(10000);
  });
  it("rejects oversized datasets and bounds heatmap dimensions", () => {
    expect(() =>
      parseReportData("data.csv", `value\n${"1\n".repeat(10001)}`),
    ).toThrow("10,000 rows");
    const rows = Array.from({ length: 51 }, (_, i) => ({
      row: String(i),
      column: String(i),
      value: i,
    }));
    const html = renderToStaticMarkup(
      createElement(
        ReportDataContext.Provider,
        { value: new Map([["data.csv", { status: "ready" as const, rows }]]) },
        createElement(Heatmap, {
          data: "data.csv",
          row: "row",
          column: "column",
          value: "value",
        }),
      ),
    );
    expect(html).toContain("This data isn’t available yet.");
    expect(html).not.toContain("<table");
  });
  it("parses quoted delimiters, newlines and escaped quotes", () => {
    expect(
      parseReportData(
        "data.csv",
        'name,value\r\n"a,b",1\r\n"line\nnext",2\r\n"say ""hi""",3',
      ),
    ).toEqual([
      { name: "a,b", value: 1 },
      { name: "line\nnext", value: 2 },
      { name: 'say "hi"', value: 3 },
    ]);
  });

  it("rejects malformed CSV instead of showing misleading measurements", () => {
    expect(() =>
      parseReportData("data.csv", 'name,value\n"unterminated,1'),
    ).toThrow();
    expect(() => parseReportData("data.csv", "name,name\na,1")).toThrow();
    expect(() => parseReportData("data.csv", "name,value\na,1,2")).toThrow();
  });

  it("parses JSON and JSONL rows and rejects non-object datasets", () => {
    expect(parseReportData("data.jsonl", '{"value":1}\n\n{"value":2}')).toEqual(
      [{ value: 1 }, { value: 2 }],
    );
    expect(() => parseReportData("data.json", "[1,2]")).toThrow(
      "array of objects",
    );
  });
});
