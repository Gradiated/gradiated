"""Discover public repository candidates with license and fork metadata."""

import argparse
import json
import subprocess
import sys
import time
from collections import Counter

LANGUAGES = (
    "C",
    "C++",
    "Rust",
    "Go",
    "Python",
    "Java",
    "TypeScript",
    "JavaScript",
    "PHP",
    "Ruby",
    "C#",
    "Kotlin",
    "Swift",
    "Scala",
    "Erlang",
    "Elixir",
    "Lua",
    "Dart",
    "Haskell",
    "OCaml",
    "Clojure",
    "Zig",
)
LICENSES = {
    "MIT",
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "ISC",
    "0BSD",
    "Unlicense",
    "BSL-1.0",
    "Zlib",
    "MPL-2.0",
}
SEEDS = """
git/git qemu/qemu FFmpeg/FFmpeg php/php-src phpmyadmin/phpmyadmin rust-lang/rust
u-boot/u-boot qt/qtbase erlang/otp openjdk/jdk bitcoin/bitcoin apache/cloudberry
ceph/ceph godotengine/godot TrinityCore/TrinityCore odoo/odoo swiftlang/swift
llvm/llvm-project swiftlang/llvm-project percona/percona-server MariaDB/server
kubernetes/kubernetes nextcloud/server moby/moby systemd/systemd torvalds/linux
apache/arrow apache/spark apache/kafka apache/flink huggingface/transformers
django/django ruby/ruby golang/go microsoft/vscode dotnet/runtime
dotnet/roslyn ziglang/zig zigtools/zls neovim/neovim vim/vim
curl/curl sqlite/sqlite python/cpython postgres/postgres llvm/llvm-project
nix-community/home-manager nixos/nixpkgs apache/netbeans rails/rails
""".split()


def api(path, *params):
    for attempt in range(3):
        p = subprocess.run(
            ["gh", "api", "--method", "GET", path, *params],
            timeout=40,
            capture_output=True,
            text=True,
        )
        if p.returncode == 0:
            return json.loads(p.stdout)
        if "limit" in p.stderr.lower() and attempt < 2:
            time.sleep(18)
        else:
            raise RuntimeError(
                f"GitHub request failed: {path}: {p.stderr.strip()[:180]}"
            )
    raise RuntimeError(f"GitHub request rate limited: {path}")


def entry(repo, index):
    spdx = (repo.get("license") or {}).get("spdx_id")
    if spdx not in LICENSES or repo["private"] or repo["fork"] or repo["size"] == 0:
        return None
    return dict(
        id=repo["id"],
        repo=repo["full_name"],
        branch=repo["default_branch"],
        license=spdx,
        language=repo.get("language") or "unknown",
        stars=repo["stargazers_count"],
        size_kib=repo["size"],
        priority=index,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--per-language", type=int, default=70, choices=range(1, 101), metavar="1..100"
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--exclude", help="existing repository manifest to skip")
    parser.add_argument(
        "--sort", choices=("stars", "updated", "forks"), default="stars"
    )
    args = parser.parse_args()
    rows = {}
    excluded = set()
    if args.exclude:
        with open(args.exclude) as stream:
            excluded = {r["id"] for r in map(json.loads, stream)}
    for name in dict.fromkeys(SEEDS) if not excluded else ():
        try:
            row = entry(api(f"repos/{name}"), 0)
        except RuntimeError as error:
            print(error, file=sys.stderr)
            continue
        if row:
            rows[row["id"]] = row
    for language in LANGUAGES:
        minimum_size = 500 if excluded else 1
        query = f'language:"{language}" stars:>=50 fork:false is:public size:{minimum_size}..6000000'
        try:
            result = api(
                "search/repositories",
                "-f",
                f"q={query}",
                "-f",
                f"sort={args.sort}",
                "-F",
                f"per_page={args.per_language}",
            )
        except RuntimeError as error:
            print(error, file=sys.stderr)
            continue
        for position, repo in enumerate(result["items"], 1):
            row = entry(repo, position)
            if row and row["id"] not in excluded:
                rows.setdefault(row["id"], row)
    if len(rows) < 50:
        raise RuntimeError(
            f"Discovery returned too few eligible repositories ({len(rows)})"
        )
    output = sorted(
        rows.values(), key=lambda r: (r["priority"], -r["stars"], r["repo"])
    )
    with open(args.output, "w") as f:
        for row in output:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
    print(
        json.dumps(
            {
                "repos": len(output),
                "languages": dict(Counter(r["language"] for r in output)),
            }
        )
    )


if __name__ == "__main__":
    main()
