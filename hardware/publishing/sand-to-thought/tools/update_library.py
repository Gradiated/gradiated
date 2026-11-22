#!/usr/bin/env python3
"""Refresh only the marked coverage table from readable per-post plan tables."""
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit
import re

ROOT = Path(__file__).resolve().parent.parent
START, END = '<!-- coverage:start -->', '<!-- coverage:end -->'


def marked(text, path):
    if text.count(START) != 1 or text.count(END) != 1:
        raise ValueError(f'{path}: expected exactly one coverage marker pair')
    before, rest = text.split(START)
    body, after = rest.split(END)
    return before, body, after


def main():
    rows = []
    for plan in sorted((ROOT / 'articles').glob('*/plan.md')):
        text = plan.read_text()
        if START not in text and END not in text:
            continue
        _, body, _ = marked(text, plan)
        title = re.search(r'^# (.+)$', text, re.M)
        status = re.search(r'^\*\*Status:\*\* (.+)$', text, re.M)
        if not title or not status:
            raise ValueError(f'{plan}: missing title or Status line')
        post_link = f'[{title[1]}]({quote("../" + plan.relative_to(ROOT).as_posix())}#topic-coverage)'
        for line in body.splitlines():
            if not line.startswith('|'):
                continue
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            if cells[0] == 'Subject' or re.fullmatch(r'[-: ]+', cells[0]):
                continue
            if len(cells) != 4:
                raise ValueError(f'{plan}: expected four coverage columns: {line}')
            subject, topic, depth, _ = cells
            if depth not in ('Introduced', 'Explained', 'Worked'):
                raise ValueError(f'{plan}: unknown coverage depth {depth!r}')
            match = re.fullmatch(r'\[([^]]+)\]\(([^)]+)\)', topic)
            if not match:
                raise ValueError(f'{plan}: topic must link to its definition')
            parsed = urlsplit(match[2])
            target = (plan.parent / unquote(parsed.path)).resolve()
            if parsed.scheme or not target.is_file() or target != ROOT / 'shared/topics.md':
                raise ValueError(f'{plan}: topic must point to TOPICS.md')
            link = quote(target.name)
            if parsed.fragment:
                link += '#' + parsed.fragment
            topic_link = f'[{match[1]}]({link})'
            rows.append(f'| {subject} | {topic_link} | {post_link} | {depth} | {status[1]} |')
    library = ROOT / 'shared/library.md'
    original = library.read_text()
    before, _, after = marked(original, library)
    table = '\n'.join([
        '| Subject | Topic | Post | Depth | Status |',
        '| --- | --- | --- | --- | --- |',
        *rows,
    ]) if rows else 'No article coverage recorded yet.'
    updated = before + START + '\n' + table + '\n' + END + after
    if updated != original:
        library.write_text(updated)
    print(f'Coverage summary refreshed: {len(rows)} entries.')


if __name__ == '__main__':
    main()
