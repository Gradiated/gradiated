import sqlite3

import pytest
from release_export import apply_override, select


def test_component_cap_and_global_holdout():
    db = sqlite3.connect(":memory:")
    db.executescript("""
        CREATE TABLE items(n INTEGER PRIMARY KEY,family TEXT,kind TEXT,language TEXT,input_key BLOB);
        CREATE TABLE disposition(n INTEGER PRIMARY KEY,component INTEGER,partition TEXT,eligible INTEGER);
    """)
    for n in range(40):
        db.execute(
            "INSERT INTO items VALUES(?,?,?,?,?)",
            (
                n,
                "train-family" if n < 30 else "dev-family",
                "noul",
                "en",
                str(n).encode(),
            ),
        )
        db.execute(
            "INSERT INTO disposition VALUES(?,?,?,1)",
            (n, 0 if n < 30 else 1, "train" if n < 30 else "dev"),
        )
    select(db)
    assert db.execute(
        "SELECT partition,COUNT(*) FROM chosen GROUP BY partition ORDER BY partition"
    ).fetchall() == [("dev", 1), ("train", 16)]


def test_legacy_eikos_terms_and_unknown_original_split():
    row = {
        "source": "caiovicentino1/eikos-decisions",
        "id": "x",
        "license": "cc-by-4.0",
    }
    corrected = apply_override(
        row,
        {
            "rows": {
                "x": {"license": "mit,cc-by-4.0", "attribution": {"upstream": "gsm8k"}}
            }
        },
    )
    assert corrected["license"] == "mit,cc-by-4.0"
    assert (
        apply_override(row, {"rows": {"x": {"reject": "unverified_train_split"}}})
        is None
    )
    with pytest.raises(KeyError):
        apply_override(row, {"rows": {}})
