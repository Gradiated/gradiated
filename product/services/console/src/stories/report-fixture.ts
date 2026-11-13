export const sampleReport = `---
title: Refund and billing routing, round two
---

{% metrics %}
{% metric label="Win rate vs current" value="72%" change="+14 pts vs v1" /%}
{% metric label="Cost per 1k requests" value="$0.30" change="2.0× cheaper" /%}
{% metric label="Median latency" value="410 ms" change="1.8× faster" /%}
{% metric label="Training examples" value="4,812" change="+1,900 vs v1" /%}
{% /metrics %}

{% callout type="recommendation" %}
Promote this version for all traffic. It routes refunds and billing tickets far more accurately than v1 and costs half as much as your current model. Shipping questions are slightly worse; we are collecting more examples for the next version.
{% /callout %}

## What changed

We trained on 4,812 resolved tickets captured between 1 Sep and 25 Oct, removing duplicates and anything with customer contact details. Compared with v1 we added 1,900 refund and billing examples and rebalanced shipping questions.

{% columns %}
{% card title="Improved" %}
- Refunds routed correctly 84% of the time
- Duplicate-charge tickets flagged as high priority
{% /card %}
{% card title="Regressed" %}
- Address changes sometimes sent to Account
- Shipping win rate 47%, down from 53%
{% /card %}
{% /columns %}

## Results

{% chart type="bar" data="win-rate.csv" x="category" y=["win_rate"] title="Win rate by category" caption="Against your current model · 600 held-out tickets" /%}

## Training

{% chart type="line" data="metrics.csv" x="step" y=["train_loss", "eval_loss"] title="Training loss" caption="We used the checkpoint at step 900" /%}

## Examples

{% data-table data="eval-samples.csv" columns=["ticket", "current_model", "this_version", "verdict"] title="Head-to-head examples" limit=5 /%}

## Next steps

1. Promote this version to production.
2. Share 300 or more shipping tickets so the next version can close the remaining gap.
`;

export const sampleReportData: Record<string, string> = {
  "win-rate.csv": `category,win_rate
Refunds,84
Billing,79
Account access,71
Product questions,66
Shipping,47
`,
  "metrics.csv": `step,train_loss,eval_loss
0,2.41,2.38
100,1.92,1.95
200,1.61,1.66
300,1.42,1.49
400,1.29,1.38
500,1.20,1.31
600,1.13,1.27
700,1.08,1.24
800,1.04,1.22
900,1.01,1.21
1000,0.98,1.21
1100,0.96,1.22
1200,0.94,1.22
`,
  "eval-samples.csv": `ticket,current_model,this_version,verdict
Charged twice for my October invoice,route: general,route: billing (high),Better
Where do I change my delivery address?,route: shipping,route: account,Worse
Refund still not received after 10 days,route: refunds,route: refunds (high),Better
"Card declined, but money left my account",route: general,route: billing,Better
Can I return an opened item?,route: refunds,route: refunds,Same
Package marked delivered but not here,route: shipping,route: shipping,Same
`,
};

