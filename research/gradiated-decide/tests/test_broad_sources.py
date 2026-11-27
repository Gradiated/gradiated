import csv
import gzip
import itertools
import json
import zipfile

import pytest

from gdecide.data import broad_sources as bs
from gdecide.data import extra_sources
from gdecide.data.hub_sources import Fetched, Stats, check_target, option_keys, validate_row

# --------------------------------------------------------------------------------------------- harness


class Ctx:
    def __init__(self, aux=None):
        self.aux = aux or {}

    def fetched(self, slug):
        return self.aux[slug]


def fetched(slug, files, source=None):
    return Fetched(source or bs.SOURCES[slug], "rev", None, list(files), [], {}, None)


@pytest.fixture
def parquet(monkeypatch):
    """Serve fixture rows instead of reading parquet (pyarrow is not a test dependency)."""
    tables = {}

    def batches(paths, columns, batch_size=4096):
        for path in paths:
            for record in tables[path.name]:
                yield {c: record.get(c) for c in columns}

    monkeypatch.setattr(bs, "_parquet_batches", batches)
    return tables


def convert(slug, files, ctx=None):
    rows = list(bs.CONVERTERS[slug](fetched(slug, files), Stats(), ctx or Ctx()))
    again = list(bs.CONVERTERS[slug](fetched(slug, files), Stats(), ctx or Ctx()))
    assert rows == again, "converter output must be deterministic"
    assert rows, f"{slug}: no rows"
    seen = set()
    for row in rows:
        assert validate_row(row) is None, (validate_row(row), row)
        assert bs.state_words(row["state"]) <= bs.MAX_STATE_WORDS * 1.1
        assert row["id"] not in seen
        seen.add(row["id"])
        for key, question in row["questions"].items():
            assert check_target(question, row["expected"][key]) is None
            if question["type"] == "choice":
                assert len(option_keys(question)) <= bs.MAX_OPTIONS
                texts = [k if v is None else v for k, v in question["criteria"].items() if k != bs.NONE_KEY]
                norm = [bs.answer_key(t) if isinstance(t, str) else json.dumps(t) for t in texts]
                assert len(set(norm)) == len(norm), f"duplicate options after normalisation: {texts}"
    return rows


def gold_text(row, key="answer"):
    question, target = row["questions"][key], row["expected"][key]
    assert isinstance(target, str)
    value = question["criteria"][target]
    return target if value is None else value


def distractor_texts(row, key="answer"):
    question, target = row["questions"][key], row["expected"][key]
    return [k if v is None else v for k, v in question["criteria"].items() if k not in (target, bs.NONE_KEY)]


