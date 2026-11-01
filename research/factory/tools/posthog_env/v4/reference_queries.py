"""Normalize a literal team scope without rewriting business values in reference SQL."""

import re


QUOTED = re.compile(r"'(?:''|\\.|[^'\\])*'|\"(?:\"\"|\\.|[^\"\\])*\"|`(?:``|[^`])*`|--[^\n]*|/\*.*?\*/", re.S)


def normalize_team(sql: str, team: int) -> str:
    pattern = re.compile(rf"(?<![\w.])((?:[a-zA-Z_]\w*\.)?team_id\s*=\s*){int(team)}(?![\w.])", re.I)
    out, end = [], 0
    for token in QUOTED.finditer(sql):
        out.extend((pattern.sub(r"\g<1>{team}", sql[end:token.start()]), token.group()))
        end = token.end()
    out.append(pattern.sub(r"\g<1>{team}", sql[end:]))
    return "".join(out)
