"""Detect HogQL/ClickHouse SQL that the trace anonymizer corrupted, and re-derive it where possible.

Stdlib only. No replay, no network.

How the corruption arises (root_agent/anon/anonymizer.py): NER spans that get the default "ID" kind are replaced with a
format-preserving fake (`_fpe`: same length, same lower/upper/digit class per character, every other character kept),
memoized per trace and substituted everywhere the literal occurs. When NER tags a piece of SQL code
(`e.event`, `maxIf(timestamp`, `person.properties.email AS email`), the code itself is scrambled:
`x.utiwb`, `wsrAt(nsfcrcdtj`, `kbvatj.fmbnrlymbf.owaoh FS azair`. Host-like code is rewritten to `sub1.example-2`.

The detector parses the query into roles (function, keyword, qualifier, field, bare column, alias definition) and
flags tokens that (a) do not resolve against a whitelist of HogQL keywords, functions, PostHog core tables/columns,
names defined in the same query and the optional `known` sets, and (b) look random (not in a vocabulary, low English
bigram coverage), with structural boosts (an undefined qualifier shaped like a defined alias, an all-caps token in a
keyword slot, an unknown function call). Repair uses the fact that the fake has exactly the shape of the original.

Public API:
    analyze_sql(sql, known=None) -> {corrupted, score, bad_identifiers, reasons, placeholders, ...}
    analyze_conversation(messages, known=None) -> [per SQL-bearing tool call dict]
    extract_sql_snippets(text) -> [sql]            (SQL inside free text / JSON tool results)
    known_from_spec(spec) -> known dict             (twin spec -> known sets, SQL-only evidence excluded)
    build_vocab(texts_by_doc, min_df=2) -> set      (corpus vocabulary of identifier parts)
    set_vocab(words) / load_vocab(path)             (install a corpus vocabulary for gibberish scoring)
"""
from __future__ import annotations

import difflib
import json
import re
from collections import Counter, defaultdict

# ------------------------------------------------------------------------------------------------ whitelists

KEYWORDS = set("""
select from where and or not in as on join left right inner outer full cross semi anti asof group by order having
limit offset union all with case when then else end is null like ilike between exists distinct over partition asc desc
nulls first last interval values using array tuple if any lateral settings format into table filter rows range
current row unbounded preceding following window true false cast extract date timestamp to of except intersect top
global final sample prewhere qualify recursive materialized ties fetch next only collate natural regexp glob escape
second seconds minute minutes hour hours day days week weeks month months quarter quarters year years millisecond
milliseconds microsecond microseconds nanosecond nanoseconds trailing leading both for substring position
""".split())

TYPE_NAMES = set(x.lower() for x in """
String FixedString UUID Date Date32 DateTime DateTime64 Bool Boolean Int8 Int16 Int32 Int64 Int128 Int256 UInt8 UInt16
UInt32 UInt64 UInt128 UInt256 Float32 Float64 Decimal Decimal32 Decimal64 Decimal128 Nullable Array Tuple Map
LowCardinality JSON Object Nothing IPv4 IPv6 Enum8 Enum16 Integer Int Float Double Text Varchar Char Numeric Real
Signed Unsigned BigInt SmallInt TinyInt
""".split())

