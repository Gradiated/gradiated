import importlib.util
import io
import json
from pathlib import Path
import sys
import time
import types
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('kimi_launch', HERE / 'launch.py')
launch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launch)


def stream(*events, done=True):
    body = b''.join(b'data: ' + json.dumps(event).encode() + b'\n\n' for event in events)
    return io.BytesIO(body + (b'data: [DONE]\n\n' if done else b''))


class Warmup(unittest.TestCase):
    def test_reasoning_stream_and_usage_qualify_without_cache_reporting(self):
        output = stream({'choices': [{'delta': {'reasoning_content': 'Let me calculate.'}}]},
                        {'usage': {'prompt_tokens': 40, 'completion_tokens': 4}, 'choices': []})
        with patch.object(launch.urllib.request, 'urlopen', return_value=output) as open_request:
            result = launch.Supervisor(['unused']).probe(32, 5)
        self.assertEqual(result['prompt_tokens'], 40)
        payload = json.loads(open_request.call_args.args[0].data)
        self.assertEqual(payload['model'], launch.MODEL)
        self.assertTrue(payload['stream_options']['include_usage'])

    def test_probe_uses_selected_served_model_name(self):
        output = stream({'choices': [{'delta': {'reasoning_content': 'ok'}}]},
                        {'usage': {'prompt_tokens': 40, 'completion_tokens': 4}, 'choices': []})
        supervisor = launch.Supervisor(
            ['unused'],
            tokenizer_path='yetalabs/Kimi-K3.1-Pro-abliterated',
            revision='0911ef0765f49d26dfa25bb0d071f29463f8000b',
            served_model_name='yetalabs/Kimi-K3.1-Pro-abliterated',
        )
        with patch.object(launch.urllib.request, 'urlopen', return_value=output) as open_request:
            supervisor.probe(32, 5)
        payload = json.loads(open_request.call_args.args[0].data)
        self.assertEqual(payload['model'], 'yetalabs/Kimi-K3.1-Pro-abliterated')

    def test_truncated_empty_and_error_streams_do_not_qualify(self):
        for output in [stream({'choices': [{'delta': {'content': 'hello'}}]}, done=False),
                       stream({'usage': {'prompt_tokens': 40, 'completion_tokens': 0}}),
                       stream({'error': {'message': 'failed'}})]:
            with self.subTest(output=output), patch.object(launch.urllib.request, 'urlopen', return_value=output):
                with self.assertRaises(RuntimeError):
                    launch.Supervisor(['unused']).probe(32, 5)



class RuntimeHealth(unittest.TestCase):
    def supervisor(self):
        supervisor = launch.Supervisor(['unused'], runtime_url='http://127.0.0.1:30000',
                                       backend_url='http://127.0.0.1:30004')
        supervisor.child = Mock()
        supervisor.child.poll.return_value = None
        supervisor.qualified.set()
        return supervisor

    def test_ready_requires_router_readiness_and_scheduler_progress(self):
        supervisor = self.supervisor()
        responses = [Mock(status=200), Mock(status=200)]
        for response in responses:
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
        with patch.object(launch.urllib.request, 'urlopen', side_effect=responses) as opened:
            self.assertTrue(supervisor.ready())
        self.assertEqual([call.args[0] for call in opened.call_args_list],
                         ['http://127.0.0.1:30000/readiness',
                          'http://127.0.0.1:30004/health_generate'])
        self.assertTrue(all(call.kwargs['timeout'] == 2 for call in opened.call_args_list))

    def test_healthy_router_cannot_hide_a_stalled_or_failed_scheduler(self):
        for failure in [TimeoutError('scheduler stalled'), OSError('backend unavailable')]:
            router = Mock(status=200)
            router.__enter__ = Mock(return_value=router)
            router.__exit__ = Mock(return_value=False)
            with self.subTest(failure=failure), patch.object(
                    launch.urllib.request, 'urlopen', side_effect=[router, failure]):
                self.assertFalse(self.supervisor().ready())

    def test_scheduler_must_report_success(self):
        router, scheduler = Mock(status=200), Mock(status=503)
        for response in [router, scheduler]:
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
        with patch.object(launch.urllib.request, 'urlopen', side_effect=[router, scheduler]):
            self.assertFalse(self.supervisor().ready())

    def test_dead_child_or_unready_router_never_probes_scheduler(self):
        supervisor = self.supervisor()
        supervisor.child.poll.return_value = 1
        with patch.object(launch.urllib.request, 'urlopen') as opened:
            self.assertFalse(supervisor.ready())
        opened.assert_not_called()
        router = Mock(status=503)
        router.__enter__ = Mock(return_value=router)
        router.__exit__ = Mock(return_value=False)
        with patch.object(launch.urllib.request, 'urlopen', return_value=router) as opened:
            self.assertFalse(self.supervisor().ready())
        self.assertEqual(opened.call_count, 1)


