"""Tests for gdecide.data.reasoning_gen.

The label checks recompute every label from ``meta["facts"]`` with code written separately from the generator
(timestamps instead of UTC datetimes, ISO weeks instead of Mondays, Decimal instead of Fraction, ...), so a bug in a
generator solver shows up as a disagreement instead of being copied into the check.
"""

import gzip
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, getcontext
from zoneinfo import ZoneInfo

import pytest

from gdecide.data import reasoning_gen as G
from gdecide.data.hub_sources import validate_row

getcontext().prec = 60
N = 4000


@pytest.fixture(scope="module")
def rows():
    return G.generate(N, 7, "train")


def by_family(rows, family):
    return [r for r in rows if r["meta"]["family"] == family]


def only(row):
    (key, q), = row["questions"].items()
    return key, q, row["expected"][key]


# --------------------------------------------------------------------------------------------- format, determinism


def test_rows_are_valid(rows):
    assert len(rows) == N
    assert len({r["id"] for r in rows}) == N
    assert len({r["state"] for r in rows}) == N
    for r in rows:
        assert validate_row(r) is None, r["id"]
        assert r["source"] == f"gdecide-gen/reasoning/{r['meta']['family']}"
        assert r["license"] == G.LICENSE
        assert "facts" in r["meta"]
        for key, q in r["questions"].items():
            target = r["expected"][key]
            if q["type"] == "noul":
                assert target in (0.0, 1.0)
            else:
                assert isinstance(target, str)  # one-hot (hard key)
            if q["type"] == "choice":
                assert all(k == k.lower() and " " not in k for k in q["criteria"])
    fams = Counter(r["meta"]["family"] for r in rows)
    assert set(fams) == set(G.FAMILIES) and max(fams.values()) - min(fams.values()) <= 1
    types = Counter((r["meta"]["family"], r["meta"]["qtype"]) for r in rows)
    for fam in G.FAMILIES:
        assert types[(fam, "noul")] and types[(fam, "choice")], fam
    assert sum(r["meta"]["long"] for r in rows) / N == pytest.approx(0.5, abs=0.05)
    longs = [len(r["state"]) for r in rows if r["meta"]["long"]]
    assert sorted(longs)[len(longs) // 2] > 1000


def test_deterministic():
    a = G.generate(150, 3, "train")
    b = G.generate(150, 3, "train")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    c = G.generate(150, 4, "train")
    assert {r["state"] for r in a}.isdisjoint({r["state"] for r in c})


def test_cli_deterministic_and_disjoint(tmp_path):
    outs = []
    for name in ("a", "b"):
        out = tmp_path / name
        assert G.main(["--out", str(out), "--n", "400", "--seed", "1", "--test-n", "200", "--test-seed", "999"]) == 0
        outs.append(out)
    for fname in ("reasoning-gen.jsonl.gz", "reasoning-gen-test.jsonl.gz"):
        assert (outs[0] / fname).read_bytes() == (outs[1] / fname).read_bytes()

    def load(path):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return [json.loads(line) for line in f]

    train = load(outs[0] / "reasoning-gen.jsonl.gz")
    test = load(outs[0] / "reasoning-gen-test.jsonl.gz")
    assert len(train) == 400 and len(test) == 200
    h = lambda r: hashlib.sha256(r["state"].encode()).hexdigest()
    assert not {h(r) for r in train} & {h(r) for r in test}
    assert not {r["id"] for r in train} & {r["id"] for r in test}
    manifest = json.loads((outs[0] / "reasoning-gen-manifest.json").read_text())
    assert manifest["train"]["rows"] == 400 and manifest["test"]["rows"] == 200
    assert sum(manifest["train"]["families"].values()) == 400


def test_label_balance(rows):
    noul = defaultdict(list)
    positions = defaultdict(Counter)
    for r in rows:
        for key, q in r["questions"].items():
            if q["type"] == "noul":
                noul[r["meta"]["family"]].append(r["expected"][key])
            elif q["type"] == "choice":
                keys = list(q["criteria"])
                positions[len(keys)][keys.index(r["expected"][key])] += 1
    everything = [v for vs in noul.values() for v in vs]
    assert sum(everything) / len(everything) == pytest.approx(0.5, abs=0.04)
    for fam, vs in noul.items():
        assert sum(vs) / len(vs) == pytest.approx(0.5, abs=0.12), fam
    for k, counter in positions.items():
        total = sum(counter.values())
        if total < 200:
            continue
        for pos in range(k):
            assert counter[pos] / total == pytest.approx(1 / k, abs=0.35 / k), (k, dict(counter))


# --------------------------------------------------------------------------------------------- independent solvers


def ts(iana, iso):
    """POSIX timestamp of a local wall time (the generator never emits ambiguous or skipped wall times)."""
    naive = datetime.fromisoformat(iso)
    z = ZoneInfo(iana)
    a, b = naive.replace(tzinfo=z, fold=0), naive.replace(tzinfo=z, fold=1)
    assert a.utcoffset() == b.utcoffset(), (iana, iso)
    return int(a.timestamp())


def business_day_after(d, n, holidays):
    count = 0
    while count < n:
        d = d + timedelta(days=1)
        if d.isoweekday() <= 5 and d.isoformat() not in holidays:
            count += 1
    return d


def deadline_bounds(f):
    receipt = datetime.fromisoformat(f["receipt"]).date()
    opening_day = business_day_after(receipt, f["open_after"], set(f["holidays"]))
    t_open = ts(f["zone"], f"{opening_day.isoformat()}T{f['open_time']}")
    dur = f["duration"]
    if dur["kind"] == "hours":
        t_close = t_open + 3600 * dur["hours"]
    else:
        closing_day = business_day_after(opening_day, dur["days"], set(f["holidays"]))
        t_close = ts(f["zone"], f"{closing_day.isoformat()}T{dur['close_time']}")
    return t_open, t_close


def deadline_class(f, t, t_open, t_close):
    if t < t_open:
        return "before_open"
    if t < t_close or (t == t_close and f["inclusive_end"]):
        return "on_time"
    return "late_major" if t - t_close >= 3600 * f["late_hours"] else "late_minor"


def test_deadline_labels(rows):
    seen = Counter()
    for r in by_family(rows, "deadline"):
        f = r["meta"]["facts"]
        _key, q, target = only(r)
        t_open, t_close = deadline_bounds(f)
        classes = [deadline_class(f, ts(e["zone"], e["local"]), t_open, t_close) for e in f["events"]]
        v = r["meta"]["variant"]
        seen[v] += 1
        if v == "classify":
            assert target == classes[0], r["id"]
        elif v == "on_time":
            assert target == float(classes[0] == "on_time"), r["id"]
        elif v == "count":
            assert int(target) == classes.count("on_time"), r["id"]
        else:
            local = datetime.fromtimestamp(t_close, ZoneInfo(f["zone"]))
            assert target == f"{local.strftime('%b').lower()}_{local.day}_{local:%H%M}", r["id"]
            # the gold option's text names the closing day and clock time
            assert f"{local:%H:%M}" in q["criteria"][target] or local.strftime("%-I:%M") in q["criteria"][target]
    assert all(seen[v] > 20 for v in ("classify", "on_time", "count", "close")), seen


def test_deadline_has_dst_traps(rows):
    """Some windows measured in elapsed hours span a clock change, so the naive wall-clock answer is wrong."""
    spanning = 0
    for r in by_family(rows, "deadline"):
        f = r["meta"]["facts"]
        if f["duration"]["kind"] != "hours":
            continue
        t_open, t_close = deadline_bounds(f)
        z = ZoneInfo(f["zone"])
        if datetime.fromtimestamp(t_open, z).utcoffset() != datetime.fromtimestamp(t_close, z).utcoffset():
            spanning += 1
    assert spanning >= 25


def roster_breaches(f):
    shifts = sorted(
        (ts(f["offices"][s["office"]], s["start"]), ts(f["offices"][s["office"]], s["end"]))
        for s in f["shifts"])
    breaches = []
    weekly = defaultdict(int)
    capped = set()
    for i, (start, end) in enumerate(shifts):
        if i > 0 and start - shifts[i - 1][1] < 3600 * f["min_rest_h"]:
            breaches.append((start, 1, "rest"))
        if end - start > 3600 * f["max_shift_h"]:
            breaches.append((start, 2, "shift_length"))
        week = datetime.fromtimestamp(start, ZoneInfo(f["home_zone"])).isocalendar()[:2]
        weekly[week] += end - start
        if weekly[week] > 3600 * f["week_cap_h"] and week not in capped:
            capped.add(week)
            breaches.append((start, 3, "weekly_cap"))
    return sorted(breaches)


def test_roster_labels(rows):
    seen = Counter()
    for r in by_family(rows, "roster"):
        f = r["meta"]["facts"]
        _key, _q, target = only(r)
        breaches = roster_breaches(f)
        v = r["meta"]["variant"]
        seen[(v, str(target))] += 1
        if v == "compliant":
            assert target == float(not breaches), r["id"]
        elif v == "count":
            assert int(target) == min(3, len(breaches)), r["id"]
        else:
            assert target == (breaches[0][2] if breaches else "none"), r["id"]
    assert all(seen[("first", k)] > 5 for k in ("rest", "shift_length", "weekly_cap", "none")), seen


def test_roster_has_clock_change_shifts(rows):
    n = 0
    for r in by_family(rows, "roster"):
        f = r["meta"]["facts"]
        for s in f["shifts"]:
            z = f["offices"][s["office"]]
            wall = (datetime.fromisoformat(s["end"]) - datetime.fromisoformat(s["start"])).total_seconds()
            if ts(z, s["end"]) - ts(z, s["start"]) != wall:
                n += 1
    assert n >= 20


UNITS = {"mg/kg": Decimal("1e-6"), "ppm": Decimal("1e-6"), "µg/g": Decimal("1e-6"), "mg/L": Decimal("1e-6"),
         "g/kg": Decimal("1e-3"), "mg/g": Decimal("1e-3"), "g/L": Decimal("1e-3"),
         "%": Decimal("1e-2"), "g/100 g": Decimal("1e-2"),
         "µg/kg": Decimal("1e-9"), "ppb": Decimal("1e-9"), "µg/L": Decimal("1e-9")}


def corrected(f, measured):
    m = Decimal(measured)
    u = Decimal(f["uncertainty"]["value"]) if f["uncertainty"]["kind"] == "abs" else (
        m * Decimal(f["uncertainty"]["pct"]) / 100)
    value = m + u if f["limit_kind"] == "max" else m - u
    return value * UNITS[f["meas_unit"]]


def threshold_class(f, measured):
    c = corrected(f, measured)
    limit = Decimal(f["limit"]) * UNITS[f["limit_unit"]]
    gap = (c - limit) if f["limit_kind"] == "max" else (limit - c)
    if gap < 0 or (gap == 0 and f["equal_passes"]):
        return "pass"
    return "narrow_fail" if gap <= limit * Decimal(f["narrow_pct"]) / 100 else "clear_fail"


def test_threshold_labels(rows):
    seen = Counter()
    for r in by_family(rows, "threshold"):
        f = r["meta"]["facts"]
        _key, q, target = only(r)
        classes = [threshold_class(f, s["measured"]) for s in f["samples"]]
        v = r["meta"]["variant"]
        seen[v] += 1
        if v == "band":
            assert target == classes[0], r["id"]
        elif v == "complies":
            assert target == float(classes[0] == "pass"), r["id"]
        elif v == "count":
            assert int(target) == classes.count("pass"), r["id"]
        else:
            true_value = corrected(f, f["samples"][0]["measured"]) / UNITS[f["limit_unit"]]

            def number(text):
                return Decimal(text.split()[0].rstrip("%"))
            best = min(q["criteria"], key=lambda k: abs(number(q["criteria"][k]) - true_value))
            assert best == target, r["id"]
            assert abs(number(q["criteria"][target]) - true_value) <= abs(true_value) * Decimal("0.005") + \
                Decimal("1e-9"), r["id"]
        assert f["limit"] in r["state"] and all(s["measured"] in r["state"] for s in f["samples"])
    assert all(seen[v] > 20 for v in ("band", "complies", "count", "corrected")), seen


def test_threshold_boundaries_present(rows):
    """Values exactly at the limit (after correction) occur and are judged by the stated equality rule."""
    exact = Counter()
    for r in by_family(rows, "threshold"):
        f = r["meta"]["facts"]
        for s in f["samples"]:
            if corrected(f, s["measured"]) == Decimal(f["limit"]) * UNITS[f["limit_unit"]]:
                exact[f["equal_passes"]] += 1
    assert exact[True] > 3 and exact[False] > 3, exact


def money(cents):
    return f"${cents // 100:,}.{cents % 100:02d}"


def half_up(x, places="1"):
    return x.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def judge_answer(template, p):
    if template == "shopping":
        sub = sum(q * c for _, q, c in p["items"])
        disc = int(half_up(Decimal(sub) * Decimal(p["discount_pct"]) / 100))
        tax = int(half_up(Decimal(sub - disc) * Decimal(p["tax_pct"]) / 100))
        return money(sub - disc + tax + p["shipping"])
    if template == "travel":
        minutes = sum(Decimal(km) * 60 / Decimal(kmh) for km, kmh in p["legs"]) + p["break_min"]
        assert minutes == int(minutes)
        h, m = map(int, p["depart"].split(":"))
        arrival = (h * 60 + m + int(minutes)) % (24 * 60)
        return f"{arrival // 60:02d}:{arrival % 60:02d}"
    if template == "payroll":
        hours = sum(Decimal(h) for h in p["hours"])
        rate = Decimal(p["rate"])
        gross = min(hours, 40) * rate + max(hours - 40, 0) * rate * Decimal(p["ot_mult"])
        gross = int(half_up(gross))
        net = gross - int(half_up(Decimal(gross) * Decimal(p["deduction_pct"]) / 100))
        return money(net)
    if template == "recipe":
        grams = Decimal(p["grams"]) * p["portions"] * (1 + Decimal(p["waste_pct"]) / 100)
        return f"{half_up(grams / 1000, '0.01')} kg"
    if template == "pct_change":
        old, new = Decimal(p["old"]), Decimal(p["new"])
        return f"{half_up((new - old) / old * 100, '0.1')}%"
    raise AssertionError(template)


def test_judge_labels(rows):
    seen = Counter()
    for r in by_family(rows, "judge"):
        f = r["meta"]["facts"]
        _key, q, target = only(r)
        answer = judge_answer(f["template"], f["params"])
        finals = [resp["final"] for resp in f["responses"]]
        for final in finals:
            assert final in r["state"], r["id"]
        if q["type"] == "noul":
            assert target == float(finals[0] == answer), r["id"]
            assert (f["responses"][0]["error"] is None) == (finals[0] == answer), r["id"]
            seen[(f["template"], f["responses"][0]["error"] or "correct")] += 1
        else:
            gold = list(q["criteria"]).index(target)
            assert finals[gold] == answer, r["id"]
            assert all(x != answer for j, x in enumerate(finals) if j != gold), r["id"]
    for template, errors in G.JUDGE_ERRORS.items():
        assert seen[(template, "correct")] > 10, (template, seen)
        for err in errors:
            assert seen[(template, err)] > 0, (template, err, seen)


def test_interest_labels(rows):
    for r in by_family(rows, "interest"):
        f = r["meta"]["facts"]
        _key, _q, target = only(r)
        start, end = date.fromisoformat(f["start"]), date.fromisoformat(f["end"])
        reset = None
        if f["fixing"]:
            reset = business_day_after(date.fromisoformat(f["fixing"]), 2, set(f["holidays"]))
        total = Decimal(0)
        for k in range((end - start).days):
            d = start + timedelta(days=k)
            rate = Decimal(f["rate2"] if reset and d >= reset else f["rate1"])
            principal = Decimal(f["principal"])
            if f["repayment"] and d >= date.fromisoformat(f["repayment"]["date"]):
                principal -= f["repayment"]["amount"]
            total += principal * rate  # exact; divided once below so a half cent stays exact
        cents = int(half_up(total / (100 * f["basis"])))
        assert r["meta"]["label"] in (cents, True, False), r["id"]
        if r["meta"]["variant"] == "amount":
            assert target == f"{f['currency'].lower()}_{cents // 100}_{cents % 100:02d}", r["id"]
        elif r["meta"]["variant"] == "check":
            assert target == float(f["stated"] == cents), r["id"]


def months_later(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    y += d.year
    m += 1
    for day in range(d.day, 0, -1):
        try:
            return date(y, m, day)
        except ValueError:
            continue


def test_warranty_labels(rows):
    for r in by_family(rows, "warranty"):
        f = r["meta"]["facts"]
        _key, _q, target = only(r)
        term_end = months_later(date.fromisoformat(f["delivered"]), f["term_months"])
        term_end += timedelta(days=sum((date.fromisoformat(b) - date.fromisoformat(a)).days + 1
                                       for a, b in f["repairs"]))
        cap_end = months_later(date.fromisoformat(f["manufactured"]), f["cap_months"])
        last = min(term_end, cap_end)

        def status(c, last=last, term_end=term_end, cap_end=cap_end):
            c = date.fromisoformat(c)
            return "covered" if c <= last else ("expired_term" if term_end < cap_end else "expired_cap")
        v = r["meta"]["variant"]
        if v == "status":
            assert target == status(f["claims"][0]["date"]), r["id"]
        elif v == "covered":
            assert target == float(status(f["claims"][0]["date"]) == "covered"), r["id"]
        elif v == "count":
            assert int(target) == sum(status(c["date"]) == "covered" for c in f["claims"]), r["id"]
        else:
            assert target == f"{last.strftime('%b').lower()}_{last.day}_{last.year}", r["id"]


def test_choice_distractors_are_buggy_answers(rows):
    """Wrong options of computed-value questions mostly come from the deliberately buggy variants."""
    n = 0
    for r in by_family(rows, "interest"):
        f = r["meta"]["facts"]
        if r["meta"]["variant"] != "amount":
            continue
        _key, q, target = only(r)
        bugs = {G.money_key(G.interest_amount(f, b), f["currency"]) for b in G.INTEREST_BUGS}
        wrong = set(q["criteria"]) - {target}
        n += bool(wrong & bugs)
    assert n > 0.9 * sum(r["meta"]["variant"] == "amount" for r in by_family(rows, "interest"))