_FUNCS = """
abs accurateCast accurateCastOrNull acos acosh addDays addHours addMinutes addMonths addQuarters addSeconds addWeeks
addYears addMilliseconds age aggThrow alphaTokens and any anyHeavy anyLast anyIf appendTrailingCharIfAbsent argMax
argMin array arrayAll arrayAUC arrayAvg arrayCompact arrayConcat arrayCount arrayCumSum arrayCumSumNonNegative
arrayDifference arrayDistinct arrayElement arrayEnumerate arrayEnumerateDense arrayEnumerateUniq arrayExists arrayFill
arrayFilter arrayFirst arrayFirstIndex arrayFirstOrNull arrayFlatten arrayFold arrayIntersect arrayJoin arrayLast
arrayLastIndex arrayLastOrNull arrayMap arrayMax arrayMin arrayPartialSort arrayPopBack arrayPopFront arrayProduct
arrayPushBack arrayPushFront arrayReduce arrayReduceInRanges arrayResize arrayReverse arrayReverseFill
arrayReverseSort arrayReverseSplit arrayRotateLeft arrayRotateRight arrayShiftLeft arrayShiftRight arraySlice arraySort
arraySplit arrayStringConcat arrayShuffle arraySum arrayUniq arrayWithConstant arrayZip asin asinh assumeNotNull atan
atan2 atanh avg avgWeighted bar base58Decode base58Encode base64Decode base64Encode bitAnd bitCount bitNot bitOr
bitShiftLeft bitShiftRight bitTest bitXor bitmapAnd bitmapCardinality bitmapOr blockNumber boundingRatio
categoricalInformationValue cbrt ceil ceiling char_length character_length cityHash64 coalesce concat concatWithSeparator
concatWs concat_ws contingency corr corrStable cos cosh count countDigits countEqual countMatches countSubstrings
covarPop covarSamp cramersV cumulativeSum currentDatabase current_date current_timestamp cutFragment cutQueryString
cutQueryStringAndFragment cutToFirstSignificantSubdomain cutURLParameter cutWWW date_add date_diff date_sub date_trunc
dateAdd dateDiff dateName dateSub dateTrunc dayofmonth dayofweek dayofyear decodeURLComponent decodeURLFormComponent
deltaSum deltaSumTimestamp dense_rank divide domain domainWithoutWWW dotProduct e empty encodeURLComponent endsWith
entropy equals erf exp exp10 exp2 extract extractAll extractAllGroups extractAllGroupsHorizontal
extractAllGroupsVertical extractGroups extractTextFromHTML extractURLParameter extractURLParameterNames
extractURLParameters first_value firstSignificantSubdomain flatten floor format formatDateTime formatReadableDecimalSize
formatReadableQuantity formatReadableSize formatReadableTimeDelta formatRow fromModifiedJulianDay fromUnixTimestamp
fromUnixTimestamp64Micro fromUnixTimestamp64Milli fromUnixTimestamp64Nano fragment gcd generateUUIDv4 generateUUIDv7
geoDistance greatest greater greaterOrEquals groupArray groupArrayInsertAt groupArrayMovingAvg groupArrayMovingSum
groupArraySample groupArraySorted groupBitAnd groupBitOr groupBitXor groupBitmap groupConcat groupUniqArray has
hasAll hasAny hasSubstr hasToken hasTokenCaseInsensitive hex histogram hostname ifNull ifNotFinite ilike in indexOf
initcap initcapUTF8 intDiv intDivOrZero intExp10 intExp2 isFinite isInfinite isNaN isNotNull isNull isValidJSON
isValidUTF8 JSONArrayLength JSONExtract JSONExtractArrayRaw JSONExtractBool JSONExtractFloat JSONExtractInt
JSONExtractKeys JSONExtractKeysAndValues JSONExtractKeysAndValuesRaw JSONExtractRaw JSONExtractString JSONExtractUInt
JSONHas JSONLength JSONType JSON_EXISTS JSON_QUERY JSON_VALUE kurtPop kurtSamp lag lagInFrame last_value lcase lcm
lead leadInFrame least left leftPad leftPadUTF8 leftUTF8 lengthUTF8 length less lessOrEquals lgamma like ln locate log
log10 log1p log2 lower lowerUTF8 lpad ltrim makeDate makeDateTime map mapContains mapFilter mapKeys mapValues match
max maxMap median medianExact mid min minMap minus modulo moduloOrZero monthName multiIf multiMatchAny multiply
multiSearchAny negate neighbor not notEmpty notEquals notILike notIn notLike now now64 nowInBlock nth_value ntile
nullIf or parseDateTime parseDateTime64BestEffort parseDateTime64BestEffortOrNull parseDateTimeBestEffort
parseDateTimeBestEffortOrNull parseDateTimeBestEffortOrZero parseDateTimeBestEffortUS parseDateTimeOrNull path
pathFull percent_rank percentile pi plus port position positionCaseInsensitive positionCaseInsensitiveUTF8
positionUTF8 pow power protocol quantile quantileDeterministic quantileExact quantileExactExclusive
quantileExactHigh quantileExactInclusive quantileExactLow quantileExactWeighted quantileTDigest quantileTDigestWeighted
quantileTiming quantiles quantilesExact quantilesTDigest queryString queryStringAndFragment radians rand rand64
randCanonical randomPrintableASCII randomString range rank rankCorr regionToName repeat replace replaceAll replaceOne
replaceRegexpAll replaceRegexpOne retention reverse reverseUTF8 right rightPad rightUTF8 round roundBankers roundDown
roundToExp2 row_number rowNumberInAllBlocks rpad rtrim runningAccumulate runningDifference sequenceCount
sequenceMatch sequenceNextNode sign simpleLinearRegression sin sinh sipHash64 skewPop skewSamp sleep space sparkbar
splitByAlpha splitByChar splitByNonAlpha splitByRegexp splitByString splitByWhitespace sqrt startsWith stddevPop
stddevPopStable stddevSamp stddevSampStable stochasticLinearRegression subDate substr substring substringIndex
substringUTF8 subtractDays subtractHours subtractMinutes subtractMonths subtractQuarters subtractSeconds subtractWeeks
subtractYears sum sumCount sumKahan sumMap sumWithOverflow tan tanh tgamma theilsU timeSlot timeSlots timestamp
timezone today toBool toColumnTypeName toDate toDate32 toDateOrNull toDateTime toDateTime64 toDateTimeOrNull toDayOfMonth
toDayOfWeek toDayOfYear toDecimal toFixedString toFloat toFloatOrDefault toFloatOrNull toFloatOrZero toHour toInt
toIntOrDefault toIntOrNull toIntOrZero toInterval toISOWeek toISOYear toJSONString toLastDayOfMonth toLastDayOfWeek
toLowCardinality toMinute toModifiedJulianDay toMonday toMonth toNullable toQuarter topK topKWeighted toRelativeDayNum
toRelativeHourNum toRelativeMinuteNum toRelativeMonthNum toRelativeSecondNum toRelativeWeekNum toRelativeYearNum
toSecond toStartOfDay toStartOfFifteenMinutes toStartOfFiveMinutes toStartOfHour toStartOfInterval toStartOfISOYear
toStartOfMinute toStartOfMonth toStartOfQuarter toStartOfSecond toStartOfTenMinutes toStartOfWeek toStartOfYear
toString toStringCutToZero toTimeZone toTimezone toTypeName toUnixTimestamp toUnixTimestamp64Micro
toUnixTimestamp64Milli toUnixTimestamp64Nano toUUID toUUIDOrNull toUUIDOrZero toWeek toYear toYearWeek toYYYYMM
toYYYYMMDD toYYYYMMDDhhmmss topLevelDomain transform translate trim trimBoth trimLeft trimRight trunc truncate tryBase64Decode
tuple tupleElement ucase unhex uniq uniqCombined uniqCombined64 uniqExact uniqHLL12 uniqTheta upper upperUTF8 uptime
URLHierarchy URLPathHierarchy varPop varPopStable varSamp varSampStable visibleWidth week windowFunnel xor yearweek
yesterday cast toFloat64 toInt64 toInt32 toUInt64 toUInt32 toUInt8 toInt8 toInt16 toUInt16 toFloat32 toDecimal64
toDecimal32 toDecimal128 toIntervalSecond toIntervalMinute toIntervalHour toIntervalDay toIntervalWeek toIntervalMonth
toIntervalQuarter toIntervalYear concatAssumeInjective lengthUTF8 empty notEmpty position
matchesAction sparkline hogql_lookupDomainType lookupDomainType lookupPaidSourceType lookupPaidDomainType
lookupOrganicSourceType lookupOrganicDomainType hogql_lookupPaidSourceType hogql_lookupPaidDomainType
hogql_lookupOrganicSourceType hogql_lookupOrganicDomainType isIPAddressInRange languageCodeToName getSurveyResponse
uniqueSurveySubmissionsFilter recording_button explain_csp_report convertCurrency getChannelType
groupArrayIf countIf sumIf avgIf minIf maxIf uniqIf uniqExactIf argMaxIf argMinIf anyIf quantileIf medianIf
count_distinct countDistinct approx_count_distinct percentile_cont percentile_disc string_agg array_agg listagg
datediff dateadd datetrunc datepart date_part strftime strptime to_char to_date to_timestamp coalesce nvl ifnull
len charindex isnull iif left right getdate current_time localtime localtimestamp regexp_replace regexp_extract
regexp_like regexp_matches split_part position strpos starts_with ends_with array_length unnest json_extract
json_extract_path_text jsonb_extract_path_text greatest least nullif mod div lpad rpad initcap btrim sha256 md5
SHA1 SHA224 SHA256 SHA512 sipHash128 xxHash64 murmurHash3_64 farmHash64 halfMD5 javaHash hiveHash
toStartOfNanosecond toStartOfMicrosecond toStartOfMillisecond toDayOfWeekName dateTimeToSnowflake formatDateTimeInJodaSyntax
fromUnixTimestampInJodaSyntax parseDateTimeInJodaSyntax toDateTimeOrZero toDateOrZero toUInt8OrZero toInt64OrNull
toInt64OrZero toFloat64OrNull toFloat64OrZero toUInt64OrNull toUInt64OrZero toStringOrNull ifEmpty
arrayStringConcat sumArray groupArrayDistinct uniqUpTo minArray maxArray avgArray
""".split()
FUNCTIONS = {f.lower() for f in _FUNCS}
FUNC_SUFFIXES = ("if", "array", "merge", "state", "ornull", "ordefault", "orzero", "distinct", "foreach", "resample",
                 "utf8", "caseinsensitive", "simplestate", "map", "argmin", "argmax")
FUNC_PREFIX_RE = re.compile(r"^(to|from|array|json|jsonextract|tostartof|tointerval|parse|format|is|has|group|quantile"
                            r"|uniq|arg|sum|count|min|max|avg|any|date|bit|ip|url|cut|extract|replace|split|lookup"
                            r"|hogql_|toyyyy|torelative|multi|position|match|string|run|sequence|window|map|tuple"
                            r"|base|murmur|xxhash|sip|city|farm|geo|h3|least|greatest)", re.I)

