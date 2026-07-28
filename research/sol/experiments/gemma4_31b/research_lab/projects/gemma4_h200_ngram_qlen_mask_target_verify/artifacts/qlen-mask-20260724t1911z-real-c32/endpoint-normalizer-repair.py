control_semantics = parse_sse(CONTROL)
candidate_semantics = parse_sse(OUT / "candidate")
token_ids_available = (
    len(control_semantics) == 32
    and len(candidate_semantics) == 32
    and all(row["token_ids"] for row in control_semantics)
    and all(row["token_ids"] for row in candidate_semantics)
)
first_token_ids_match = token_ids_available and (
    [row["token_ids"][0] for row in control_semantics]
    == [row["token_ids"][0] for row in candidate_semantics]
)
