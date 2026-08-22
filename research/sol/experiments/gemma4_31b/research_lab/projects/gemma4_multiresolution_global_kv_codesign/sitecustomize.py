import os

if os.environ.get("GLOBAL_KV_HOOK") == "1":
    import global_kv_sglang_hook  # noqa: F401