# PostHog core tables (HogQL database) and their standard columns, flattened table-agnostic.
CORE_TABLES = {
    "events", "persons", "sessions", "groups", "cohorts", "person_distinct_ids", "raw_sessions", "cohort_people",
    "static_cohort_people", "session_replay_events", "raw_session_replay_events", "log_entries", "logs", "query_log",
    "error_tracking_issues", "error_tracking_issue_fingerprint_overrides", "error_tracking_issue_fingerprints",
    "heatmaps", "app_metrics", "document_embeddings", "person_distinct_id_overrides", "raw_persons", "raw_groups",
    "raw_person_distinct_ids", "raw_cohort_people", "exchange_rate", "numbers", "system", "web_stats_daily",
    "web_bounces_daily", "preaggregation_results", "person_static_cohort", "notebooks", "survey_responses",
    "persons_revenue_analytics", "groups_revenue_analytics", "revenue_analytics", "posthog", "pdi", "poe",
    "events_summary", "data_modeling_jobs", "logs_kafka_metrics", "trace_spans", "ai_events", "web_goals", "dual",
    "person", "session", "unnest", "insights", "dashboards", "feature_flags", "experiments", "surveys", "actions",
    "annotations", "dashboard_tiles", "insight_variables", "teams", "groups_revenue", "persons_revenue",
    "revenue_analytics_charge", "revenue_analytics_customer", "revenue_analytics_product", "revenue_analytics_revenue_item",
    "revenue_analytics_subscription", "revenue_analytics_mrr", "sessions_v2", "raw_sessions_v3", "batch_exports",
    "data_warehouse_tables", "information_schema", "tables", "columns", "web_overview_daily", "web_paths_daily",
    "experiment_exposures", "person_overrides", "session_recording_events",
}
CORE_COLUMNS = set("""
uuid event properties timestamp distinct_id elements_chain created_at person_id person pdi poe team_id session
$session_id $window_id $group_0 $group_1 $group_2 $group_3 $group_4 group_0 group_1 group_2 group_3 group_4
$session_id_uuid elements_chain_href elements_chain_texts elements_chain_ids elements_chain_elements
event_person_id override_person_id event_issue_id issue_id inserted_at _timestamp _offset _partition
id is_identified is_deleted version properties_last_updated_at properties_last_operation $virt_initial_channel_type
$virt_initial_referring_domain_type $virt_revenue $virt_revenue_last_30_days $virt_email $virt_name
session_id $start_timestamp $end_timestamp $entry_current_url $end_current_url $exit_current_url $entry_pathname
$end_pathname $exit_pathname $pageview_count $autocapture_count $screen_count $session_duration $is_bounce
$channel_type $entry_referring_domain $entry_utm_source $entry_utm_medium $entry_utm_campaign $entry_utm_term
$entry_utm_content $entry_gclid $entry_fbclid $entry_gad_source $last_external_click_url $num_uniq_urls $urls
$entry_hostname $end_hostname $exit_hostname $session_type $vital_lcp $page_screen_autocapture_count_up_to
$entry_has_gclid $entry_has_fbclid $entry_mc_cid $entry_igshid $entry_ttclid $entry__kx $entry_irclid
$start_hostname $first_timestamp $last_timestamp $entry_referrer
min_timestamp max_timestamp start_timestamp end_timestamp duration urls entry_url exit_url
key index group_type_index group_key group_type group_properties cohort_id start_time end_time click_count
keypress_count mouse_activity_count active_milliseconds console_log_count console_warn_count console_error_count
first_url size event_count message_count snapshot_source all_urls retention_period_days
name description query kind result results value values count total level message instance_id log_source log_source_id
fingerprint status assignee first_seen last_seen occurrences sessions users title source library
date day week month hour minute year quarter number num
tables columns table_name column_name table_schema data_type
""".split())
ROOT_QUALIFIERS = {"person", "properties", "session", "pdi", "poe", "events", "persons", "sessions", "groups",
                   "override", "elements", "system", "posthog", "group_0", "group_1", "group_2", "group_3", "group_4",
                   "e", "p", "s", "g", "i"} | CORE_TABLES

# Common PostHog $ properties (names after the `$`), so that `$lbsri` stands out but `$pathname` does not.
STD_PROPS = set("""
current_url pathname host referrer referring_domain browser browser_version os os_version device_type device_id
screen_height screen_width viewport_height viewport_width lib lib_version insert_id time raw_user_agent
geoip_city_name geoip_country_name geoip_country_code geoip_continent_name geoip_continent_code geoip_postal_code
geoip_latitude geoip_longitude geoip_time_zone geoip_subdivision_1_name geoip_subdivision_1_code
geoip_subdivision_2_name geoip_subdivision_2_code geoip_city_confidence ip pageview_id prev_pageview_pathname
prev_pageview_duration prev_pageview_max_scroll prev_pageview_max_content prev_pageview_max_scroll_percentage
initial_referrer initial_referring_domain initial_utm_source initial_utm_medium initial_utm_campaign
initial_utm_content initial_utm_term initial_current_url initial_pathname initial_browser initial_os
initial_device_type initial_gclid initial_fbclid initial_host initial_geoip_country_code initial_geoip_country_name
initial_geoip_city_name utm_source utm_medium utm_campaign utm_content utm_term gclid fbclid msclkid
session_id window_id session_entry_url session_entry_pathname session_entry_referrer session_entry_referring_domain
session_entry_utm_source session_entry_utm_medium session_entry_utm_campaign session_entry_host
event_type el_text elements elements_chain exception_list exception_type exception_message exception_fingerprint
exception_issue_id exception_level exception_source exception_sources exception_types exception_values
exception_functions exception_handled exception_personURL feature_flag feature_flag_response feature_flag_payload
active_feature_flags feature_flag_called groups group_type group_key group_set set set_once unset survey_id
survey_name survey_response survey_questions survey_iteration survey_completed survey_submission_id
screen_name app_version app_build app_name app_namespace device_manufacturer device_model device_name network_wifi
network_carrier locale timezone timezone_offset language is_identified anon_distinct_id identified_id user_id
web_vitals_LCP_value web_vitals_FCP_value web_vitals_INP_value web_vitals_CLS_value autocapture_disabled_server_side
ai_model ai_provider ai_input_tokens ai_output_tokens ai_total_cost_usd ai_input_cost_usd ai_output_cost_usd
ai_latency ai_trace_id ai_span_id ai_parent_id ai_input ai_output ai_output_choices ai_is_error ai_error
ai_http_status ai_base_url ai_span_name ai_generation_id ai_session_id ai_tools ai_temperature ai_stream
ai_cache_read_input_tokens ai_cache_creation_input_tokens ai_input_state ai_output_state ai_feedback_text
ai_metric_name ai_metric_value ai_embedding_vector process_person_profile is_bot lib_custom_api_host
dead_click_scroll_delay_ms rage_click scroll_depth current_url_path title referrer_domain email name
sdk_debug_retry_queue_size config_defaults configured_session_timeout_ms replay_sample_rate
recording_status session_recording_start_reason sent_at entry_url
""".split())

# Small built-in vocabulary of identifier words. A corpus vocabulary (set_vocab/build_vocab) is far stronger.
_BASE_WORDS = """
a about access account accounts action actions active activated activation activity ad add added address admin ads
after age agent agg aggregate ai alert all amount analytics and anon anonymous answer api app application apps arr
array as at attempt attempts attribution auth average avg back balance base basic batch before beta billing bin blog
board body bot bounce brand browser bucket build button by cache call calls campaign cancel canceled cancelled card
cart case category change channel chart chat check checkout child churn city class clean click clicked clicks client
close closed cloud code cohort col column comment company complete completed config connect content context conversion
converted cost count counter country create created credit credits cta cur currency current customer customers cycle
daily dashboard data date day days deal default delete deleted delta demo deploy description detail device diff
direct discount display distinct doc docs domain done download downloads duration edit element email embed empty
enabled end ended engaged engagement entry env error errors event events exit experiment export external extra fail
failed failure feature features feedback field file filter final first flag flags flow form free frequency from
funnel gap goal group growth guest has hash header help high history home host hour hours id ids import in inbox info
initial input insight install installed instance integration interval invite invited invoice ip is issue item items
key keys kind label landing lang language last latest lead length level lib license limit link list live load loaded
local location log login logout low main manager max medium member members message messages meta method metric
metrics min minute mobile mode model module month monthly months msg name new next num number object old onboarding
open opened order orders org organization origin os other out output overview owner page pageview pageviews paid
param params parent partner path pathname payment pct per percent period person persons phone plan plans platform
play plugin point pos post posthog prev price pricing pro product products profile project projects prompt properties
property provider purchase qty quantity query question rank rate ratio raw read reason recent recording records ref
referral referrer referring region release remove render report request requests response result results retention
revenue role rows run runs sale sales score screen search second seconds segment select send sent seq server session
sessions setting settings setup share shown sign signup signed site size skip slug source spend src stage start
started state status step steps store sub subscription success sum summary support survey survey_id sync tab table
tag tags target task team teams term test text the theme thread tier time timestamp title to token tokens tool
top total tour track trial trigger type types ui unique unit until update updated upgrade url urls usage use used
user users utm value values variant version video view viewed views visit visitor visitors web week weekly weeks
window with workspace year yes zone utc tz ts dt dau wau mau ltv mrr pct cnt agg avg ms sec min max idx ref
""".split()
VOCAB_BUILTIN = {w.lower() for w in _BASE_WORDS} | KEYWORDS | TYPE_NAMES
_VOCAB: set[str] = set()


def set_vocab(words) -> None:
    """Install a corpus vocabulary (lower-case identifier parts) used by the gibberish score."""
    global _VOCAB
    _VOCAB = {w.lower() for w in words}


def load_vocab(path: str) -> None:
    with open(path, encoding="utf-8") as fh:
        set_vocab(json.load(fh))


