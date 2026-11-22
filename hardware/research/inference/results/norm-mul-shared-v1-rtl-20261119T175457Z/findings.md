# Shared five-clock normalisation multiplier in RTL

The shared multiplier matched the three dedicated Experiment 20 multipliers on all seven frozen model replays. Both arms had the same first-output, last-output and completion counters. The checks covered **219,096 exact 128-bit magnitude products, 68,736 normalisation outputs, 103,360 autonomous scores and 4,480 legacy BOS scores** across 716 positions. Cache traffic and contents, feed-forward and attention arithmetic, output bytes and stop reasons also matched. [Dedicated control](../norm-mul-dsp-v1-rtl-20261119T175201Z/findings.md)

| Request | Positions | First useful output, clocks | Last useful output, clocks | Completion, clocks |
| --- | ---: | ---: | ---: | ---: |
| Hello | 101 | 329,533 | 4,077,439 | 4,129,132 |
| Six bytes | 135 | 391,907 | 5,950,820 | 6,009,805 |
| 48 bytes | 201 | 3,780,951 | 10,143,776 | 10,216,819 |
| BOS only | 1 | — | — | 30,443 |
| Hello, cap 0 | 11 | — | — | 329,533 |
| Hello, cap 1 | 11 | 329,533 | 329,533 | 329,533 |
| Full 256-position context | 256 | — | — | 14,307,892 |

Each normalisation instance completed 102 multiplies per position. The transformer starts them in separate phases and accepts the last coordinate before advancing. Every multiplier request was granted on the original first edge, with the same owner accepting the result on the fifth edge. The replay observed zero simultaneous requests and zero added handoff clocks. An independent comparison matched the recorded Experiment 20 operands and raw products, normalisation outputs and all request counters.

The directed bench checked 396 signed products, including overflow and signed-minimum cases, in 132 simultaneous three-client batches. It held a response in the shared unit for four clocks while another requester waited, then checked both results. Reset cancelled the pending work before grant and at each of the four registered datapath stages. Each cancellation was followed by a successful fresh request. The first local test attempts exposed two testbench issues, a missing compile define in the full replay and an assertion that inspected an idle client’s retained error bit. The final directed and full-model qualification passed with the same pinned shared RTL.

The two variants retain the same five calculation clocks. The candidate shares the unsigned magnitude datapath and leaves the three normalisation controllers and scalar state separate. The nominal arithmetic falls from 48 to 16 DSPs across these multipliers, a saving of 32. The operand selection and shared product return introduce routing and control overhead. The timing and resource report will show whether that overhead fits at 50 MHz. A matched physical comparison will measure module power and energy even when the request counters match.

[Run record](run.json) · [Implementation and proof](../../implementations/kv260/variants/norm-mul-shared-v1/README.md) · [Protocol](../../experiments/kv260-norm-mul-shared-v1.md)