export const everyBlockReport = `---
title: Every report block
---

{% metrics %}
{% metric label="Win rate vs current" value="72%" change="+14 pts vs v1" data="win-trend.csv" y="win_rate" /%}
{% metric label="Cost per 1k requests" value="$0.30" change="2.0× cheaper" /%}
{% metric label="Median latency" value="410 ms" change="+40 ms vs v1" tone="negative" /%}
{% metric label="Training examples" value="4,812" change="Unchanged" tone="neutral" /%}
{% /metrics %}

{% callout type="recommendation" %}
Promote this version. Recommendations explain what we suggest and why.
{% /callout %}

{% callout type="success" title="Ready for production" %}
Success callouts highlight a result worth celebrating.
{% /callout %}

{% callout type="warning" %}
Warnings flag a risk, such as the shipping regression below.
{% /callout %}

{% callout %}
Notes hold neutral context. Inline badges work in prose: {% badge tone="positive" %}Better{% /badge %} {% badge tone="negative" %}Worse{% /badge %} {% badge tone="info" %}New{% /badge %} {% badge %}Same{% /badge %}.
{% /callout %}

## Charts

{% chart type="bar" data="win-rate.csv" x="category" y=["win_rate"] format="percent" title="Bar chart" caption="One series" /%}

{% chart type="bar" data="verdicts.csv" x="category" y=["better", "same", "worse"] stacked=true title="Stacked bar chart" caption="Verdicts per category" /%}

{% chart type="line" data="metrics.csv" x="step" y=["train_loss", "eval_loss"] title="Line chart" caption="Two series with a legend" /%}

{% chart type="area" data="latency.csv" x="day" y=["p50", "p95"] title="Area chart" caption="Latency in ms" /%}

{% columns %}
{% chart type="donut" data="sources.csv" x="source" y=["examples"] title="Donut chart" caption="Training data by source" /%}
{% bar-list data="win-rate.csv" label="category" value="win_rate" format="percent" title="Bar list" caption="Ranked breakdown" /%}
{% /columns %}

{% heatmap data="confusion.csv" row="expected" column="predicted" value="count" title="Heatmap" caption="Expected vs predicted route" /%}

## Tables

{% data-table data="eval-samples.csv" title="Data table" caption="First rows of a CSV" limit=4 /%}

## Comparisons

{% comparison title="Charged twice for my October invoice" verdict="better" %}
{% side title="Current model" %}
\`route: general\`
{% /side %}
{% side title="This version" %}
\`route: billing · priority: high\`
{% /side %}
{% /comparison %}

{% comparison title="Where do I change my delivery address?" verdict="worse" %}
{% side title="Current model" %}
Sent to Shipping, which handles address changes.
{% /side %}
{% side title="This version" %}
Sent to Account, which can't change an order's address.
{% /side %}
{% /comparison %}

## Layout

{% columns count=3 %}
{% card title="Data" %}
4,812 resolved tickets from 1 Sep to 25 Oct.
{% /card %}
{% card title="Training" %}
Rank 16 LoRA, 1,200 steps, checkpoint at step 900.
{% /card %}
{% card title="Evaluation" %}
600 held-out tickets judged against your current model.
{% /card %}
{% /columns %}

{% tabs %}
{% tab title="Refunds" %}
Refunds improved the most: 84% win rate.
{% /tab %}
{% tab title="Shipping" %}
Shipping regressed slightly: 47% win rate.
{% /tab %}
{% /tabs %}

{% facts %}
{% fact label="Base model" value="Qwen3 8B" /%}
{% fact label="LoRA rank" value="16" /%}
{% fact label="Learning rate" value="2e-4" /%}
{% fact label="Epochs" value="3" /%}
{% /facts %}

{% timeline %}
{% event date="12 Sep" title="Pilot (v0)" %}
First routing model on 900 tickets.
{% /event %}
{% event date="2 Oct" title="v1 in production" %}
Added account and billing tickets.
{% /event %}
{% event date="3 Nov" title="v2 delivered" %}
Refund and billing improvements.
{% /event %}
{% /timeline %}

{% details summary="Training settings" %}
Collapsible details hold reference material most readers skip.

\`\`\`json
{ "rank": 16, "alpha": 32, "learning_rate": 0.0002, "epochs": 3 }
\`\`\`
{% /details %}

## Text

Paragraphs support **bold**, *italic*, \`inline code\` and [links](https://huggingface.co/docs/peft).

- Bulleted lists
- With several items

1. Numbered lists
2. For steps

> Quotes for customer feedback or a key finding.

\`\`\`bash
vllm serve Qwen/Qwen3-8B --enable-lora --lora-modules support-triage-v2=./support-triage-v2
\`\`\`

{% data-table data="missing.csv" title="Missing data" caption="Shows a quiet placeholder" /%}
`;

export const everyBlockReportData: Record<string, string> = {
  ...sampleReportData,
  "win-trend.csv": `version,win_rate
v0,41
v1,58
v2,72
`,
  "verdicts.csv": `category,better,same,worse
Refunds,84,10,6
Billing,79,12,9
Account access,71,17,12
Product questions,66,20,14
Shipping,47,21,32
`,
  "latency.csv": `day,p50,p95
Mon,402,880
Tue,398,860
Wed,410,905
Thu,415,940
Fri,407,890
Sat,395,820
Sun,401,850
`,
  "sources.csv": `source,examples
Captured traces,2935
Labelled tickets,1299
Synthetic edge cases,578
`,
  "confusion.csv": `expected,predicted,count
Billing,Billing,118
Billing,Refunds,9
Billing,Shipping,3
Refunds,Billing,7
Refunds,Refunds,131
Refunds,Shipping,2
Shipping,Billing,4
Shipping,Refunds,6
Shipping,Shipping,96
`,
};