# English letter bigrams that are common in identifiers; random strings hit far fewer of them.
_COMMON_BIGRAMS = set("""
th he in er an re on at en nd ti es or te of ed is it al ar st to nt ng se ha as ou io le ve co me de hi ri ro ic ne
ea ra ce li ch ll be ma si om ur ca el ta la ns di fo ho pe ec pr no ct us ac ot il tr ly nc et ut ss so rs un lo wa
ge ie wh ee wi em ad ol rt po we na ul ni ts mo ow pa im mi ai sh ir su id os iv ia am fi ci vi pl ig tu ev ld ry mp
fe bl ab gh ty op wo sa ay ex ke fr oo av ag ap gr od bo sp rd do uc bu ei ov by rm ep tt oc fa ef cu rn sc gi da yo
cr cl du ga qu ue ff ba ey ls va um pp ua up lu go ht ru ug ds lt pi rc rr eg au ck ew mu br bi pt ak pu ui rg ib tl
ny ki rk ys ob mm fu ph og ms ye ud mb ip ub oi rl gu dr hr cc tw ft wn nu af hu nn eo vo rv nf xp gn sm fl iz ok nl
my gl aw ju oa eq sy sl ps jo fy nk ks lk ze za zo yp xt ix ax dd oy ky sk sw sn ue rp gs ny lm rf ws ah oh nv nw
uf wl dl lf mn yl bs bj ja je vu dy ye mf gy ns oe hn ln dg ae hy ik aj yr
""".split())
_VOWELS = set("aeiouy")


