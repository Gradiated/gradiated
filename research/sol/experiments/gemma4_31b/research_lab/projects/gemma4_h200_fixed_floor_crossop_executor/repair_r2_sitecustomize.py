"""Standalone SGLang scheduler context needed by the direct component consumer."""

from sglang.srt.server_args import set_global_server_args_for_scheduler


class StandaloneServerArgs:
    rl_on_policy_target = None


set_global_server_args_for_scheduler(StandaloneServerArgs())
