# twingen: synthetic PostHog projects from twin specs

Turns twin project specs (`../twins/specs/*.json`, `../twins/clusters/*.json`; see `../twins/SCHEMA.md`) into
PostHog-shaped project data. An agent trained in a synthetic PostHog environment then sees the same taxonomy, value
shapes, volumes and objects that production showed it. Everything stays on fbf8. Specs, priors and generated projects
contain anonymized production-derived names and values. Tools print aggregates only.

## Layout

| path | content |
|---|---|
| `priors_build.py` | Builds `priors/*.json` from all 4912 conversation specs (~2 s). |
| `specio.py` | Loads conversation and cluster specs into one normalized form (timezone, `now`, events, props, objects, anchors). |
| `anchors.py` | Turns anchors into volume hints, funnel shapes and retention curves. Also derives the required history window. |
| `values.py` | Property value samplers: spec values first, then priors, then name-shape fallbacks. |
| `catalog.py` | Public built-in catalogs: browsers/OS/devices, countries/cities, referrers, UTM, names, AI models, exception types. |
| `gen.py` | Generator (`Project`). CLI: `gen.py SPEC OUT_DIR [--seed N] [--now ISO] [--max-events N] [--history-days N]`. |
| `run_all.py` | `targets` builds `targets.jsonl`. `run` generates in parallel and writes `projects/_run_log.jsonl`. |
| `validate.py` | Aggregate checks of a set of project dirs against their specs. |
| `tools/` | Aggregate-only probes (`shape.py`, `stats*.py`, `diag.py`, `pick.py`). |
| `projects/<id>/` | Generated projects. `<id>` is a cluster id or a conversation id. |
| `validation/` | Validation outputs: per-project JSON and summaries. |

Python: `.venv` (numpy, pyarrow, orjson, tzdata, pyflakes). To regenerate everything:
`.venv/bin/python priors_build.py && .venv/bin/python run_all.py targets targets.jsonl && .venv/bin/python run_all.py run targets.jsonl projects --workers 32`.

## Priors (`priors/`)

All priors are aggregated across specs. A string value enters a cross-project prior only if at least 3 distinct specs
show it, so no project-specific value leaks into another synthetic project.

- `std_event_props.json`: for each `$` event with property lists (`$pageview` has 680 specs), the frequency, majority type, shared values and numeric quantiles of each property.
- `custom_event_dollar_props.json`: `$` props that ride on custom events.
- `dollar_props_any.json`: values for any `$` property, across events and unscoped use.
- `custom_props_common.json`: custom property names on custom events seen in 15 or more projects, with type and values. Also the number of props per custom event.
- `name_shape_priors.json`: property name shapes (`*_id`, `*_count`, `*_at`, `is_*`, email, url, money, duration, category, path, ...) mapped to a type histogram, numeric quantiles and value-class mix (uuid/int/slug/prefixed id/text). Event and person props are kept separate.
- `person_props.json`, `session_props.json`, `group_props.json`: frequency, types and values.
- `volume.json`: per-event daily totals and DAU, total/DAU ratio, `$` event volume relative to `$pageview`, custom event volume relative to `$pageview`, project DAU and daily total (linear and log10 quantiles), active events per project, required history window, and active/inactive shares.
- `funnel_retention.json`: step-to-step funnel conversion by step index (from 1480 anchor steps), median conversion time, and mean day/week/month retention curves from retention anchors.
- `project.json`: default `now` (median spec time), generic custom event names (20 or more specs, 3 or more timezone families) and object counts.
- `warehouse.json`: field type histogram, overall and by field name.

## Generation model (`gen.py`)