def _parts(tok: str) -> list[str]:
    tok = tok.lstrip("$")
    out = []
    for chunk in re.split(r"[_\W\d]+", tok):
        if not chunk:
            continue
        out.extend(p for p in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+", chunk) if p)
    return [p.lower() for p in out]


def _part_gib(p: str, extra: set[str]) -> float:
    """0 (word-like) .. 1 (random-looking) for one lower-case alphabetic part."""
    if p in VOCAB_BUILTIN or p in _VOCAB or p in extra:
        return 0.0
    if len(p) <= 2:
        return 0.3
    bigr = [p[i:i + 2] for i in range(len(p) - 1)]
    cov = sum(b in _COMMON_BIGRAMS for b in bigr) / len(bigr)
    vow = sum(c in _VOWELS for c in p) / len(p)
    run = max((len(m) for m in re.findall(r"[^aeiouy]+", p)), default=0)
    s = 0.0
    s += max(0.0, 0.75 - cov) * 1.6           # low bigram coverage
    s += 0.35 if vow < 0.2 or vow > 0.75 else 0.0
    s += 0.3 if run >= 4 else 0.0
    if _VOCAB:                                 # with a corpus vocabulary, unseen longer parts are suspicious
        s += 0.35 if len(p) >= 5 else 0.15
    return min(1.0, s)


def gibberish(tok: str, extra: set[str] | None = None) -> float:
    """Max part score, weighted so one random part in a snake_case name is enough."""
    extra = extra or set()
    if tok.lower() in extra or tok.lower().lstrip("$") in extra:
        return 0.0
    ps = _parts(tok)
    if not ps:
        return 0.0
    scores = [_part_gib(p, extra) for p in ps]
    return max(scores) * (0.7 + 0.3 * (sum(1 for s in scores if s >= 0.5) / len(scores)))


# ------------------------------------------------------------------------------------------------ tokenizer

_TOKEN_RE = re.compile(r"""
  (?P<ws>\s+)
| (?P<comment>--[^\n]*|/\*.*?\*/)
| (?P<str>'(?:[^'\\]|\\.|'')*'?)
| (?P<qid>`[^`]*`|"(?:[^"\\]|\\.)*")
| (?P<ph>\{[A-Za-z_][\w.]*\})
| (?P<num>0x[0-9A-Fa-f]+|\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)
| (?P<id>[A-Za-z_$][A-Za-z0-9_$]*)
| (?P<op>->|::|>=|<=|!=|<>|==|\|\||=~|!~|[-+*/%=<>(),.;\[\]{}:?!|&^~])
| (?P<other>.)
""", re.S | re.X)


def tokenize(sql: str) -> list[tuple[str, str, int]]:
    out = []
    for m in _TOKEN_RE.finditer(sql):
        k = m.lastgroup
        if k in ("ws", "comment"):
            continue
        out.append((k, m.group(), m.start()))
    return out


def _with_gaps(sql: str, toks):
    """Tokens plus the whitespace/comments between them, so a joined string keeps the original offsets."""
    last = 0
    for k, v, pos in toks:
        if pos > last:
            yield ("ws", sql[last:pos], last)
        yield (k, v, pos)
        last = pos + len(v)
    if last < len(sql):
        yield ("ws", sql[last:], last)


def shape(tok: str) -> str:
    """The `_fpe` invariant: character class per position (a lower, A upper, 9 digit), other chars kept."""
    return "".join("a" if c.isascii() and c.islower() else "A" if c.isascii() and c.isupper() else "9" if c.isdigit()
                   else c for c in tok)


# ------------------------------------------------------------------------------------------------ placeholders

PLACEHOLDER_RES = {
    "email": re.compile(r"\buser\d+@[\w.-]+|\balex@example\.com\b", re.I),
    "domain": re.compile(r"\b(?:sub\d+\.)*example-\d+\.com\b|\bhost-\d+\b", re.I),
    "company": re.compile(r"\bExample (?:Company \d+|Org|Project)\b", re.I),
    "address": re.compile(r"\b\d+0 Example Street\b", re.I),
    "ip": re.compile(r"\b203\.0\.113\.\d+\b|\b198\.51\.100\.\d+\b|2001:db8:ffff::[0-9a-f]+", re.I),
    "user_name": re.compile(r"\bAlex Morgan\b"),
    "path": re.compile(r"/page\d+(?=[/?#'\"\s]|$)"),
}
# Value placeholders that landed in code (outside string literals): the anonymizer rewrote an identifier as a host,
# company or e-mail.
_CODE_PH_RE = re.compile(r"(?i)\b(?:sub\d+\.)*example-\d+(?:\.[a-z]+)?\b|\bexample (?:company|org|project)(?: \d+)?"
                         r"|\buser\d+@[\w.-]+|\bhost-\d+\b|\bsub\d+\.[a-z]|\b\d+0 example street\b")


def count_placeholders(text: str) -> dict:
    return {k: len(r.findall(text)) for k, r in PLACEHOLDER_RES.items() if r.search(text)}


# ------------------------------------------------------------------------------------------------ analysis

_EXPR_END = {"id", "qid", "num", "str", "ph"}
_ALIAS_STOP = KEYWORDS | {"settings", "format"}


def _known_sets(known: dict | None) -> dict:
    k = {x: set() for x in ("events", "props", "tables", "columns", "aliases", "vocab", "functions")}
    for key, val in (known or {}).items():
        if key in k and val:
            k[key] = {str(v) for v in val}
    k["lower"] = {v.lower() for key in ("props", "tables", "columns", "aliases", "functions") for v in k[key]}
    k["lower"] |= {v.lower().lstrip("$") for v in k["props"]}
    extra = set(k["vocab"])
    for key in ("events", "props", "tables", "columns"):
        for v in k[key]:
            extra.update(_parts(v))
    k["extra"] = {v.lower() for v in extra}
    return k


def _func_known(name: str, ks: dict) -> bool:
    low = name.lower()
    if low in FUNCTIONS or low in ks["lower"]:
        return True
    base = low
    for _ in range(3):
        for suf in FUNC_SUFFIXES:
            if base.endswith(suf) and base[: -len(suf)] in FUNCTIONS:
                return True
        stripped = False
        for suf in FUNC_SUFFIXES:
            if base.endswith(suf) and len(base) > len(suf) + 2:
                base, stripped = base[: -len(suf)], True
                break
        if not stripped:
            break
    return base in FUNCTIONS


def _func_wordlike(name: str, ks: dict) -> bool:
    """Unknown but plausible function (hallucinated `percentileCont`, `DATE_FORMAT`) vs scrambled `pmSzshXtvngdlmf`."""
    if FUNC_PREFIX_RE.match(name) and gibberish(name, ks["extra"]) < 0.5:
        return True
    return gibberish(name, ks["extra"]) < 0.45


def analyze_sql(sql: str, known: dict | None = None) -> dict:
    """Score one SQL string for anonymizer corruption.

    known: optional sets `events`, `props`, `tables`, `columns`, `aliases` (and `vocab`, `functions`) from the spec.
    Returns {corrupted, score, bad_identifiers, reasons, placeholders, bad (detailed list), unknown_wordlike}.
    """
    ks = _known_sets(known)
    toks = tokenize(sql or "")
    n = len(toks)
    kinds = [t[0] for t in toks]
    vals = [t[1] for t in toks]
    low = [v.lower() for v in vals]

    def nxt(i, d=1):
        j = i + d
        return vals[j] if 0 <= j < n else ""

    # ---- pass 1: names defined in this query ---------------------------------------------------------------------
    defined: set[str] = set()
    tables_used: set[str] = set()
    core_aliases: set[str] = set()   # aliases of core tables: their fields must be real columns, not query aliases
    alias_tables: dict[str, str] = {}
    qual_names: set[str] = set()     # names a qualifier may legally use: tables, table/subquery aliases, CTEs, lambdas
    for i in range(n):
        if kinds[i] != "id":
            continue
        v, lv = vals[i], low[i]
        prev = low[i - 1] if i > 0 else ""
        # CTE: name AS (
        if i + 2 < n and low[i + 1] == "as" and vals[i + 2] == "(" and prev in ("with", ",", "recursive"):
            defined.add(lv)
            qual_names.add(lv)
        # expr AS name / table AS alias
        if prev == "as" and lv not in TYPE_NAMES:
            defined.add(lv)
        # FROM/JOIN table [AS] alias
        if prev in ("from", "join"):
            j = i
            parts = [v]
            while j + 2 < n and vals[j + 1] == "." and kinds[j + 2] in ("id", "qid"):
                j += 2
                parts.append(vals[j])
            tables_used.add(".".join(p.strip('`"') for p in parts).lower())
            for p in parts:
                defined.add(p.strip('`"').lower())
                qual_names.add(p.strip('`"').lower())
            k = j + 1
            if k < n and low[k] == "as":
                k += 1
            if k < n and kinds[k] == "id" and low[k] not in _ALIAS_STOP:
                defined.add(low[k])
                qual_names.add(low[k])
                alias_tables[vals[k]] = ".".join(p.strip('`"') for p in parts).lower()
                if tables_used and parts[0].strip('`"').lower() in CORE_TABLES and len(parts) == 1:
                    core_aliases.add(low[k])
        # ) alias  after a subquery, or implicit `expr alias`
        if kinds[i] == "id" and i > 0 and (vals[i - 1] == ")" or kinds[i - 1] in ("id", "qid", "num", "str")) \
                and lv not in _ALIAS_STOP and prev not in KEYWORDS and (i + 1 >= n or vals[i + 1] in (",", ")", ";")
                                                                        or low[i + 1] in _ALIAS_STOP):
            defined.add(lv)
        # lambda params: x -> / (x, y) ->
        if nxt(i) == "->":
            defined.add(lv)
            qual_names.add(lv)
        if prev == ")" and lv not in _ALIAS_STOP:
            qual_names.add(lv)
        if prev == "as" and i >= 2 and vals[i - 2] == ")":
            qual_names.add(lv)
        if nxt(i) in (",", ")"):
            j = i
            while j + 1 < n and vals[j + 1] == "," and j + 2 < n and kinds[j + 2] == "id":
                j += 2
            if j + 2 < n and vals[j + 1] == ")" and vals[j + 2] == "->":
                defined.add(lv)
        # WINDOW w AS (
        if prev == "window":
            defined.add(lv)
        # ARRAY JOIN expr AS alias handled by AS rule
    for qid_i in range(n):
        if kinds[qid_i] == "qid" and qid_i > 0 and low[qid_i - 1] == "as":
            defined.add(vals[qid_i].strip('`"').lower())
    defined |= {a.lower() for a in ks["aliases"]}
    defined_shapes = {shape(d) for d in defined | {t.split(".")[-1] for t in tables_used}}

    from_core = any(t.split(".")[0] in CORE_TABLES or t in ks["tables"] for t in tables_used) or not tables_used
    bad: list[dict] = []
    wordlike: list[str] = []
    reasons: Counter = Counter()

    def flag(i, role, reason, weight):
        bad.append({"token": vals[i], "pos": toks[i][2], "idx": i, "role": role, "reason": reason, "w": weight})
        reasons[reason] += 1

    upper_kw = sum(1 for i in range(n) if kinds[i] == "id" and low[i] in KEYWORDS and vals[i].isupper())
    kw_shapes = {}
    for kw in KEYWORDS:
        kw_shapes.setdefault(shape(kw.upper()), set()).add(kw.upper())
        kw_shapes.setdefault(shape(kw), set()).add(kw)

    # ---- placeholders in code -------------------------------------------------------------------------------------
    ph_idx: set[int] = set()
    masked = "".join(" " * len(v) if k in ("str", "qid") else v for k, v, _ in _with_gaps(sql or "", toks))
    for m in _CODE_PH_RE.finditer(masked):
        idxs = [i for i in range(n) if m.start() <= toks[i][2] < m.end()]
        if not idxs:
            continue
        ph_idx.update(idxs)
        bad.append({"token": re.sub(r"\s+", " ", m.group()), "pos": m.start(), "idx": idxs[0], "role": "code",
                    "reason": "placeholder_in_code", "w": 1.0})
        reasons["placeholder_in_code"] += 1

    # ---- pass 2: roles --------------------------------------------------------------------------------------------
    for i in range(n):
        k, v, lv = kinds[i], vals[i], low[i]
        if k != "id" or i in ph_idx:
            continue
        prev = vals[i - 1] if i > 0 else ""
        lprev = prev.lower()
        is_field = prev == "."
        is_qual = nxt(i) == "." and i + 2 < n and kinds[i + 2] in ("id", "qid", "num")
        is_call = nxt(i) == "(" and not is_field
        if lv in defined and not is_field and not is_call:
            continue
        if lv in KEYWORDS or lv in TYPE_NAMES:
            continue
        if is_call:
            if lprev in ("from", "join") or lv in defined or lv in ("as",):
                continue  # table function or CTE
            if _func_known(v, ks):
                continue
            if lv in CORE_COLUMNS or lv in ks["lower"]:
                continue
            if _func_wordlike(v, ks):
                wordlike.append(v)
                reasons["unknown_function_wordlike"] += 1
                continue
            flag(i, "function", "unknown_function", 1.0)
            continue
        if is_field:
            # chain element: a.b(.c). Head of chain decides the context.
            j = i
            while j - 2 >= 0 and vals[j - 1] == ".":
                j -= 2
            head = low[j]
            parent = low[i - 2] if i >= 2 else ""
            if lv in CORE_COLUMNS or lv in ks["lower"] or lv.lstrip("$") in STD_PROPS:
                continue
            if lv in defined and not (i - 2 == j and head in core_aliases | CORE_TABLES):
                continue
            if lv.lower() in CORE_TABLES and parent in ("system", "posthog"):
                continue
            if head in ("system", "information_schema", "posthog") or (head in ks["lower"] and head not in ROOT_QUALIFIERS):
                # warehouse/system table path
                if gibberish(v, ks["extra"]) >= 0.75:
                    flag(i, "field", "gibberish_field", 0.8)
                continue
            if lprev == "." and parent in ("properties",) or v.startswith("$"):
                role = "property"
            else:
                role = "field"
            g = gibberish(v, ks["extra"])
            if role == "field" and i - 2 == j and any(b["idx"] == j and b["role"] == "qualifier" for b in bad) \
                    and g >= 0.25:
                flag(i, role, "field_of_undefined_alias", 0.8)
                continue
            if role == "field" and i - 2 == j and (head in core_aliases or head in CORE_TABLES - {"system", "posthog"}):
                # `e.<x>` on a core table must be a real column; HogQL cannot resolve anything else
                if g >= 0.35:
                    flag(i, role, "unknown_core_column", 1.0)
                else:
                    wordlike.append(v)
                    reasons["unknown_core_column_wordlike"] += 1
                continue
            if v.startswith("$") and v[1:].lower() not in STD_PROPS and not lv.startswith(("$virt_", "$feature", "$survey", "$ai_", "$exception", "$web_vitals", "$geoip", "$initial_", "$session_", "$entry_", "$prev_", "$set", "$group")):
                g = max(g, 0.5 if len(v) > 3 else g)
            if g >= 0.7:
                flag(i, role, f"gibberish_{role}", 1.0)
            elif g >= 0.5:
                flag(i, role, f"suspicious_{role}", 0.5)
            else:
                wordlike.append(v)
            continue
        if is_qual:
            if lv in ROOT_QUALIFIERS or lv in defined or lv in ks["lower"] or re.fullmatch(r"group_\d", lv):
                continue
            if shape(v) in defined_shapes:
                flag(i, "qualifier", "undefined_alias", 1.0)
            elif gibberish(v, ks["extra"]) >= 0.6:
                flag(i, "qualifier", "gibberish_qualifier", 1.0)
            elif len(v) <= 3:
                flag(i, "qualifier", "undefined_alias_short", 0.6)
            else:
                wordlike.append(v)
                reasons["undefined_qualifier_wordlike"] += 1
            continue
        # bare identifier
        if lv in CORE_COLUMNS or lv in ks["lower"] or lv.lstrip("$") in STD_PROPS:
            continue
        if lprev in ("from", "join"):
            if lv in CORE_TABLES:
                continue
            g = gibberish(v, ks["extra"])
            if g >= 0.75:
                flag(i, "table", "gibberish_table", 0.8)
            continue
        # keyword slot: all-caps token shaped like a keyword, or `expr XX ident`
        prev_end = i > 0 and (kinds[i - 1] in _EXPR_END or vals[i - 1] == ")")
        next_id = i + 1 < n and kinds[i + 1] in ("id", "qid") and low[i + 1] not in KEYWORDS
        sh = shape(v)
        if v.isupper() and len(v) <= 9 and sh in kw_shapes and upper_kw >= 1:
            flag(i, "keyword", "keyword_scrambled", 1.0)
            continue
        if prev_end and next_id and sh in kw_shapes and len(v) <= 6:
            flag(i, "keyword", "keyword_scrambled", 1.0 if v.isupper() or len(v) <= 2 else 0.6)
            continue
        if i > 0 and bad and bad[-1]["idx"] == i - 1 and bad[-1]["role"] == "keyword":
            flag(i, "alias_def", "alias_after_scrambled_keyword", 0.3)
            continue
        g = gibberish(v, ks["extra"])
        if g >= 0.7:
            flag(i, "column", "gibberish_column", 1.0 if from_core else 0.7)
        elif g >= 0.5:
            flag(i, "column", "suspicious_column", 0.4)
        else:
            if from_core and lv not in defined:
                wordlike.append(v)

    # ---- score ------------------------------------------------------------------------------------------------
    score = 0.0
    by_tok: dict[str, float] = {}
    for b in bad:
        by_tok[b["token"]] = max(by_tok.get(b["token"], 0.0), b["w"])
    vals_sorted = sorted(by_tok.values(), reverse=True)
    # the strongest signal plus a quarter of the rest: one strong signal or several medium ones, not many weak ones
    score = (vals_sorted[0] + 0.25 * sum(vals_sorted[1:])) if vals_sorted else 0.0
    # corroboration: several distinct weak signals add up; a single 0.5 does not cross.
    placeholders = count_placeholders(" ".join(v for k, v, _ in toks if k == "str"))
    code_ph = sum(1 for b in bad if b["reason"] == "placeholder_in_code")
    return {
        "corrupted": score >= 0.95,
        "score": round(score, 3),
        "bad_identifiers": sorted(by_tok, key=lambda t: -by_tok[t]),
        "reasons": sorted(reasons),
        "reason_counts": dict(reasons),
        "placeholders": sum(placeholders.values()) + code_ph,
        "placeholder_kinds": placeholders,
        "bad": [{kk: b[kk] for kk in ("token", "idx", "role", "reason", "w")} for b in bad],
        "unknown_wordlike": sorted(set(wordlike))[:20],
        "tables": sorted(tables_used),
        "alias_tables": alias_tables,
        "qualifier_names": sorted(qual_names),
        "defined": sorted(defined),
    }


# ------------------------------------------------------------------------------------------------ SQL extraction

_SQL_HINT = re.compile(r"(?is)\bselect\b.+?\bfrom\b")
_FENCE = re.compile(r"```[ \t]*([A-Za-z]*)[ \t]*\n(.*?)```", re.S)
_STMT = re.compile(r"(?is)(?:^|(?<=[\s:(>\"]))((?:WITH\s+[A-Za-z_]\w*\s+AS\s*\(|SELECT\s)(?:(?!\n\s*\n|```).)+)")


def _looks_sql(s: str) -> bool:
    return bool(_SQL_HINT.search(s)) and bool(re.search(r"(?is)\bfrom\s+[A-Za-z_`\"(]", s)) \
        and bool(re.search(r"[(),.*=]", s))


def extract_sql_snippets(text: str) -> list[str]:
    """SQL inside a free-text or JSON string: JSON `query` fields, fenced blocks, then bare SELECT/WITH statements."""
    if not text or not _SQL_HINT.search(text):
        return []
    out: list[str] = []
    stripped = text.strip()
    if stripped[:1] in "[{":
        try:
            obj = json.loads(stripped)
        except ValueError:
            obj = None
        if obj is not None:
            for s in _json_strings(obj):
                out.extend(extract_sql_snippets(s))
            return out
    rest = text
    for m in _FENCE.finditer(text):
        body = m.group(2)
        if _looks_sql(body):
            out.append(body)
    rest = _FENCE.sub(" ", text)
    for m in _STMT.finditer(rest):
        s = m.group(1)
        if _looks_sql(s):
            out.append(s)
    return out


def _json_strings(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _json_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _json_strings(v)
    elif isinstance(obj, str) and _SQL_HINT.search(obj):
        yield obj


def tool_input_sqls(name: str, inp) -> list[tuple[str, str]]:
    """(field path, sql) pairs from one tool_use input."""
    out = []

    def walk(o, path):
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, path + (str(k),))
        elif isinstance(o, list):
            for v in o:
                walk(v, path + ("[]",))
        elif isinstance(o, str) and _SQL_HINT.search(o):
            key = path[-1] if path else ""
            if key in ("query", "sql", "hogql", "select") and _looks_sql(o) and not o.lstrip().startswith(("[", "{")):
                out.append((".".join(path), o))
            else:
                for s in extract_sql_snippets(o):
                    out.append((".".join(path), s))

    walk(inp if isinstance(inp, (dict, list)) else {"input": inp}, ())
    return out


# ------------------------------------------------------------------------------------------------ conversation

_ERR_RE = re.compile(r"QueryError|SyntaxError|Unable to resolve field|Field not found|Unsupported function|"
                     r"cannot be parsed|Tool failed|validation error|internal error|Exception|\berror\b", re.I)


def _blocks(m):
    c = m.get("content")
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    return c or []


def _result_text(b) -> str:
    c = b.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in c)
    return json.dumps(c) if c is not None else ""


