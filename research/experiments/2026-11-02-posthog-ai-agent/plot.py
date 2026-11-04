"""Rebuild aggregate figures: uv run --with matplotlib python <this-file>."""
from pathlib import Path
import csv
import json
import statistics

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
FIG = ROOT / 'figures'
FIG.mkdir(exist_ok=True)
snapshot = json.loads((DATA / 'snapshot.json').read_text())
deepseek_path = DATA / 'deepseek_result.json'
deepseek = json.loads(deepseek_path.read_text()) if deepseek_path.exists() else None
local_path = DATA / 'deepseek_local_result.json'
local_deepseek = json.loads(local_path.read_text()) if local_path.exists() else None
plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False,
                     'svg.hashsalt': 'posthog-ai-agent', 'svg.fonttype': 'none'})


def save(fig, name):
    fig.savefig(FIG / (name + '.svg'), bbox_inches='tight', metadata={'Date': None})
    svg = FIG / (name + '.svg')
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines()) + '\n')
    fig.savefig(FIG / (name + '.png'), dpi=160, bbox_inches='tight')
    plt.close(fig)


with (DATA / 'sft_loss.csv').open() as f:
    loss = [{k: float(v) for k, v in row.items()} for row in csv.DictReader(f)]
fig, ax = plt.subplots(figsize=(10, 4.6), layout='constrained')
for epoch in [1, 2, 3]:
    rows = [r for r in loss if int(r['epoch']) == epoch]
    x = [r['training_minutes'] for r in rows]
    y = [r['loss'] for r in rows]
    smooth = [statistics.mean(y[max(0, i - 4):i + 1]) for i in range(len(y))]
    ax.plot(x, y, color='#90b6e5', marker='.', lw=1, label='Logged minibatch loss' if epoch == 1 else None)
    ax.plot(x, smooth, color='#2166c5', lw=2, label='5-step trailing mean' if epoch == 1 else None)
    if epoch < 3:
        ax.axvline(x[-1], color='#999', ls='--', lw=.8)
    ax.text((x[0] + x[-1]) / 2, .322, f'Epoch {epoch}', ha='center', color='#667085')
ax.set(title='SFT training loss: three epochs, 72 optimizer steps', xlabel='Cumulative training minutes (pause and loading excluded)', ylabel='Logged training loss', ylim=(.14, .33), xlim=(0, 160))
ax.grid(alpha=.18)
ax.legend(frameon=False, loc='lower left')
save(fig, 'sft-loss')

mapping = [
    ('Base Qwen', 'qwen', 'qwen'),
    ('SFT: 1 epoch', 'qwen-hilltrain3-am-sft-e84-v1', 'qwen-hilltrain3-am-sft-e84-v1'),
    ('OPD: procedure', 'qwen-hilltrain3-am-opd-procedure-e84-v1', 'qwen-hilltrain3-am-opd-procedure-e84-v1'),
    ('OPD: contract', 'qwen-hilltrain3-am-opd-contract-e84-v1', 'qwen-hilltrain3-am-opd-contract-e84-v1'),
    ('Fresh Sol', None, None),
]
if deepseek:
    mapping.insert(-1, ('DeepSeek 1017 (OpenRouter)', None, None))
if local_deepseek:
    mapping.insert(-1, ('DeepSeek 1017 (local)', None, None))
evaluation_rows = []
primary = []
secondary = []
for label, key, secondary_key in mapping:
    if key:
        p = snapshot['morning']['primary_metrics'][key]['passed']
        s = snapshot['judge_agreement']['arms'][secondary_key]['secondary_passes']
        run = 'morning'
    else:
        if label == 'DeepSeek 1017 (local)':
            reference = local_deepseek['metrics']['deepseek-v41-flash-1017-local']
            run = 'deepseek_local_v3'
        elif label == 'DeepSeek 1017 (OpenRouter)':
            reference = deepseek['metrics']
            run = 'deepseek_repaired_v2'
        else:
            reference = snapshot['fresh_sol']['metrics']
            run = 'fresh_sol_followup'
        p = reference['primary']['passed']
        s = reference['secondary_terra']['passed']
    primary.append(p)
    secondary.append(s)
    for judge, count in [('Sol v3i', p), ('Terra v3i', s)]:
        evaluation_rows.append({'run': run, 'model': label, 'split': 'frozen_final', 'judge': judge, 'passed': count, 'judged': 24, 'planned': 24, 'samples_per_task': 1})
with (DATA / 'evaluation_results.csv').open('w') as f:
    w = csv.DictWriter(f, fieldnames=list(evaluation_rows[0]), lineterminator='\n')
    w.writeheader()
    w.writerows(evaluation_rows)
