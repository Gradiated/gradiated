import argparse
import logging
import runpy
from functools import wraps


def install_dispatch_hooks(manager):
    from middleware import mark_generation_started

    def wrap(original):
        @wraps(original)
        async def dispatched(self, *args, **kwargs):
            result = await original(self, *args, **kwargs)
            try:
                mark_generation_started()
            except Exception:
                pass
            return result
        return dispatched

    methods = ['_send_one_request', '_send_batch_request']
    originals = [getattr(manager, name) for name in methods]
    for name, original in zip(methods, originals):
        setattr(manager, name, wrap(original))


def main():
    try:
        # Separate tokenizer processes cannot safely divide one GPU power budget.
        parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
        parser.add_argument('--tokenizer-worker-num', type=int, default=1)
        options, _ = parser.parse_known_args()
        if options.tokenizer_worker_num == 1:
            from sglang.srt.entrypoints.http_server import app
            from sglang.srt.managers.tokenizer_manager import TokenizerManager
            from middleware import EnergyMiddleware

            install_dispatch_hooks(TokenizerManager)
            app.add_middleware(EnergyMiddleware)
    except Exception:
        logging.getLogger(__name__).warning('GPU energy estimates unavailable', exc_info=True)

    runpy.run_module('sglang.launch_server', run_name='__main__')


if __name__ == '__main__':
    main()