def _is_error_result(b) -> bool:
    if b.get("is_error"):
        return True
    t = _result_text(b)[:400]
    return bool(_ERR_RE.search(t)) and not t.lstrip().startswith(("Here is the results", "|"))


def _id_tokens(sql: str) -> list[tuple[int, str]]:
    return [(i, v) for i, (k, v, _) in enumerate(tokenize(sql)) if k == "id"]


def analyze_conversation(messages, known: dict | None = None) -> list[dict]:
    """One dict per SQL-bearing tool_use: indexes, tool, field, corruption result, tool-result error, repairs."""
    results_by_id = {}
    for m in messages:
        for b in _blocks(m):
            if isinstance(b, dict) and b.get("type") == "tool_result":
                results_by_id[b.get("tool_use_id")] = b
    calls = []
    a_turn = h_turn = -1
    for mi, m in enumerate(messages):
        role = m.get("role")
        if role == "user" and any(isinstance(b, dict) and b.get("type") == "text" for b in _blocks(m)):
            h_turn += 1
        if role != "assistant":
            continue
        a_turn += 1
        for b in _blocks(m):
            if not isinstance(b, dict) or b.get("type") != "tool_use":
                continue
            for field, sql in tool_input_sqls(b.get("name", ""), b.get("input")):
                res = analyze_sql(sql, known)
                rb = results_by_id.get(b.get("id"))
                calls.append({
                    "message_index": mi, "assistant_turn": a_turn, "human_turn": max(h_turn, 0),
                    "tool_use_id": b.get("id"), "tool": b.get("name"), "field": field, "sql": sql,
                    "result_error": _is_error_result(rb) if rb else None, "_result": _result_text(rb) if rb else "",
                    **res,
                })
    _repair(calls, messages, known)
    return calls


