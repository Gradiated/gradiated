"""Add Sonnet 5.5 and GPT-6.x root models to the PostHog env driver on fbf8 (idempotent).

    python3 patch_gpt_roots.py /opt/posthog-env

Roots: sonnet55 / haiku55 (production Anthropic path, claude-sonnet-5-5 / claude-haiku-5-5, adaptive thinking) and gpt-sol / gpt-terra /
gpt-luna (OpenAI chat completions through the CLIProxyAPI subscription proxy, native tool calling, reasoning effort
GPT_ROOT_EFFORT, default medium). GPT roots refuse to run without the proxy. Backups: *.before-gptroots-20261030.
"""

import sys

base = sys.argv[1]

p = f"{base}/agent_driver.py"
s = open(p).read()
if "GPT_ROOTS" not in s:
    s = s.replace(
        'ROOT_CHOICES = ("vllm", "anthropic", "opus", "k3", "k3-reasoning")',
        'ROOT_CHOICES = ("vllm", "anthropic", "opus", "k3", "k3-reasoning", "sonnet55", "gpt-sol", "gpt-terra", "gpt-luna")\n'
        "# [GPT ROOTS PATCH 2026-10-30] GPT roots through the CLIProxyAPI subscription proxy (OpenAI chat completions,\n"
        "# native tools). Revert: restore agent_driver.py.before-gptroots-20261030.\n"
        'GPT_ROOTS = {"gpt-sol": "gpt-6.1-sol", "gpt-terra": "gpt-6.1-terra", "gpt-luna": "gpt-6-luna"}\n'
        'GPT_ROOT_EFFORT = os.environ.get("GPT_ROOT_EFFORT", "medium")',
        1,
    )
    s = s.replace(
        "    raise ValueError(root)\n\n\n_ROOT_CLASS",
        "    if root in GPT_ROOTS:\n"
        "        import llm_proxy\n\n"
        '        return RootConfig(root, GPT_ROOTS[root], f"{llm_proxy.PROXY_BASE}/v1", "OPENAI_API_KEY", emulate_tools=False,\n'
        "                          max_tokens=32768, temperature=None, extra_body={}, reasoning_effort=GPT_ROOT_EFFORT,\n"
        "                          max_retries=6, timeout=900.0)\n"
        "    raise ValueError(root)\n\n\n_ROOT_CLASS",
        1,
    )
    s = s.replace(
        '    elif root == "opus":\n        mark_anthropic_root("claude-opus-5-5")\n    else:',
        '    elif root == "opus":\n        mark_anthropic_root("claude-opus-5-5")\n'
        '    elif root == "sonnet55":\n        mark_anthropic_root("claude-sonnet-5-5")\n    else:',
        1,
    )
    s = s.replace(
        '    load_key("ANTHROPIC_API_KEY", required=(root in ("anthropic", "opus")))',
        '    load_key("ANTHROPIC_API_KEY", required=(root in ("anthropic", "opus", "sonnet55")))\n'
        "    if root in GPT_ROOTS and not via_proxy:\n"
        '        raise RuntimeError("GPT roots run only through the subscription proxy (POSTHOG_ENV_LLM_VIA_PROXY=1)")',
        1,
    )
    assert s.count("GPT_ROOTS") == 4 and 'mark_anthropic_root("claude-sonnet-5-5")' in s, "driver patch did not apply"
    open(p, "w").write(s)

p = f"{base}/runner/runner_common.py"
s = open(p).read()
if '"gpt-sol"' not in s:
    anchor = '    "opus": {"root": "opus", "submodels": "openai", "label": "Claude Opus 5.5 (production path, adaptive thinking)"},\n'
    assert anchor in s, "runner_common anchor missing"
    s = s.replace(anchor, anchor + (
        '    "sonnet55": {"root": "sonnet55", "submodels": "openai", "label": "Claude Sonnet 5.5 (production path, adaptive thinking)"},\n'
        '    "gpt-sol": {"root": "gpt-sol", "submodels": "openai", "label": "GPT-6.1 Sol root (proxy, native tools, effort medium)"},\n'
        '    "gpt-terra": {"root": "gpt-terra", "submodels": "openai", "label": "GPT-6.1 Terra root (proxy, native tools, effort medium)"},\n'
        '    "gpt-luna": {"root": "gpt-luna", "submodels": "openai", "label": "GPT-6 Luna root (proxy, native tools, effort medium)"},\n'), 1)
    open(p, "w").write(s)
# Haiku 5.5 root (added after the first patch; idempotent on its own).
p = f"{base}/agent_driver.py"
s = open(p).read()
if '"haiku55"' not in s:
    s = s.replace('"gpt-sol", "gpt-terra", "gpt-luna")\n', '"gpt-sol", "gpt-terra", "gpt-luna", "haiku55")\n', 1)
    s = s.replace('    elif root == "sonnet55":\n        mark_anthropic_root("claude-sonnet-5-5")\n',
                  '    elif root == "sonnet55":\n        mark_anthropic_root("claude-sonnet-5-5")\n'
                  '    elif root == "haiku55":\n        mark_anthropic_root("claude-haiku-5-5")\n', 1)
    s = s.replace('required=(root in ("anthropic", "opus", "sonnet55"))', 'required=(root in ("anthropic", "opus", "sonnet55", "haiku55"))', 1)
    assert s.count('"haiku55"') == 3, "haiku patch did not apply"
    open(p, "w").write(s)
p = f"{base}/runner/runner_common.py"
s = open(p).read()
if '"haiku55"' not in s:
    anchor = '    "gpt-sol": {"root": "gpt-sol"'
    assert anchor in s
    s = s.replace(anchor, '    "haiku55": {"root": "haiku55", "submodels": "openai", "label": "Claude Haiku 5.5 (production path, adaptive thinking)"},\n' + anchor, 1)
    open(p, "w").write(s)
print("patched")
