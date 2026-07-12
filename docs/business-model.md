# Business unit economics (v1, overnight 2026-07-12)

Assumptions: blended output-equivalent price $1.00/Mtok (~half of incumbent
list for GLM-class), serving costs from the calibrated studies with the 0.73
realization factor applied, batch-fleet duty 95% (deferrable traffic).

```
price assumption: $1.00/Mtok (about half of incumbent list)

phase                                 cost  gross margin  $/day at 50B tok/day
P1 rented on-demand + surgery        0.231          77%               38.5k
P2 hybrid reserved+spot              0.135          86%               43.2k
P3 owned GPUs (high duty)            0.105          90%               44.8k
P4 family-ASIC fleet                 0.060          94%               47.0k

seed pilot (~2 anchor customers)          5B tok/day =     22 GPUs | revenue ~$1.8M/yr
Series A scale                           50B tok/day =    221 GPUs | revenue ~$18.2M/yr
large provider                          500B tok/day =   2207 GPUs | revenue ~$182.5M/yr
ASIC break-even zone                   1000B tok/day =   4414 GPUs | revenue ~$365.0M/yr

capex gates: owned GPUs pay back vs reserved-rental in ~14-18 months at >85% duty;
ASIC NRE ($100-500M) breaks even at 2.9k-14.5k chips ~ 1T tok/day (computed earlier).
Funding logic: P1-P2 are opex-only (margin-positive from first anchor customer);
P3 capex is bankable against contracted volume; P4 is a Series B/C decision informed
by the simulator's per-family dossiers + operating traffic maps.
```

Notes
- Margins are gross serving margins; exclude R&D/staff (the auto-research
  machine is the R&D — its cost is mostly compute for healing campaigns and
  per-model analysis, both bounded and per-family amortized).
- Erosion discipline: the software edge vs best-practice decays as incumbents
  improve; the per-model surgery edge regenerates with each new model family.
  Phase margins assume the machine keeps re-earning the edge (see erosion
  scenarios, queued).
- Every phase transition is gated by a measurable milestone, not a bet:
  P2 needs achieved cache-hit + spot ops; P3 needs contracted volume;
  P4 needs ~1T tok/day and a stable model family.