def _context_pool(messages) -> Counter:
    """Identifier-like tokens from non-SQL text in the conversation (taxonomy, results), for shape matching."""
    c = Counter()
    for m in messages:
        for b in _blocks(m):
            if not isinstance(b, dict):
                continue
            t = b.get("text") if b.get("type") == "text" else _result_text(b) if b.get("type") == "tool_result" else ""
            if t:
                c.update(re.findall(r"\$?[A-Za-z_][A-Za-z0-9_$]{1,60}", t[:200000]))
    return c


# Per-table columns for joint alias/field repair.
TABLE_COLUMNS = {
    "events": set("""uuid event properties timestamp distinct_id elements_chain created_at person_id person pdi poe
        team_id session $session_id $window_id $group_0 $group_1 $group_2 $group_3 $group_4 group_0 group_1 group_2
        group_3 group_4 elements_chain_href elements_chain_texts elements_chain_ids elements_chain_elements
        event_person_id $session_id_uuid""".split()),
    "persons": set("id created_at properties is_identified team_id pdi version".split()),
    "sessions": {c for c in CORE_COLUMNS if c.startswith("$")} | {"session_id", "distinct_id", "id"},
    "groups": set("key index created_at properties team_id group_type_index group_key".split()),
    "person_distinct_ids": set("distinct_id person_id person is_deleted version team_id".split()),
    "cohort_people": set("person_id cohort_id person version".split()),
    "session_replay_events": set("""session_id distinct_id start_time end_time click_count keypress_count
        mouse_activity_count active_milliseconds console_log_count console_warn_count console_error_count first_url
        all_urls size event_count message_count snapshot_source min_first_timestamp max_last_timestamp
        retention_period_days person events""".split()),
}
_RESULTS_HDR = re.compile(r"(?m)^Results:\s*\n```[^\n]*\n([^\n]+)\n")


def _result_columns(text: str) -> list[str]:
    m = _RESULTS_HDR.search(text or "")
    if not m or "|" not in m.group(1):
        return []
    return [c.strip() for c in m.group(1).strip().strip("|").split("|")]


def _select_items(toks) -> list[list[int]]:
    """Token-index lists of the outermost (main) SELECT list."""
    vals = [t[1].lower() for t in toks]
    depth, start, items = 0, None, []
    for i, v in enumerate(vals):
        if v == "(":
            depth += 1
        elif v == ")":
            depth -= 1
        elif depth == 0 and v == "select":
            start, items = i + 1, []
            if start < len(vals) and vals[start] == "distinct":
                start += 1
        elif depth == 0 and start is not None and v == ",":
            items.append(list(range(start, i)))
            start = i + 1
        elif depth == 0 and start is not None and v == "from":
            items.append(list(range(start, i)))
            start = None
    if start is not None:
        items.append(list(range(start, len(vals))))
    return [it for it in items if it]


_KW_UP = {k.upper() for k in KEYWORDS}


def _keyword_candidates(x: str, prev: str, nxt: str) -> set[str]:
    sx = shape(x)
    cands = {k for k in (_KW_UP | KEYWORDS) if shape(k) == sx and k != x}
    p, q = prev.lower(), nxt.lower()
    rule = None
    if q and re.match(r"[A-Za-z_$`\"]", nxt) and q not in KEYWORDS:
        rule = "as"
    if q == "by":
        rule = "group" if p in ("", ")", ",") or p.isidentifier() else None
    if p in ("group", "order", "partition"):
        rule = "by"
    if p == "select":
        rule = "distinct"
    if q.isdigit():
        rule = "interval"
    if p in ("left", "inner", "right", "full", "cross", "array"):
        rule = "join"
    if rule:
        hit = {k for k in cands if k.lower() == rule}
        if hit:
            return hit
    return cands