fig, ax = plt.subplots(figsize=(12, 4.8), layout='constrained')
x = list(range(len(mapping)))
for offset, counts, label, color in [(-.19, primary, 'Primary: Sol judge', '#2166c5'), (.19, secondary, 'Secondary: Terra judge', '#85b7a6')]:
    bars = ax.bar([i + offset for i in x], [p / 24 * 100 for p in counts], width=.36, label=label, color=color)
    ax.bar_label(bars, labels=[f'{p}/24' for p in counts], padding=3, fontsize=9)
ax.set(xticks=x, xticklabels=[r[0].replace(' (', '\n(') for r in mapping], ylabel='Passed tasks (%)', ylim=(0, 108), title='Same frozen 24 tasks; one rollout per task and model')
ax.legend(frameon=False, loc='upper left')
ax.yaxis.grid(alpha=.18)
ax.set_axisbelow(True)
fig.text(.5, -.025, 'Terra rejudges the same traces. Small synthetic holdout; native paths/settings differ and runs were not simultaneous. Opus and Sonnet 5.5 unavailable.', ha='center', fontsize=9, color='#667085')
save(fig, 'pass-rates')

under = snapshot['underfed_eval']
refed = snapshot.get('refed_collection')
windows = [{'label': 'Evaluation only', 'output_tps': sum(p['output_tps'] for p in under['ports'].values()), 'mean_running': sum(p['mean_running'] for p in under['ports'].values()), 'window_seconds': under['window_seconds'], 'timestamp_unix': under['at'], 'scope': 'Two dev worlds; model evaluation pinned B; A idle', 'evidence': 'host_artifact'}]
if refed:
    windows.append({'label': 'Collection + evaluation', 'output_tps': refed['fleet_tps'], 'mean_running': sum(p['mean_running'] for p in refed['ports'].values()), 'window_seconds': refed['window_s'], 'timestamp_unix': refed['at'], 'scope': '40 training/execution worlds; two TP4s; 28 collection slots plus dev', 'evidence': 'host_artifact'})
with (DATA / 'throughput_windows.csv').open('w') as f:
    w = csv.DictWriter(f, fieldnames=list(windows[0]), lineterminator='\n')
    w.writeheader()
    w.writerows(windows)
fig, ax = plt.subplots(figsize=(8.5, 4.4), layout='constrained')
bars = ax.bar([r['label'] for r in windows], [r['output_tps'] for r in windows], color=['#b3c3d6', '#2166c5'])
ax.bar_label(bars, labels=[f"{r['output_tps']:.0f} TPS\n{r['mean_running']:.1f} mean active requests" for r in windows], padding=6)
ax.set(ylabel='Fleet output tokens / second', ylim=(0, max(r['output_tps'] for r in windows) * 1.25), title='Feeding existing inference replicas with independent worlds')
ax.yaxis.grid(alpha=.18)
ax.set_axisbelow(True)
fig.text(.5, -.035, 'Observed 60s and 180s windows, different task mixes. Not a matched causal speedup or hardware ceiling.', ha='center', fontsize=9, color='#667085')
save(fig, 'throughput')

development_path = DATA / 'epoch_dev_results.json'
if development_path.exists():
    development = json.loads(development_path.read_text())
    epoch_arms = [('Base', 'qwen'), ('Epoch 1', 'qwen-hilltrain3-am-sft-e84-v1'),
                  ('Epoch 2', 'qwen-hilltrain3-sft-epoch2-e84-v1'),
                  ('Epoch 3', 'qwen-hilltrain3-sft-epoch3-e84-v1')]
    epoch_rows = [{'model': label, 'split': 'development', **development['metrics'][arm]}
                  for label, arm in epoch_arms]
    with (DATA / 'epoch_dev_results.csv').open('w') as f:
        fields = ['model', 'split', 'judged', 'planned', 'passed', 'pass_rate', 'mean_score']
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore', lineterminator='\n')
        writer.writeheader()
        writer.writerows(epoch_rows)
    fig, ax = plt.subplots(figsize=(8, 4.4), layout='constrained')
    bars = ax.bar([r['model'] for r in epoch_rows], [r['pass_rate'] * 100 for r in epoch_rows],
                  color=['#879aaf', '#b5cce8', '#7ca7d9', '#2166c5'])
    ax.bar_label(bars, labels=[f"{r['passed']}/{r['judged']}" for r in epoch_rows], padding=5)
    ax.set(title='Development evaluation after each SFT epoch', ylabel='Passed tasks (%)', ylim=(0, 100))
    ax.yaxis.grid(alpha=.18)
    ax.set_axisbelow(True)
    fig.text(.5, -.035, 'Same 18 dev tasks, one rollout per arm, Sol v3i judge. Separate from the 24-task final benchmark.',
             ha='center', fontsize=9, color='#667085')
    save(fig, 'epoch-dev-pass-rates')
print('Rebuilt aggregate figures and CSVs from saved data.')
