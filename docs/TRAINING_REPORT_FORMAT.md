# Training report format

Each delivered task version can carry a `report.md` training report plus the data
files it references. Staff attach them from the version page (Files › Add files);
customers read the report on that page and download every file. Files are stored as
version files (see [DATA_MODEL.md](DATA_MODEL.md#version-files)).

`report.md` is [Markdoc](https://markdoc.dev): Markdown plus the tags below. The
console renders tags with its own components, so reports always match the product.
Reports cannot run code or raw HTML. Staff see validation problems above the report;
customers never do. The Storybook story *Pages › Training › Blocks › Training report ›
Every block* renders every tag, and `services/console/src/stories/report-fixture.ts`
holds its source.

## Front matter

```markdown
---
title: Refund and billing routing, round two
---
```

`title` appears under the version name.

## Markdown

Headings, paragraphs, bold, italic, inline code, lists, quotes, fenced code, horizontal
rules and links (`https://` links open in a new tab). Level-2 headings (`##`) become the
page's "On this page" contents. Images reference an attached file by name:
`![Loss curve](loss.png)`.

## Data files

Charts and tables read an attached `.csv` (header row required), `.json` (array of
objects) or `.jsonl` file of at most 2 MiB, referenced by its file name. A missing or
unreadable file shows a quiet placeholder instead of the block.

## Tags

| Tag | Use | Attributes |
| --- | --- | --- |
| `{% metrics %}` with `{% metric /%}` | Headline numbers | `label`, `value` (required); `change`; `tone` = `positive` (default), `negative`, `neutral`; optional sparkline from `data` + `y` |
| `{% callout %}` | Recommendation or context | `type` = `note` (default), `recommendation`, `success`, `warning`; `title` |
| `{% columns %}` with `{% card %}` | Side-by-side cards | columns: `count` = 2 (default), 3, 4; card: `title` |
| `{% badge %}` | Inline status in prose | `tone` = `neutral` (default), `positive`, `negative`, `info` |
| `{% chart /%}` | Bar, line, area or donut chart | `type`, `data`, `x`, `y` (list, e.g. `y=["train_loss","eval_loss"]`) required; `stacked=true`; `format` = `number`, `percent`, `usd`; `title`, `caption` |
| `{% bar-list /%}` | Ranked breakdown | `data`, `label`, `value` required; `format`; `max`; `title`, `caption` |
| `{% heatmap /%}` | Confusion matrix or grid | `data`, `row`, `column`, `value` required; `title`, `caption` |
| `{% data-table /%}` | Rows from a file | `data` required; `columns` (list); `limit` (default 50); `title`, `caption` |
| `{% comparison %}` with `{% side %}` | Two outputs for one input | comparison: `title`, `verdict` = `better`, `same`, `worse`; side: `title` |
| `{% facts %}` with `{% fact /%}` | Label and value pairs | `label`, `value` required |
| `{% timeline %}` with `{% event %}` | Dated history | `title` required; `date` |
| `{% details %}` | Collapsed reference material | `summary` required |
| `{% tabs %}` with `{% tab %}` | Alternative views | `title` required |

Example:

```markdown
{% chart type="line" data="metrics.csv" x="step" y=["train_loss", "eval_loss"] title="Training loss" /%}
```