def _repair(calls, messages, known):
    """Conversation-level repair: votes from result headers, alignment with clean queries, role pools, context."""
    ks = known or {}
    ks_sets = _known_sets(known)
    bad_tokens_all = {b["token"] for c in calls for b in c["bad"]}
    good_calls = [c for c in calls if not c["bad"]]
    good_tokens = [tokenize(c["sql"]) for c in good_calls]
    good_by_role = defaultdict(set)
    for toks in good_tokens:
        for i, (k, v, _) in enumerate(toks):
            if k != "id":
                continue
            prev = toks[i - 1][1] if i else ""
            nx = toks[i + 1][1] if i + 1 < len(toks) else ""
            if nx == "(" and prev != ".":
                good_by_role["function"].add(v)
            elif prev == ".":
                good_by_role["field"].add(v)
            elif nx == ".":
                good_by_role["qualifier"].add(v)
            elif prev.lower() == "as":
                good_by_role["alias_def"].add(v)
            else:
                good_by_role["column"].add(v)
    ctx = _context_pool(messages) if any(c["corrupted"] for c in calls) else Counter()
    props_pool = set(ks.get("props", ())) | {"$" + p for p in STD_PROPS} | good_by_role["field"]
    func_pool = {f for f in _FUNCS} | good_by_role["function"]
    votes: dict[str, Counter] = defaultdict(Counter)

    vote_src: dict[tuple[str, str], Counter] = defaultdict(Counter)

    def vote(x, y, w, src="?"):
        if y and x != y and shape(x) == shape(y) and y not in bad_tokens_all:
            # one vote per (pair, evidence source) per conversation: repeated weak evidence must not add up
            if w > vote_src[(x, y)][src]:
                votes[x][y] += w - vote_src[(x, y)][src]
                vote_src[(x, y)][src] = w

    for c in calls:
        if not c["corrupted"]:
            continue
        toks = tokenize(c["sql"])
        vals = [t[1] for t in toks]
        badset = {b["token"] for b in c["bad"]}
        # A) result header: SELECT item i -> result column i (names survive because only the code span was scrambled)
        hdr = _result_columns(c.get("_result") or "")
        items = _select_items(toks)
        if hdr and len(hdr) == len(items):
            for it, col in zip(items, hdr):
                last = vals[it[-1]]
                if last in badset:
                    vote(last, col, 3, "header")
                    # `q.f.col AS alias` with the alias repaired: the column usually has the alias name
                    if len(it) >= 3 and vals[it[-3]] in badset and shape(vals[it[-3]]) == shape(col):
                        vote(vals[it[-3]], col, 1, "header_alias")
                    if len(it) >= 2 and vals[it[-2]] in badset and toks[it[-2]][0] == "id":
                        for kw in _keyword_candidates(vals[it[-2]], vals[it[-3]] if len(it) >= 3 else "", last):
                            if kw.lower() == "as":
                                vote(vals[it[-2]], kw, 3, "header_kw")
        # B) alignment with clean queries of the conversation
        for gt in good_tokens:
            gv = [t[1] for t in gt]
            sm = difflib.SequenceMatcher(a=vals, b=gv, autojunk=False)
            if sm.quick_ratio() < 0.7 or sm.ratio() < 0.7:
                continue
            for op, a0, a1, b0, b1 in sm.get_opcodes():
                if op == "replace" and a1 - a0 == b1 - b0 <= 3:
                    for x, y in zip(vals[a0:a1], gv[b0:b1]):
                        if x in badset:
                            vote(x, y, 2, "align")
        # C) role pools and context rules
        alias_tables = {k.lower(): v for k, v in (c.get("alias_tables") or {}).items()}
        defined = set(c.get("defined") or [])
        for b in c["bad"]:
            x, role, i = b["token"], b["role"], b["idx"]
            if role == "code":
                continue
            sx = shape(x)
            prev = vals[i - 1] if i > 0 else ""
            nxt = vals[i + 1] if i + 1 < len(vals) else ""
            if role == "keyword":
                cands = _keyword_candidates(x, prev, nxt)
                if len(cands) == 1:
                    vote(x, next(iter(cands)), 2, "kw")
                continue
            if role == "qualifier":
                fld = vals[i + 2] if i + 2 < len(vals) else ""
                fl = fld.lower()
                fld_unknown = fld in badset or (fl not in CORE_COLUMNS and fl not in ks_sets["lower"]
                                                and fl.lstrip("$") not in STD_PROPS and fl != "properties")
                combos = []
                bad_low = {t.lower() for t in bad_tokens_all}
                for a in c.get("qualifier_names") or []:
                    if shape(a) != sx or a in bad_low:
                        continue
                    cols = TABLE_COLUMNS.get(alias_tables.get(a, a))
                    if fld_unknown:
                        if cols:
                            combos.extend((a, f) for f in cols if shape(f) == shape(fld))
                        else:
                            combos.append((a, None))
                    elif cols is None or fl in cols or fl == "properties":
                        combos.append((a, None))
                for rq in ROOT_QUALIFIERS:
                    if len(rq) > 1 and shape(rq) == sx and (rq == "properties" or fld_unknown or fl == "properties"
                                                            or fl in CORE_COLUMNS):
                        combos.append((rq, None))
                if len({a for a, _ in combos}) == 1:
                    vote(x, combos[0][0], 2, "qual")
                    fs = {f for _, f in combos if f}
                    if len(fs) == 1 and fld in badset:
                        vote(fld, fs.pop(), 2, "qual_field")
                continue
            if role == "function":
                cands = {f for f in func_pool if shape(f) == sx}
                used = {f for f in cands if f in good_by_role["function"]}
                if len(used) == 1:
                    vote(x, used.pop(), 1, "func_used")
                elif len(cands) == 1:
                    vote(x, cands.pop(), 1 if len(x) >= 6 else 0.5, "func_unique")
                continue
            open_schema = False
            if role in ("property",) or (prev == "." and i >= 2 and vals[i - 2].lower() == "properties"):
                pools = [good_by_role["field"], props_pool, {t for t in ctx if t.startswith("$") == x.startswith("$")}]
            elif role == "field":
                head = vals[i - 2].lower() if i >= 2 else ""
                cols = TABLE_COLUMNS.get(alias_tables.get(head, head))
                open_schema = cols is None
                pools = [good_by_role["field"], cols or set(), set(ks.get("columns", ())) | CORE_COLUMNS, set(ctx)]
            elif role == "alias_def":
                pools = [good_by_role["alias_def"] | good_by_role["column"]]
            else:  # bare column / table
                tabs = [TABLE_COLUMNS.get(t) for t in (c.get("tables") or [])]
                open_schema = any(t is None for t in tabs)  # a warehouse table may own the column
                cols = set().union(*[t for t in tabs if t]) if any(tabs) else set()
                pools = [good_by_role["column"] | good_by_role["alias_def"], cols, set(ks.get("columns", ())), set(ctx)]
            # Shape-only evidence: full weight only for distinctive shapes whose candidate is unique across the
            # narrow pools (clean SQL of this conversation, schema/known names); the wide context pool only helps.
            distinctive = len(x) >= 7 or (len(x) >= 5 and re.search(r"[_$\d]", x[1:]))
            narrow = set().union(*pools[:2])
            n_cands = {p for p in narrow if shape(p) == sx and p != x and p not in bad_tokens_all}
            for rank, pool in enumerate(pools):
                cands = {p for p in pool if shape(p) == sx and p != x and p not in bad_tokens_all}
                w = (1.0 if distinctive else 0.5) * (1.0 if rank < 2 and len(n_cands) == 1 and not open_schema else 0.5)
                if len(cands) == 1:
                    vote(x, cands.pop(), w, f"pool{rank}")
                    break
                if len(cands) > 1:
                    break
    resolved = {}
    for x, cnt in votes.items():
        top = cnt.most_common(2)
        if top[0][1] >= 1.0 and (len(top) == 1 or top[0][1] >= 2 * top[1][1]):
            resolved[x] = top[0][0]
    for c in calls:
        c.pop("_result", None)
        c["repairs"], c["repaired_sql"], c["repair_status"] = {}, None, None
        if not c["corrupted"]:
            continue
        repairs = {b["token"]: resolved[b["token"]] for b in c["bad"] if b["token"] in resolved}
        c["repairs"] = repairs
        c["repair_sources"] = {x: sorted(vote_src[(x, y)]) for x, y in repairs.items()}
        need = {b["token"] for b in c["bad"] if b["w"] >= 0.5}
        if need and need <= set(repairs) and not any(b["role"] == "code" for b in c["bad"]):
            toks = tokenize(c["sql"])
            out, last = [], 0
            for k, v, pos in toks:
                if k == "id" and v in repairs:
                    out.append(c["sql"][last:pos])
                    out.append(repairs[v])
                    last = pos + len(v)
            out.append(c["sql"][last:])
            fixed = "".join(out)
            check = analyze_sql(fixed, known)
            c["repaired_sql"] = fixed if not check["corrupted"] else None
            c["repair_status"] = "repaired" if c["repaired_sql"] else "repair_rejected"
        else:
            c["repair_status"] = "partial" if repairs else "none"


# ------------------------------------------------------------------------------------------------ helpers

def known_from_spec(spec: dict) -> dict:
    """Known sets from a twin spec; names whose only evidence is agent SQL are excluded (they may be scrambled)."""
    sqlish = {"sql", "sql_failed", "insight_sql", "insight_patch_failed", "insight_failed"}

    def trusted(obj):
        src = obj.get("sources") or {}
        names = set(src) if isinstance(src, (dict, list)) else set()
        return bool(names - sqlish)

    events, props, tables, columns = set(), set(), set(), set()
    for name, ev in (spec.get("events") or {}).items():
        if ev.get("evidence") == "observed":
            events.add(name)
        for p, P in (ev.get("properties") or {}).items():
            if trusted(P):
                props.add(p)
    for p, P in (spec.get("event_properties_unscoped") or {}).items():
        if trusted(P):
            props.add(p)
    for scope in ("person", "session"):
        for p, P in (((spec.get("entities") or {}).get(scope) or {}).get("properties") or {}).items():
            if trusted(P):
                props.add(p)
    for g in ((spec.get("groups") or {}).get("types") or {}).values():
        for p, P in (g.get("properties") or {}).items():
            if trusted(P):
                props.add(p)
    for t, T in ((spec.get("warehouse") or {}).get("tables") or {}).items():
        if T.get("evidence") == "observed":
            tables.add(t)
            for part in t.split("."):
                tables.add(part)
            for f in T.get("fields") or []:
                if f.get("name"):
                    columns.add(f["name"])
    return {"events": events, "props": props, "tables": tables, "columns": columns, "aliases": set()}


def build_vocab(docs, min_df: int = 2, min_df_short: int = 3) -> set[str]:
    """docs: iterable of strings, one per conversation. Returns identifier parts seen in >= min_df documents."""
    df = Counter()
    for text in docs:
        parts = set()
        for tok in set(re.findall(r"\$?[A-Za-z_][A-Za-z0-9_$]{1,60}", text)):
            parts.update(_parts(tok))
        df.update(parts)
    return {p for p, c in df.items() if c >= (min_df_short if len(p) <= 4 else min_df)}