1. **Normalize** (`specio`): drop `failed_only` events. Split events into active and inactive (`not_seen_days` set). Take `now` from the spec's latest `current_time_utc`, or the prior median if the spec has none. Map the timezone family to IANA (`IST+330` maps to `Asia/Kolkata`, `-03(-180)` to `America/Sao_Paulo`, and so on; the fallback is `Etc/GMT±N`). Clusters use the majority observed timezone and the merged sections.
2. **Event set.** Use the spec's active events. A spec with no active events becomes a default web (or mobile) product: `$pageview`, `$pageleave`, `$autocapture`, `$identify`, `$web_vitals`, `$rageclick`, `$exception`, plus 3 to 8 generic custom events sampled from the prior. A spec whose events come only from SQL references (no taxonomy listing) gets `$pageleave`, `$autocapture` and `$identify` added. Error tracking issues imply `$exception`. Every invented event is flagged `invented` in `definitions.json`.
3. **Volumes.** Hints come from event `volume` (Trends attributions), `sql_events_timeseries` with a single event, and `sql_events_breakdown` by event with a parsed `INTERVAL`. Filtered series count only as lower bounds. Project DAU is the maximum of the event DAUs and `all_events_day_dau`, or it is inferred from totals. With no anchor, DAU is sampled from the prior log-DAU distribution and clamped to 3..20000. Unanchored events are sized by priors: `$` events relative to `$pageview` (for example `$autocapture` is about 3x pageviews), with typical DAU fractions (`$identify` at most about 5% of DAU, `$exception` about 4%). Unanchored custom events are sized relative to the project's anchored custom events, or relative to `$pageview` from the prior.
4. **History and cap.** The default history is 90 days. It extends up to 365 days when anchors or insights use longer ranges (`-6m`, `-180d`, `-12m`). If the projected events exceed `--max-events` (default 5M), history first shrinks toward 35 days. If that is not enough, all volumes are scaled by `volume_scale`, which `manifest.json` records.
5. **Persons and activity.** New persons arrive by a Poisson process with mild growth over the history plus 120 pre-history days. Each person has a lognormal activity intensity. The chance of being active on day k after first seen follows the prior day-retention curve (day1 about 0.20, day7 about 0.10, then a power-law tail), times a per-project stickiness factor and a weekend factor. The arrival rate is solved so that mean DAU over the last 30 days matches the target. Persons with no activity in the window are dropped.
6. **Events per user-day.** Each event has a nested reach threshold on a latent per-person engagement u. A person who reaches a rarer event also reaches the more common ones, so funnels convert plausibly. Each event also has a per-day probability and an overdispersed count (gamma-Poisson). Funnel steps from anchors and insights keep reach non-increasing along the steps and are ordered within sessions. `$identify` fires on the first day of identified new persons, plus re-identifies at the target rate. Every active spec event is guaranteed at least 1 to 3 occurrences.
7. **Sessions and time.** A user-day has 1 to 6 sessions (more when busier), and pageviews are spread round-robin so each session holds one. Start times follow a diurnal profile in the project timezone. Events within a session are ordered by funnel rank, with lognormal gaps (median 12 s). `$session_id` and `$window_id` are UUIDv7. Nothing is later than `now`.
8. **Properties.** Precedence is: spec values for that event and prop, then priors, then name shape. Spec values get Zipf weights, plus a synthetic tail of the same value class when the taxonomy says "and N more". A forcing schedule emits every spec value at least once early in the history.
   - Context `$` props on every client-side event are coherent per person: device, OS, browser, screen, geo by country or city (tilted toward the project timezone), language and lib. The set comes from the spec's `$pageview` property list when it has one, or from the prior otherwise. Spec values override the coherent profile 85% of the time.
   - Page props (`$current_url`, `$host`, `$pathname`, `$referrer`, `$referring_domain`, `$search_engine`, UTM on the first pageview of a session) come from the spec's hosts, URLs, paths and referrers. Agent filter fragments become concrete paths.
   - Structural props: `$prev_pageview_*`, `$autocapture` `$event_type`/`$el_text`, `$web_vitals_*_value`, `$feature_flag`/`$feature_flag_response`/`$feature/<key>` (from flags and experiments, with sticky variants per person), `$exception_*` with `$exception_list`, tied to the spec's error tracking issue ids and titles, `$ai_*` (model, provider, tokens, cost, latency, with a trace id per session), `$survey_*`, `$set`, `$groups`.
   - Custom events without property lists get the unscoped props that share a name token or belong to the top custom events, plus 0 to 3 common custom props from the prior. Props referring to the person (`*user_id`, email) take the person's values, so warehouse and person joins work.
   - Server-like custom events (spec props without any web context) and `$ai_*` events carry only `$lib` context.
9. **Persons.** Each person has an anonymous UUIDv7 distinct id and, if identified, a user id. The id style per project is uuid, int, email or prefixed. Person props use the spec's person property list (or the prior's common `$` set, plus email and name): `$initial_*` from the first page and referrer, geo and device from the profile, email and name synthetic (the email domain mix comes from spec domains), plan, datetimes near creation, and spec values elsewhere.
10. **Groups.** Created when the spec has group types or indices. Group type names come from the spec when they are named, and otherwise from organization/company/project/workspace/team. Each person belongs to one group per type, with Zipf group sizes. Group props come from the spec or the prior, and every group has a `name`.
11. **Inactive events** (`not seen in N days`) are in definitions with `last_seen_at = now - N`. Custom and agent-referenced ones also get 1 to 40 legacy events before that date. Built-in taxonomy-only `$` events (`$mcp_*`, `$conversation_*`, ...) are definitions only.
12. **Objects.** Insights, dashboards (with tiles matched by name), flags (filters and variants), experiments, cohorts (with an invented simple person-property filter), actions (one step on the best name-matching event), surveys (with invented question text by type), error tracking issues, notebooks and rare kinds are written as stubs. Objects created in the conversation (`created_in_conversation`, or `first_source` of `created_by_agent`/`upsert_dashboard`) are excluded and counted. Edited insights are kept and flagged `edited_in_conversation`. Insight stubs get a valid `InsightVizNode`/`DataVisualizationNode` query built from the spec's query summary.
13. **Warehouse.** Each table takes its spec fields. `lazy_table` fields become `joins`. A table without fields gets columns inferred from `alias.column` use in spec SQL, or from table-name heuristics (payments, users, products). Rows number 200 to 3000; user-like tables scale with persons. Email, user id and person id columns reuse generated persons so joins resolve.