class ExtraWarmup(unittest.TestCase):
    def supervisor(self, cap=3):
        return launch.Supervisor(['unused'], backend_url='http://127.0.0.1:30004', active_requests=cap,
                                 tokenizer_path='/pinned/checkpoint', max_queued_requests=cap+2)

    def test_concurrency_counts_include_non_power_of_two_admission_cap(self):
        for cap, expected in [(1, (1,)), (3, (1, 2, 3)), (4, (1, 2, 4)), (6, (1, 2, 4, 6))]:
            self.assertEqual(launch.startup_concurrencies(cap), expected)
        for invalid in (0, -1, True, 1.5, '3'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                launch.startup_concurrencies(invalid)

    def test_seed_zero_is_preserved_with_production_sampling_defaults(self):
        make = lambda: stream({'choices': [{'delta': {'reasoning_content': 'synthetic'}}]},
                             {'usage': {'prompt_tokens': 40, 'completion_tokens': 4}})
        with patch.object(launch.urllib.request, 'urlopen', side_effect=[make(), make()]) as opened:
            self.supervisor().probe(32, 5, seed=0)
            self.supervisor().probe(32, 5)
        payloads = [json.loads(call.args[0].data) for call in opened.call_args_list]
        self.assertEqual(payloads[0]['seed'], 0)
        self.assertNotIn('seed', payloads[1])
        for payload in payloads:
            self.assertEqual((payload['temperature'], payload['top_p'], payload['reasoning_effort']), (1., .95, 'max'))

    def test_native_probe_requires_real_counts_and_private_backend(self):
        valid = {'prompt_tokens': 129, 'cached_tokens': 128, 'completion_tokens': 4,
                 'finish_reason': {'type': 'length'}}
        for changed in ({}, {'prompt_tokens': 128}, {'cached_tokens': None}, {'cached_tokens': 130},
                        {'completion_tokens': None}, {'completion_tokens': 0}, {'completion_tokens': 5},
                        {'finish_reason': {'type': 'abort'}}):
            body = io.BytesIO(json.dumps({'text': 'not logged', 'meta_info': {**valid, **changed}}).encode())
            with self.subTest(changed=changed), patch.object(launch.urllib.request, 'urlopen', return_value=body) as opened:
                if changed:
                    with self.assertRaises(RuntimeError):
                        self.supervisor().native_probe([11]*129, 5)
                else:
                    result = self.supervisor().native_probe([11]*129, 5)
                    self.assertEqual((result['prompt_tokens'], result['cached_tokens']), (129, 128))
                    self.assertTrue(opened.call_args.args[0].full_url.endswith('/generate'))
                    self.assertNotIn('text', result)
        no_backend = launch.Supervisor(['unused'], active_requests=3)
        with self.assertRaisesRegex(RuntimeError, 'private backend'):
            no_backend.native_probe([11], 5)

    def test_cache_geometry_matches_all_reported_schedulers(self):
        for dcp, prefix in ((1, 128), (8, 1024)):
            state = {'page_size': 64, 'dcp_size': dcp}
            self.assertEqual(launch.cache_geometry({**state, 'internal_states': [state, state]})['prefix_tokens'], prefix)
        valid = {'page_size': 64, 'dcp_size': 8}
        invalids = [None, [], {}, {**valid, 'internal_states': []},
                    {**valid, 'internal_states': [{**valid, 'dcp_size': 1}]},
                    {**valid, 'internal_states': [{**valid, 'page_size': True}]},
                    {**valid, 'internal_states': [{**valid, 'dcp_size': 0}]},
                    {**valid, 'internal_states': [None]},
                    {'page_size': 65536, 'dcp_size': 1, 'internal_states': [{'page_size': 65536, 'dcp_size': 1}]}]
        for info in invalids:
            with self.subTest(info=info), self.assertRaises(RuntimeError):
                launch.cache_geometry(info)

    def test_geometry_is_read_from_private_backend_with_startup_deadline(self):
        supervisor = self.supervisor()
        supervisor.remaining = Mock(return_value=7)
        state = {'page_size': 64, 'dcp_size': 8}
        body = io.BytesIO(json.dumps({**state, 'internal_states': [state]}).encode())
        with patch.object(launch.urllib.request, 'urlopen', return_value=body) as opened:
            self.assertEqual(supervisor.read_cache_geometry()['cache_quantum'], 512)
        self.assertEqual(opened.call_args.args[0], 'http://127.0.0.1:30004/server_info')
        self.assertEqual(opened.call_args.kwargs['timeout'], 7)
        self.assertEqual([call.args[0] for call in supervisor.remaining.call_args_list], [25, 1])

    def test_dcp_prefix_rendering_is_exact_bounded_and_deadline_checked(self):
        supervisor = self.supervisor()
        supervisor.remaining = Mock(return_value=1)
        tokenizer = Mock()
        tokenizer.apply_chat_template.side_effect = lambda messages, **kw: [11] * (40 + messages[0]['content'].count(' x'))
        self.assertEqual(len(supervisor.cached_prefix(tokenizer, 1024)), 1024)
        self.assertEqual(tokenizer.apply_chat_template.call_count, 2)
        tokenizer.apply_chat_template.side_effect = lambda *a, **k: [11] * 40
        with self.assertRaises(RuntimeError):
            supervisor.cached_prefix(tokenizer, 1024)
        self.assertLessEqual(tokenizer.apply_chat_template.call_count, 34)

    def test_dcp_cached_shapes_use_global_quantum(self):
        supervisor = self.supervisor()
        supervisor.read_cache_geometry = Mock(return_value={'prefix_tokens': 1024})
        supervisor.load_tokenizer = Mock(return_value=types.SimpleNamespace(encode=lambda *a, **k: [17]))
        supervisor.cached_prefix = Mock(return_value=[11]*1024)
        supervisor.native_probe = Mock(side_effect=lambda ids, timeout: {
            'prompt_tokens': len(ids), 'cached_tokens': 1024})
        supervisor.warm_cached_prefills()
        self.assertEqual([len(call.args[0]) for call in supervisor.native_probe.call_args_list],
                         [n for n in range(1025, 1029) for _ in range(3)])
        supervisor.cached_prefix.assert_called_with(supervisor.load_tokenizer.return_value, 1024)

    def test_cached_shapes_are_exercised_and_rechecked_with_actual_cache_counts(self):
        supervisor = self.supervisor()
        tokenizer = types.SimpleNamespace(encode=Mock(return_value=[17]))
        supervisor.load_tokenizer = Mock(return_value=tokenizer)
        supervisor.read_cache_geometry = Mock(return_value={'prefix_tokens': 128})
        supervisor.cached_prefix = Mock(return_value=[11]*128)
        supervisor.native_probe = Mock(side_effect=lambda ids, timeout: {
            'prompt_tokens': len(ids), 'cached_tokens': 128, 'completion_tokens': 4, 'elapsed_seconds': .1})
        supervisor.warm_cached_prefills()
        calls = supervisor.native_probe.call_args_list
        self.assertEqual([len(call.args[0]) for call in calls], [n for n in (129, 130, 131, 132) for _ in range(3)])
        self.assertEqual([call.args[1] for call in calls], [180, 180, 25]*4)
        self.assertTrue(all(call.args[0][:128] == [11]*128 for call in calls))

    def test_cold_hybrid_prefix_is_reprimed_until_fully_cached(self):
        supervisor = self.supervisor()
        supervisor.load_tokenizer = Mock(return_value=types.SimpleNamespace(encode=lambda *a, **k: [17]))
        supervisor.read_cache_geometry = Mock(return_value={'prefix_tokens': 128})
        supervisor.cached_prefix = Mock(return_value=[11]*128)
        hits = iter([0, 64, 128, 128, 128] + [64, 128, 128, 128]*3)
        supervisor.native_probe = Mock(side_effect=lambda ids, timeout: {
            'prompt_tokens': len(ids), 'cached_tokens': next(hits)})
        supervisor.warm_cached_prefills()
        self.assertEqual(supervisor.native_probe.call_count, 5 + 4*3)

    def test_unprimeable_prefix_fails_closed(self):
        supervisor = self.supervisor()
        supervisor.load_tokenizer = Mock(return_value=types.SimpleNamespace(encode=lambda *a, **k: [17]))
        supervisor.read_cache_geometry = Mock(return_value={'prefix_tokens': 128})
        supervisor.cached_prefix = Mock(return_value=[11]*128)
        supervisor.native_probe = Mock(return_value={'prompt_tokens': 129, 'cached_tokens': 64})
        with self.assertRaisesRegex(RuntimeError, 'new-token shape'):
            supervisor.warm_cached_prefills()
        self.assertEqual(supervisor.native_probe.call_count, 4)

    def test_cached_shape_mismatch_fails_closed(self):
        supervisor = self.supervisor()
        supervisor.load_tokenizer = Mock(return_value=types.SimpleNamespace(encode=lambda *a, **k: [17]))
        supervisor.read_cache_geometry = Mock(return_value={'prefix_tokens': 128})
        supervisor.cached_prefix = Mock(return_value=[11]*128)
        supervisor.native_probe = Mock(return_value={'prompt_tokens': 129, 'cached_tokens': 127})
        with self.assertRaisesRegex(RuntimeError, 'new-token shape'):
            supervisor.warm_cached_prefills()
        self.assertFalse(supervisor.ready())

    def test_seeded_sampling_covers_every_batch_size_and_mixed_rows(self):
        for cap in (1, 3, 6):
            supervisor = self.supervisor(cap)
            supervisor.probe, supervisor.seeded_group = Mock(), Mock()
            supervisor.warm_seeded_sampling()
            self.assertEqual([call.kwargs['seed'] for call in supervisor.probe.call_args_list], [0, 1])
            counts = [len(call.args[1]) for call in supervisor.seeded_group.call_args_list]
            self.assertEqual(counts, [count for count in range(1, cap + 1) for _ in range(6)])
            seeds = [seed for call in supervisor.seeded_group.call_args_list for seed in call.args[1]]
            self.assertIn(0, seeds)
            self.assertIn(None, seeds)

    def test_seeded_group_runs_requested_batch_size_within_active_cap(self):
        supervisor = self.supervisor(3)
        supervisor.probe = Mock(return_value={'prompt_tokens': 40, 'elapsed_seconds': .1})
        result = supervisor.seeded_group('unit_mixed', [0, None, 1], 5)
        self.assertEqual(len(result), 3)
        self.assertCountEqual([call.kwargs['seed'] for call in supervisor.probe.call_args_list], [0, None, 1])
        self.assertEqual(len(supervisor.seeded_group('smaller', [0, None], 5)), 2)
        for seeds in ([], [0, None, 1, 0]):
            with self.assertRaisesRegex(RuntimeError, 'within its active request limit'):
                supervisor.seeded_group('bad', seeds, 5)

    def test_legacy_probe_groups_never_exceed_active_cap(self):
        supervisor = self.supervisor(2)
        seen = []
        def group(_self, phase, shapes, timeout):
            seen.append(len(shapes))
            return [{'prompt_tokens': word} for word in shapes]
        with patch.object(launch.base.Supervisor, 'probe_group', group):
            results = supervisor.probe_group('mixed', [32, 8192, 8192], 5)
        self.assertEqual(seen, [2, 1])
        self.assertEqual(len(results), 3)

    def test_all_extra_paths_complete_before_base_can_publish_readiness(self):
        supervisor = self.supervisor(3)
        previous = launch.base.CONCURRENCIES
        order = []
        supervisor.health = Mock(return_value=True)
        supervisor.qualified.set()
        def extra(name):
            def run():
                self.assertFalse(supervisor.qualified.is_set())
                order.append(name)
            return run
        supervisor.warm_cached_prefills = extra('cache')
        supervisor.warm_seeded_sampling = extra('seed')
        def base_warmup(instance):
            self.assertEqual(launch.base.CONCURRENCIES, (1, 2, 3))
            self.assertFalse(instance.qualified.is_set())
            order.append('legacy'); instance.qualified.set()
        with patch.object(launch.base.Supervisor, 'warmup', base_warmup):
            supervisor.warmup()
        self.assertEqual(order, ['cache', 'seed', 'legacy'])
        self.assertTrue(supervisor.ready())
        self.assertEqual(launch.base.CONCURRENCIES, previous)

    def test_extra_failure_and_expired_startup_never_publish_readiness(self):
        for expired in (False, True):
            supervisor = self.supervisor()
            supervisor.qualified.set()
            supervisor.health = Mock(return_value=not expired)
            supervisor.warm_cached_prefills = Mock(side_effect=RuntimeError('missing token counts'))
            if expired: supervisor.deadline = time.monotonic()-1
            with patch.object(launch.base.Supervisor, 'warmup') as legacy:
                with self.assertRaises(RuntimeError): supervisor.warmup()
            legacy.assert_not_called()
            self.assertFalse(supervisor.qualified.is_set())

    def test_expired_native_probe_opens_no_network_connection(self):
        supervisor = self.supervisor(); supervisor.deadline = time.monotonic()-1
        with patch.object(launch.urllib.request, 'urlopen') as opened:
            with self.assertRaisesRegex(RuntimeError, 'startup deadline'):
                supervisor.native_probe([11], 5)
        opened.assert_not_called()



if __name__ == '__main__':
    unittest.main()