def write_jsonl(path, records, gz=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    opener = gzip.open if gz else open
    with opener(path, "wt", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")
    return path


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# --------------------------------------------------------------------------------------------- helpers


def test_numbers_and_normalisation():
    assert bs.parse_number("$1,234.5") == 1234.5
    assert bs.parse_number("(23)") == -23
    assert bs.parse_number("14.1%") == 14.1
    assert bs.parse_number("Paris") is None
    assert bs.same_number(14.1, 0.141) and bs.same_number(100.0, 100.4) and not bs.same_number(100, 110)
    assert bs.numbers_in("In 2000, (192 people paid $1,234.5 or 12%.") == ["2000", "192", "$1,234.5", "12%"]
    assert bs.fmt_like(1234.567, "$1,000.00") == "$1,234.57"
    assert bs.fmt_like(-5, "3%") == "-5%"


def test_distractors_never_equal_gold():
    rng = bs.rng_for("t")
    out = bs.distinct_distractors(["12.5%"], ["0.125", "12.50%", "13%", "the 12.5%", "20%", "20.0%"], rng, 5)
    assert sorted(out) == ["13%", "20%"]
    out = bs.distinct_distractors(["Paris"], ["paris", "The Paris", "Lyon", "Lyon "], rng, 5)
    assert out == ["Lyon"]


def test_choice_from_none_modes():
    rng = bs.rng_for("x")
    q, target = bs.choice_from(rng, ["A1"], ["B2", "C3"], "Which?", none="gold")
    assert target == bs.NONE_KEY and q["criteria"][bs.NONE_KEY] == bs.NONE_TEXT
    assert all(bs.answer_key(t) != "a1" for t in (k if v is None else v for k, v in q["criteria"].items()))
    q, target = bs.choice_from(rng, ["A1"], ["B2", "C3"], "Which?", none="option")
    assert bs.NONE_KEY in q["criteria"] and target != bs.NONE_KEY
    q, target = bs.choice_from(rng, ["A1", "D4"], ["B2"], "Which?")
    assert isinstance(target, dict) and len(target) == 2 and abs(sum(target.values()) - 1) < 1e-6
    with pytest.raises(bs.Drop):
        bs.choice_from(rng, ["A1"], [], "Which?")


def test_chunk_words_covers_text():
    text = "\n\n".join(" ".join(f"w{i}_{j}" for j in range(300)) for i in range(20))
    spans = bs.chunk_words(text, 1000)
    assert spans[0][0] == 0 and spans[-1][1] == len(text)
    assert all(a[1] == b[0] for a, b in itertools.pairwise(spans))
    assert all(len(text[a:b].split()) <= 1000 for a, b in spans)


def test_fit_paragraphs_keeps_answer():
    paragraphs = [" ".join(["filler"] * 1000) for _ in range(10)]
    paragraphs[7] = "The answer is Zanzibar. " + paragraphs[7]
    kept = bs.fit_paragraphs(paragraphs, ["Zanzibar"], budget=3000)
    assert any("Zanzibar" in p for p in kept) and sum(len(p.split()) for p in kept) <= 3000


def test_registry_and_exclusions():
    assert set(bs.CONVERTERS) == set(bs.SOURCES)
    for source in bs.SOURCES.values():
        assert source.license and source.license_note and "NC" not in source.license
    repos = " ".join(s.repo.lower() for s in bs.SOURCES.values())
    for banned in ("xnli", "mmmlu", "global-mmlu", "pubmedqa", "bioasq", "bbh", "theoremqa", "scibench", "anli",
                   "contractnli", "lichess", "mind2web"):
        assert banned not in repos


# --------------------------------------------------------------------------------------------- 1. numeric QA

TABLE = [["", "2019", "2018"], ["Revenue", "1,200", "1,000"], ["Cost of sales", "800", "700"],
         ["Gross profit", "400", "300"], ["Operating expenses", "150", "120"]]


def test_tatqa(tmp_path):
    doc = {
        "table": {"uid": "t1", "table": TABLE},
        "paragraphs": [{"uid": "p1", "order": 1, "text": "Revenue grew because of new customers in Europe. The company "
                        "opened 3 new stores and 2 offices. Margins improved as the cost of sales fell."}],
        "questions": [
            {"uid": "q1", "order": 1, "question": "What was the change in revenue?", "answer": 200,
             "answer_type": "arithmetic", "scale": "thousand"},
            {"uid": "q2", "order": 2, "question": "How many years had revenue above 900?", "answer": 2,
             "answer_type": "count", "scale": ""},
            {"uid": "q3", "order": 3, "question": "Why did revenue grow?", "answer": ["new customers"],
             "answer_type": "span", "scale": ""},
            {"uid": "q4", "order": 4, "question": "Which years?", "answer": ["2019", "2018"],
             "answer_type": "multi-span", "scale": ""},
        ],
    }
    rows = convert("tatqa", [write_json(tmp_path / "tatqa.json", [doc])])
    by_id = {r["id"]: r for r in rows}
    arithmetic = by_id["tatqa:q1"]
    assert gold_text(arithmetic) == "200 thousand"
    assert all(not bs.same_number(bs.parse_number(d.split()[0]), 200) for d in distractor_texts(arithmetic))
    assert gold_text(by_id["tatqa:q2"]) == "2"
    assert gold_text(by_id["tatqa:q3"]) == "new customers"
    assert "tatqa:q4" not in by_id
    compare = by_id["tatqa-compare:t1"]
    assert all(q["type"] == "noul" for q in compare["questions"].values())


def finqa_doc(i, question, answer, exe):
    return {"id": f"ABC/2019/page_{i}.pdf-1", "pre_text": ["revenue was $ 1200 million in 2019 ."],
            "post_text": ["cost of sales was $ 800 million ."], "table_ori": TABLE,
            "qa": {"question": question, "answer": answer, "exe_ans": exe}}


def test_finqa(tmp_path):
    docs = [finqa_doc(1, "what was the growth rate of revenue?", "20.0%", 0.2),
            finqa_doc(2, "did revenue increase?", "yes", "yes")]
    rows = convert("finqa", [write_json(tmp_path / "train.json", docs)])
    numeric = next(r for r in rows if r["meta"]["task"] == "finqa/numeric")
    assert gold_text(numeric) == "20.0%"
    assert all(not bs.same_number(bs.parse_number(d), 20.0) for d in distractor_texts(numeric))
    yesno = next(r for r in rows if r["meta"]["task"] == "finqa/yesno")
    assert yesno["expected"]["answer"] == 1.0


def test_convfinqa(tmp_path):
    doc = finqa_doc(3, "", "", 0)
    doc["id"] = "Single_ABC/2019/page_3.pdf-1"
    doc["annotation"] = {"dialogue_break": ["what was revenue in 2019?", "and in 2018?", "what is the change?"],
                         "exe_ans_list": [1200.0, 1000.0, 200.0]}
    path = tmp_path / "data.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("data/train.json", json.dumps([doc]))
    rows = convert("convfinqa", [path])
    turn = rows[0]["meta"]["turn"]
    assert len(rows[0]["state"]["conversation"]) == turn
    assert bs.parse_number(gold_text(rows[0])) == [1200.0, 1000.0, 200.0][turn]


def test_drop(parquet, tmp_path):
    passage = ("The Lions scored first with a 23-yard field goal by Jason Hanson. The Buccaneers answered with a "
               "38-yard field goal by Connor Barth. Matthew Stafford threw a 5-yard pass to Calvin Johnson, and "
               "Mike Williams caught a 12-yard touchdown in 2010.")
    parquet["drop.parquet"] = [
        {"section_id": "s", "query_id": "a", "passage": passage, "question": "How many field goals were kicked?",
         "answers_spans": {"spans": ["2"], "types": ["number"]}},
        {"section_id": "s", "query_id": "b", "passage": passage, "question": "Who kicked the longest field goal?",
         "answers_spans": {"spans": ["Connor Barth"], "types": ["span"]}},
        {"section_id": "s", "query_id": "c", "passage": passage, "question": "Who scored?",
         "answers_spans": {"spans": ["Jason Hanson", "Connor Barth"], "types": ["span", "span"]}},
    ]
    rows = convert("drop", [tmp_path / "drop.parquet"])
    assert [r["id"] for r in rows] == ["drop:a", "drop:b"]
    assert gold_text(rows[0]) == "2" and "2" not in distractor_texts(rows[0])
    assert gold_text(rows[1]) == "Connor Barth"


# --------------------------------------------------------------------------------------------- 3. temporal


def test_timeqa_none_option(tmp_path):
    def rec(i, question, targets):
        return {"idx": f"/wiki/Knox#P39#{i}", "question": question, "targets": targets,
                "paragraphs": [{"title": "Knox", "text": "Knox was an MP, then a delegate, then a secretary and a "
                                "governor."}]}

    records = [rec(0, "Which position did Knox hold in 1955?", ["MP for South Antrim"]),
               rec(1, "Which position did Knox hold in 1957?", ["delegate to the Council"]),
               rec(2, "Which position did Knox hold in 1960?", ["Private Secretary"]),
               rec(3, "Which position did Knox hold in 1962?", ["Governor of Ulster"]),
               rec(4, "Which position did Knox hold in 1999?", [""])]
    path = write_jsonl(tmp_path / "train.easy.json.gzip", records, gz=True)
    rows = convert("timeqa", [path])
    unanswerable = next(r for r in rows if r["id"].endswith("#4"))
    assert unanswerable["expected"]["answer"] == bs.NONE_KEY
    assert unanswerable["questions"]["answer"]["criteria"][bs.NONE_KEY] == bs.NONE_TEXT
    answerable = next(r for r in rows if r["id"].endswith("#0"))
    assert gold_text(answerable) == "MP for South Antrim"


def test_tempreason(tmp_path):
    record = {"id": "L2_Q1_P39_0", "question": "Which position did Ann hold in May, 1946?",
              "text_answers": {"text": ["senator"]}, "neg_answers": ["governor", "mayor", "senator", "judge"],
              "fact_context": "Ann holds the position of governor from Jan, 1951 to Jan, 1957.\n"
                              "Ann holds the position of senator from Jan, 1940 to Jan, 1951.",
              "context": "Ann was a senator and later governor of the state."}
    rows = convert("tempreason", [write_jsonl(tmp_path / "train_l2.json", [record])])
    assert gold_text(rows[0]) == "senator" and "senator" not in distractor_texts(rows[0])


def test_2wiki(parquet, tmp_path):
    context = json.dumps([["Film A", ["Film A is a 1970 film directed by Stuart Rosenberg."]],
                          ["Stuart Rosenberg", ["Stuart Rosenberg (August 11, 1927 - March 15, 2007) was a director."]],
                          ["Jean Pollet", ["Jean Pollet (28 June 1936 - 9 September 2004) was a French director."]],
                          ["Film B", ["Film B is a 1963 film directed by Jean Pollet."]]])
    parquet["train.parquet"] = [
        {"_id": "c1", "type": "compositional", "question": "When was the director of Film A born?",
         "context": context, "evidences": json.dumps([["Film A", "director", "Stuart Rosenberg"],
                                                       ["Stuart Rosenberg", "date of birth", "August 11, 1927"]]),
         "answer": "August 11, 1927"},
        {"_id": "c2", "type": "comparison", "question": "Which film came out first, Film A or Film B?",
         "context": context, "evidences": json.dumps([["Film A", "publication date", "1970"],
                                                       ["Film B", "publication date", "1963"]]),
         "answer": "Film B"},
        {"_id": "c3", "type": "bridge_comparison", "question": "Was the director of Film A born before the "
         "director of Film B?", "context": context,
         "evidences": json.dumps([["Stuart Rosenberg", "date of birth", "1927"], ["Jean Pollet", "date of birth",
                                                                                  "1936"]]), "answer": "yes"},
        {"_id": "c4", "type": "inference", "question": "Who is the grandchild?", "context": context,
         "evidences": "[]", "answer": "X"},
    ]
    rows = {r["id"]: r for r in convert("2wikimultihopqa", [tmp_path / "train.parquet"])}
    assert gold_text(rows["2wiki:c1"]) == "August 11, 1927"
    assert all(bs.kind_of(d) in ("date", "year") for d in distractor_texts(rows["2wiki:c1"]))
    assert sorted([gold_text(rows["2wiki:c2"]), *distractor_texts(rows["2wiki:c2"])]) == ["Film A", "Film B"]
    assert rows["2wiki:c3"]["expected"]["answer"] == 1.0 and "2wiki:c4" not in rows


# --------------------------------------------------------------------------------------------- 4. contracts


def test_cuad_balanced(parquet, tmp_path, monkeypatch):
    monkeypatch.setattr(bs, "CHUNK_WORDS", 200)
    words = [f"word{i}" for i in range(1000)]
    words[50:53] = ["governed", "by", "Delaware"]
    words[700:703] = ["exclusive", "dealing", "commitment"]
    context = " ".join(words)
    start_gov = context.index("governed")
    start_exc = context.index("exclusive")

    def q(cat, details):
        return f'Highlight the parts (if any) of this contract related to "{cat}" that should be reviewed by a ' \
               f"lawyer. Details: {details}"

    parquet["0000.parquet"] = [
        {"title": "ACME_AGREEMENT", "context": context, "question": q("Governing Law", "Which law governs?"),
         "answers": {"text": ["governed by Delaware"], "answer_start": [start_gov]}},
        {"title": "ACME_AGREEMENT", "context": context, "question": q("Exclusivity", "Exclusive dealing?"),
         "answers": {"text": ["exclusive dealing commitment"], "answer_start": [start_exc]}},
        {"title": "ACME_AGREEMENT", "context": context, "question": q("Insurance", "Insurance required?"),
         "answers": {"text": [], "answer_start": []}},
        {"title": "ACME_AGREEMENT", "context": context, "question": q("Audit Rights", "Audit?"),
         "answers": {"text": [], "answer_start": []}},
    ]
    rows = convert("cuad", [tmp_path / "0000.parquet"])
    for row in rows:
        values = list(row["expected"].values())
        if 1.0 in values:
            assert values.count(1.0) == values.count(0.0)
    first = next(r for r in rows if r["id"] == "cuad:ACME_AGREEMENT#0")
    assert first["expected"]["governing_law"] == 1.0 and "exclusivity" not in first["expected"] or \
        first["expected"].get("exclusivity") == 0.0


def test_maud(tmp_path):
    path = tmp_path / "MAUD_train.csv"
    fields = ["data_type", "contract_name", "text", "answer", "label", "question", "subquestion", "text_type", "id",
              "category"]
    records = [
        ["main", "c1", "each share converted into $70 in cash", "All Cash", "0", "Type of Consideration-Answer",
         "<NONE>", "t", "1", "General"],
        ["main", "c2", "each share converted into 0.5 shares of parent", "All Stock", "1",
         "Type of Consideration-Answer", "<NONE>", "t", "1", "General"],
        ["abridged", "c1", "converted into $70", "All Cash", "0", "Type of Consideration-Answer", "<NONE>", "t", "1",
         "General"],
        ["main", "c1", "the merger shall be effective upon announcement", "announcement", "1",
         "A/P/C application to-Answer", "announcement", "t", "2", "MAE"],
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(fields)
        writer.writerows(records)
    rows = convert("maud", [path])
    assert len(rows) == 3
    choice = next(r for r in rows if r["meta"]["task"] == "maud/choice" and "c2" in r["id"])
    assert gold_text(choice) == "All Stock" and distractor_texts(choice) == ["All Cash"]
    assert next(r for r in rows if r["meta"]["task"] == "maud/subquestion")["expected"]["answer"] == 1.0


# --------------------------------------------------------------------------------------------- 5. ShARC


def test_sharc(tmp_path):
    base = {"tree_id": "t", "source_url": "u", "snippet": "You can claim if you are over 16.", "scenario": "",
            "question": "Can I claim?", "history": [], "evidence": []}
    records = [dict(base, utterance_id="a", answer="Yes"), dict(base, utterance_id="b", answer="Are you over 16?"),
               dict(base, utterance_id="c", answer="Irrelevant")]
    path = tmp_path / "sharc.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("sharc1-official/json/sharc_train.json", json.dumps(records))
    rows = convert("sharc", [path])
    assert [r["expected"]["response"] for r in rows] == ["Yes", "Inquire", "Irrelevant"]


# --------------------------------------------------------------------------------------------- 6. multi-hop


def test_hotpotqa(parquet, tmp_path):
    context = {"title": ["Arthur's Magazine", "First for Women", "Radio City", "Echosmith"],
               "sentences": [["Arthur's Magazine was an American literary periodical first published in 1844."],
                             ["First for Women is a woman's magazine published by Bauer Media Group in the USA."],
                             ["Radio City is India's first private FM radio station started on 3 July 2001."],
                             ["Echosmith is an American indie pop band formed in Chino, California in 2009."]]}
    parquet["h.parquet"] = [
        {"id": "h1", "question": "Which magazine was started first, Arthur's Magazine or First for Women?",
         "answer": "Arthur's Magazine", "type": "comparison", "level": "easy", "context": context},
        {"id": "h2", "question": "In what year was the band from Chino formed?", "answer": "2009", "type": "bridge",
         "level": "easy", "context": context},
        {"id": "h3", "question": "Are both magazines American?", "answer": "no", "type": "comparison",
         "level": "easy", "context": context},
    ]
    rows = {r["id"]: r for r in convert("hotpotqa", [tmp_path / "h.parquet"])}
    assert distractor_texts(rows["hotpotqa:h1"]) == ["First for Women"]
    assert gold_text(rows["hotpotqa:h2"]) == "2009"
    assert all(bs.kind_of(d) == "year" for d in distractor_texts(rows["hotpotqa:h2"]))
    assert rows["hotpotqa:h3"]["expected"]["answer"] == 0.0


def test_musique_unanswerable(tmp_path):
    paragraphs = [{"idx": 0, "title": "Queen", "paragraph_text": "Crazy Little Thing Called Love was written by "
                   "Freddie Mercury of Queen in London."},
                  {"idx": 1, "title": "Freddie Mercury", "paragraph_text": "Freddie Mercury was born in Zanzibar and "
                   "died in 1991 in Kensington. Brian May was born in 1947 and Roger Taylor in 1949."}]
    decomposition = [{"answer": "Freddie Mercury"}, {"answer": "1991"}]
    records = [{"id": "2hop__1_2", "paragraphs": paragraphs, "question": "When did the writer of Crazy Little Thing "
                "Called Love die?", "question_decomposition": decomposition, "answer": "1991",
                "answer_aliases": [], "answerable": answerable} for answerable in (True, False)]
    rows = convert("musique", [write_jsonl(tmp_path / "musique.jsonl", records)])
    answerable, unanswerable = rows
    assert gold_text(answerable) == "1991"
    assert unanswerable["expected"]["answer"] == bs.NONE_KEY
    assert "1991" in distractor_texts(unanswerable)


# --------------------------------------------------------------------------------------------- 7. preference


def test_helpsteer2(tmp_path):
    records = [{"prompt": "What is C#?", "response": "A language.", "helpfulness": 3, "correctness": 4,
                "coherence": 4, "complexity": 1, "verbosity": 0},
               {"prompt": "Hi<extra_id_1>Assistant\nHello<extra_id_1>User\nMore", "response": "x", "helpfulness": 1,
                "correctness": 1, "coherence": 1, "complexity": 1, "verbosity": 1}]
    rows = convert("helpsteer2", [write_jsonl(tmp_path / "train.jsonl.gz", records, gz=True)])
    assert len(rows) == 1 and rows[0]["expected"]["helpfulness"] == "3"
    assert all(q["type"] == "score" and len(q["criteria"]) == 5 for q in rows[0]["questions"].values())


def test_helpsteer3_soft_and_single_turn(tmp_path):
    base = {"domain": "general", "language": "english", "response1": "Answer one.", "response2": "Answer two."}
    records = [dict(base, context=[{"role": "user", "content": "Question?"}], overall_preference=-2,
                    individual_preference=[{"score": -2}, {"score": -3}, {"score": 1}]),
               dict(base, context=[{"role": "user", "content": "Q"}, {"role": "assistant", "content": "A"},
                                   {"role": "user", "content": "Q2"}], overall_preference=1,
                    individual_preference=[])]
    rows = convert("helpsteer3", [write_jsonl(tmp_path / "train.jsonl.gz", records, gz=True)])
    assert len(rows) == 1
    target = rows[0]["expected"]["preferred"]
    first = rows[0]["questions"]["preferred"]["criteria"]["response_1"]
    p_one = target["response_1"] if first == "Answer one." else target["response_2"]
    assert p_one == pytest.approx((0.8 + 0.95 + 0.35) / 3, abs=1e-6)


def test_oasst2(parquet, tmp_path):
    def msg(mid, parent, role, text, rank=None, **kw):
        return {"message_id": mid, "parent_id": parent, "text": text, "role": role, "lang": "en",
                "review_result": True, "deleted": False, "rank": rank, "synthetic": False, **kw}

    parquet["o.parquet"] = [msg("p", None, "prompter", "How do I boil an egg?"),
                            msg("a1", "p", "assistant", "Boil it for 9 minutes.", 0),
                            msg("a2", "p", "assistant", "Eggs are nice.", 1),
                            msg("a3", "p", "assistant", "Spam.", 2, deleted=True)]
    rows = convert("oasst2", [tmp_path / "o.parquet"])
    assert len(rows) == 1 and gold_text(rows[0], "best_reply") == "Boil it for 9 minutes."
    assert "Spam." not in distractor_texts(rows[0], "best_reply")


def test_stack_exchange(parquet, tmp_path):
    path = tmp_path / "data" / "cooking.stackexchange.com" / "train-00000-of-00001.parquet"
    parquet[path.name] = [
        {"qid": 1, "question": "<p>How long to boil an egg?</p>", "answers": [
            {"answer_id": 10, "pm_score": 5, "text": "<p>About <b>9</b> minutes.</p>"},
            {"answer_id": 11, "pm_score": 1, "text": "<p>Ask someone.</p>"}]},
        {"qid": 2, "question": "<p>Tie?</p>", "answers": [{"answer_id": 12, "pm_score": 2, "text": "a"},
                                                          {"answer_id": 13, "pm_score": 2, "text": "b"}]},
    ]
    rows = convert("stack-exchange-prefs", [path])
    assert len(rows) == 1 and gold_text(rows[0], "better_answer") == "About 9 minutes."


# --------------------------------------------------------------------------------------------- 8. verification


def test_fever(tmp_path):
    records = [{"id": "1", "claim": "Tesla makes cars.", "label": "SUPPORTS",
                "evidence": [["Tesla,_Inc.", "0", "Tesla -LRB- formerly Tesla Motors -RRB- makes electric cars ."]]},
               {"id": "2", "claim": "X stars Y.", "label": "NOT ENOUGH INFO",
                "evidence": [["Other_film", "3", "It stars Z ."]]},
               {"id": "3", "claim": "No evidence.", "label": "REFUTES", "evidence": []}]
    rows = convert("fever", [write_jsonl(tmp_path / "train.jsonl", records)])
    assert len(rows) == 2
    assert rows[0]["state"]["evidence"] == ["Tesla, Inc.: Tesla (formerly Tesla Motors) makes electric cars."]
    nei = rows[1]
    assert nei["expected"]["verdict"] in ("NOT ENOUGH INFO", 0.0)


def test_tabfact(parquet, tmp_path):
    parquet["tables.parquet"] = [{"table_id": "1-1.html.csv", "table_text": "year#wins\n1994#3\n1995#1\n",
                                  "table_caption": "racing"}]
    tables = fetched("tabfact", [tmp_path / "tables.parquet"], bs.AUX_SOURCES["tabfact-tables"])
    r1 = write_json(tmp_path / "r1_training_all.json", {"1-1.html.csv": [["wins were 3 in 1994", "wins were 4"],
                                                                         [1, 0], "racing"],
                                                        "9-9.html.csv": [["x"], [1], "y"]})
    ids = write_json(tmp_path / "train_id.json", ["1-1.html.csv"])
    rows = convert("tabfact", [r1, ids], Ctx({"tabfact-tables": tables}))
    assert [r["expected"]["entailed"] for r in rows] == [1.0, 0.0]


# --------------------------------------------------------------------------------------------- 9. reading comprehension


def test_squad2_none(parquet, tmp_path):
    context = ("Beyonce was born in Houston, Texas in 1981. She rose to fame in Destiny's Child and released "
               "Dangerously in Love in 2003, which sold 11 million copies. She later toured Europe and Asia.")
    parquet["s.parquet"] = [
        {"id": "a", "title": "Beyonce", "context": context, "question": "In what year was Beyonce born?",
         "answers": {"text": ["1981"], "answer_start": [41]}},
        {"id": "b", "title": "Beyonce", "context": context, "question": "In what year did Beyonce retire?",
         "answers": {"text": [], "answer_start": []}},
    ]
    rows = {r["id"]: r for r in convert("squad2", [tmp_path / "s.parquet"])}
    assert gold_text(rows["squad2:a"]) == "1981"
    assert rows["squad2:b"]["expected"]["answer"] == bs.NONE_KEY


def test_condaqa(tmp_path):
    base = {"PassageID": 1, "PassageEditID": 0, "QuestionID": "q1", "sentence1": "He did not go.",
            "sentence2": "Did he go?"}
    records = [dict(base, SampleID=1, label="NO"), dict(base, SampleID=2, label="DON'T KNOW"),
               dict(base, SampleID=3, label="British")]
    rows = convert("condaqa", [write_jsonl(tmp_path / "train.json", records)])
    assert [r["expected"]["answer"] for r in rows] == ["no", "dont_know"]


def test_tydiqa(parquet, tmp_path, monkeypatch):
    monkeypatch.setattr(bs, "TYDI_NULL_KEEP", 1.0)
    passages = [f"Passage number {i} talks about topic {i} in some detail here." for i in range(8)]
    text = "\n".join(passages)
    starts, ends, pos = [], [], 0
    for p in passages:
        starts.append(len(text[:pos].encode()))
        ends.append(len(text[: pos + len(p)].encode()))
        pos += len(p) + 1

    def rec(url, gold, yes_no="NONE"):
        return {"passage_answer_candidates": {"plaintext_start_byte": starts, "plaintext_end_byte": ends},
                "question_text": "Is topic 3 detailed?", "document_title": "Topics", "language": "english",
                "annotations": {"passage_answer_candidate_index": [gold], "yes_no_answer": [yes_no]},
                "document_plaintext": text, "document_url": url}

    parquet["t.parquet"] = [rec("u1", 3, "YES"), rec("u2", -1)]
    rows = convert("tydiqa", [tmp_path / "t.parquet"])
    passage_rows = [r for r in rows if r["meta"]["task"].startswith("tydiqa/passage")]
    answerable = next(r for r in passage_rows if r["meta"]["answerable"])
    assert gold_text(answerable, "passage") == passages[3]
    null = next(r for r in passage_rows if not r["meta"]["answerable"])
    assert null["expected"]["passage"] == bs.NONE_KEY
    yesno = next(r for r in rows if r["meta"]["task"].startswith("tydiqa/yesno"))
    assert yesno["expected"]["answer"] == 1.0 and yesno["state"]["passage"] == passages[3]


# --------------------------------------------------------------------------------------------- 10. safety


def test_aegis2_human_labels_only(tmp_path):
    base = {"reconstruction_id_if_redacted": None, "prompt_label_source": "human"}
    records = [
        dict(base, id="1", prompt="How do I hurt someone?", response=None, prompt_label="unsafe",
             response_label=None, violated_categories="Violence", response_label_source=None),
        dict(base, id="2", prompt="Tell me a joke", response="Here is one.", prompt_label="safe",
             response_label="safe", violated_categories="", response_label_source="llm_jury"),
        dict(base, id="3", prompt="Write malware", response="Sure, here is code", prompt_label="unsafe",
             response_label="unsafe", violated_categories="Malware, Criminal Planning/Confessions",
             response_label_source="human"),
        dict(base, id="4", prompt="REDACTED", response=None, prompt_label="safe", response_label=None,
             violated_categories="", response_label_source=None),
    ]
    rows = {r["id"]: r for r in convert("aegis2", [write_json(tmp_path / "train.json", records)])}
    assert rows["aegis2:1"]["expected"] == {"unsafe": 1.0, "category": "Violence"}
    assert rows["aegis2:2"]["meta"]["task"] == "aegis2/prompt" and "assistant" not in json.dumps(
        rows["aegis2:2"]["state"])
    assert rows["aegis2:3"]["expected"]["category"] == {"Malware": 0.5, "Criminal Planning/Confessions": 0.5}
    assert "aegis2:4" not in rows


def test_civil_comments_soft(parquet, tmp_path):
    parquet["c.parquet"] = [{"text": f"comment number {i}", "toxicity": (i % 10) / 10, "insult": 0.1,
                             "threat": 0.0, "identity_attack": 0.0, "obscene": 0.0} for i in range(400)]
    rows = convert("civil-comments", [tmp_path / "c.parquet"])
    assert 5 < len(rows) < 120
    assert any(0 < r["expected"]["toxic"] < 1 for r in rows)


# --------------------------------------------------------------------------------------------- optional


def test_medmcqa_lexglue_multiwoz_csqa(parquet, tmp_path, monkeypatch):
    parquet["m.parquet"] = [{"id": "1", "question": "Q?", "opa": "a", "opb": "b", "opc": "c", "opd": "d", "cop": 2,
                             "choice_type": "single", "subject_name": "Anatomy"},
                            {"id": "2", "question": "Q?", "opa": "a", "opb": "a", "opc": "c", "opd": "d", "cop": 2,
                             "choice_type": "single", "subject_name": "Anatomy"}]
    assert [r["expected"]["answer"] for r in convert("medmcqa", [tmp_path / "m.parquet"])] == ["C"]

    monkeypatch.setattr(extra_sources, "class_names", lambda path: {"label": ["Waivers", "Governing Laws"]})
    files = [tmp_path / "ledgar" / "l.parquet", tmp_path / "unfair_tos" / "u.parquet",
             tmp_path / "case_hold" / "c.parquet"]
    parquet["l.parquet"] = [{"text": "This agreement is governed by Delaware law.", "label": 1}]
    parquet["u.parquet"] = [{"text": "We may terminate your account at any time.", "labels": [1]}]
    parquet["c.parquet"] = [{"context": "See Smith (<HOLDING>).", "endings": list("vwxyz"), "label": 4}]
    rows = {r["meta"]["task"]: r for r in convert("lexglue", files)}
    assert rows["lexglue/ledgar"]["expected"]["type"] == "Governing Laws"
    assert rows["lexglue/unfair_tos"]["expected"]["unilateral_termination"] == 1.0
    assert rows["lexglue/case_hold"]["expected"]["holding"] == "E"

    schema = write_json(tmp_path / "schema.json", [
        {"service_name": "hotel", "intents": [{"name": "find_hotel", "description": "find"},
                                              {"name": "book_hotel", "description": "book"}]},
        {"service_name": "taxi", "intents": [{"name": "book_taxi", "description": "taxi"}]}])

    def frame(service, intent):
        return {"service": service, "state": {"active_intent": intent}}

    dialogue = {"dialogue_id": "D1", "services": ["hotel"], "turns": [
        {"speaker": "USER", "utterance": "I need a hotel.", "frames": [frame("hotel", "find_hotel"),
                                                                       frame("taxi", "NONE")]},
        {"speaker": "SYSTEM", "utterance": "Sure.", "frames": []},
        {"speaker": "USER", "utterance": "Book it.", "frames": [frame("hotel", "book_hotel"), frame("taxi", "NONE")]}]}
    rows = convert("multiwoz22", [schema, write_json(tmp_path / "dialogues_001.json", [dialogue])])
    assert list(rows[0]["questions"]) == ["hotel"]
    assert rows[0]["expected"]["hotel"] in ("find_hotel", "book_hotel")

    parquet["q.parquet"] = [{"id": "x", "question": "Where do fish live?", "answerKey": "B",
                             "choices": {"label": list("ABCDE"), "text": ["desert", "water", "sky", "tree", "car"]}}]
    assert convert("commonsenseqa", [tmp_path / "q.parquet"])[0]["expected"]["answer"] == "B"