## Output format (`projects/<id>/`)

| file | shape |
|---|---|
| `events.parquet` | `uuid, event, properties (JSON string), timestamp (us, UTC), distinct_id, person_id, $session_id, $window_id, elements_chain (""), person_properties (dictionary-encoded JSON), $group_0..$group_4`. Sorted by time, zstd, 100k-row groups. |
| `persons.parquet` | `id, created_at, properties (JSON), is_identified, version`. |
| `person_distinct_ids.parquet` | `distinct_id, person_id, version, is_deleted`. |
| `groups.parquet` | `group_type_index, group_key, group_properties (JSON), created_at` (only when the project has groups). |
| `definitions.json` | `event_definitions` (name, description, last_seen_at, invented, generated_count), `property_definitions` (name; type 1 event, 2 person, 3 group, 4 session; property_type; is_numerical; description; group_type_index; flags `virtual_or_unused` and `derived`), `event_properties` pairs, `group_type_mapping`. |
| `objects.json` | `{kind: [stub]}`. |
| `warehouse/*.parquet`, `warehouse/schema.json` | One file per table. The schema has columns, joins, `columns_inferred` and rows. |
| `manifest.json` | Spec id, kind, members, split, seed, now, timezone, history, volume_scale, DAU target and realized DAU, platform, counts, per-event targets, notes and timing. |

Session-level fields are not written, because ClickHouse derives them. `$virt_*` properties are computed by PostHog, so
they appear only in definitions.

## Gaps and known limitations

- Most volumes are invented: only about 9% of the generated projects have any volume hint. Persons-per-DAU comes from the activity model, because only 3 specs have usable person counts.
- Funnel reach follows volumes. Anchor step conversions are not fit exactly; only the step order and non-increasing reach are enforced.
- One property context per person. There is no cross-device switching and no person property history (`person_properties` is the final state).
- `elements_chain` is empty. There are no recordings, LLM trace bodies, survey answers beyond simple values, or cohort internals beyond a stub.
- Filter-literal values (agent `icontains` fragments) count as covered when a generated value contains them.
- Projects capped by `--max-events` (22 of 1076) have `volume_scale < 1` and do not match their anchors' absolute level.

## Validation

`validate.py` runs over all 1076 generated projects (`validation/all.json`, summary in `validation/all_summary.json`).
It also covers a fixed random sample of 50 projects (`validation/sample50_ids.json`). Properties are checked on up to
4000 sampled rows per event. Volume compares generated daily totals and DAU over the last 30 days with anchor
hints × `volume_scale`. Results are aggregates only.

| check | all 1076 | sample 50 |
|---|---|---|
| active spec events present in events | 35208/35209 | 1898/1898 |
| inactive spec events defined (+ in data as legacy events) | 18078/18078 (2801 in data) | 1026/1026 |
| spec event props present on that event | 47282/52339 (90.3%) | 2400/2643 |
| ... remaining definition-only (4881 of 5057 are `$virt_*`) | 5057 | 243 |
| unscoped props present on some event | 1486/1512 | 46/47 |
| spec person props present in persons | 12983/12984 | 643/643 |
| spec property values present (non-DateTime, not result-derived) | 7487/8071 (92.8%) | 318/366 |
| volume hints within 3× (all) | 1032/1075 | 134/135 |
| volume hints within 3×, target ≥ 1/day | 782/821 (95.2%) | 125/126 |

- Volume accuracy: log10(gen/target) for targets ≥ 1/day has p5/p10/p50/p90/p95 = −0.28/−0.09/−0.00/+0.06/+0.09. 209 projects have volume hints. The 39 misses sit in 17 projects (6 of them in volume-scaled projects). Most come from conflicting hints for one event, such as a filtered SQL series and an unfiltered Trends series.
- Realized/target DAU (last 30 days) p10/p50/p90 = 0.77/1.10/1.30. Median session duration across projects is p50 205 s (p10 32 s, p90 507 s); events per session p50 10.
- The missing active event is in a hard-capped project. Value misses are mostly agent filter literals on page props and taxonomy values on rarely emitted props.
- Timing for the full run of 1076 projects with 32 workers on a shared box: 702 s wall-clock and 393M events (59 GB). Per project, p50 is 0.25–1.9 s by group. 1059/1076 finished in under 60 s. The largest (4.7M-event, high-DAU clusters with about 100k+ persons) took up to about 650 s under contention. The sample of 50: generation p50 0.2 s, p90 7.3 s, p95 17 s; events p50 16k, p90 588k.
- Output by group (events p50 / p90): clusters 134k / 4.56M; test_v2 20k / 433k; dev 18k / 624k; train singletons 18k / 674k. 22 projects hit the 5M cap and have `volume_scale < 1`.
