"""compute_usage cost events: the arithmetic, idempotent intervals, and metering VMs from the local ledger."""

import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import _path  # noqa: F401
from gradctl import usage
from gradctl.compute import commands

T0 = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


def vm(state='RUNNING', **extra):
    return {'name': 'train-1', 'id': 'r-1', 'region': 'us-east', 'state': state, 'term': 'spot',
            'gpu_type': 'nvidia_b300', 'gpus': 8, 'usd_per_gpu_hour': 7.5, 'created_at': None, **extra}


class Event(unittest.TestCase):
    def make(self, state='RUNNING', hours=2.0):
        return usage.event(customer='bild-ai', stage='training', run_id='run-1', workstream='bildy', provider='ornn',
                           resource_name='train-1', resource_id='r-1', region='us-east', term='spot',
                           gpu_type='nvidia_b300', gpu_count=8, usd_per_hour=60.0, price_source='ornn_reservation',
                           start=T0, end=T0 + timedelta(hours=hours), vm_state=state, source='test')

    def test_cost_and_gpu_hours_follow_the_interval_and_price(self):
        p = self.make()['properties']
        self.assertEqual((p['cost_usd'], p['gpu_hours'], p['usd_per_gpu_hour']), (120.0, 16.0, 7.5))
        self.assertEqual(self.make()['distinct_id'], 'bild-ai')

    def test_a_stopped_vm_costs_nothing_for_gpu_time(self):
        p = self.make(state='STOPPED')['properties']
        self.assertEqual((p['billed'], p['cost_usd'], p['gpu_hours']), (False, 0.0, 0.0))

    def test_the_same_interval_always_gets_the_same_uuid(self):
        self.assertEqual(self.make()['uuid'], self.make()['uuid'])
        self.assertNotEqual(self.make()['uuid'], usage.event(**{**self.kwargs(), 'start': T0 + timedelta(hours=1)})['uuid'])

    def kwargs(self):
        return dict(customer='bild-ai', stage='training', run_id='run-1', workstream='bildy', provider='ornn',
                    resource_name='train-1', resource_id='r-1', region='us-east', term='spot', gpu_type='nvidia_b300',
                    gpu_count=8, usd_per_hour=60.0, price_source='ornn_reservation', start=T0,
                    end=T0 + timedelta(hours=2), vm_state='RUNNING', source='test')

    def test_sending_can_be_turned_off(self):
        with mock.patch.dict(os.environ, {'GRADIATED_USAGE_EVENTS': '0'}), \
                mock.patch.object(usage.urllib.request, 'urlopen') as urlopen:
            self.assertEqual(usage.send([self.make()]), 0)
        urlopen.assert_not_called()


class Meter(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        self.patches = [mock.patch.object(commands, 'state', return_value=self.dir)]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        self.cloud = SimpleNamespace(name='ornn')
        with usage.ledger(self.dir) as book:
            book['ornn:train-1'] = {'customer': 'bild-ai', 'stage': 'training', 'run_id': 'run-1',
                                    'workstream': 'bildy', 'started_at': T0.isoformat()}

    def meter(self, end, sent=None, fail=False):
        def send(events):
            if fail:
                raise OSError('PostHog unreachable')
            (sent if sent is not None else []).extend(events)
            return len(events)
        with mock.patch.object(usage, 'send', side_effect=send):
            return commands.meter_vms(self.cloud, [vm()], end, 'test')

    def test_metering_continues_from_where_it_stopped_and_keeps_the_tags(self):
        first = self.meter(T0 + timedelta(hours=1))
        second = self.meter(T0 + timedelta(hours=1, minutes=30))
        self.assertEqual(first[0]['properties']['cost_usd'], 60.0)
        self.assertEqual(second[0]['properties']['interval_start'], (T0 + timedelta(hours=1)).isoformat())
        self.assertEqual(second[0]['properties']['cost_usd'], 30.0)
        self.assertEqual((second[0]['properties']['customer'], second[0]['properties']['stage']), ('bild-ai', 'training'))

    def test_a_failed_send_is_retried_as_the_identical_event(self):
        with self.assertRaises(OSError):
            self.meter(T0 + timedelta(hours=1), fail=True)
        retried = self.meter(T0 + timedelta(hours=2))
        # Same uuid and timestamp as the attempt that may have reached PostHog, so it cannot count twice.
        self.assertEqual(retried[0]['properties']['interval_end'], (T0 + timedelta(hours=1)).isoformat())
        self.assertEqual(retried[0]['properties']['cost_usd'], 60.0)
        after = self.meter(T0 + timedelta(hours=2))
        self.assertEqual(after[0]['properties']['interval_start'], (T0 + timedelta(hours=1)).isoformat())

    def test_a_billed_interval_without_a_price_stays_open(self):
        with mock.patch.object(usage, 'send', return_value=1):
            none = commands.meter_vms(self.cloud, [vm(usd_per_gpu_hour=None)], T0 + timedelta(hours=1), 'test')
        self.assertEqual(none, [])
        priced = self.meter(T0 + timedelta(hours=2))
        self.assertEqual((priced[0]['properties']['interval_start'], priced[0]['properties']['cost_usd']),
                         (T0.isoformat(), 120.0))

    def test_an_interval_is_billed_by_the_state_the_vm_was_last_seen_in(self):
        with mock.patch.object(usage, 'send', return_value=1):
            commands.meter_vms(self.cloud, [vm(state='STOPPED')], T0 + timedelta(hours=1), 'test')
            restarted = commands.meter_vms(self.cloud, [vm(state='RUNNING')], T0 + timedelta(hours=2), 'test')
        # Stopped at the last meter: the hour before the restart was seen is not billed for GPUs.
        self.assertEqual(restarted[0]['properties']['cost_usd'], 0.0)

    def test_a_ledger_entry_recorded_by_name_moves_to_the_resource_id(self):
        events = self.meter(T0 + timedelta(hours=1))
        self.assertEqual(events[0]['properties']['customer'], 'bild-ai')
        with usage.ledger(self.dir) as book:
            self.assertIn('ornn:r-1', book)
            self.assertNotIn('ornn:train-1', book)

    def test_a_final_interval_that_failed_during_down_is_sent_by_the_next_meter(self):
        with self.assertRaises(OSError):
            self.meter(T0 + timedelta(hours=1), fail=True)
        with usage.ledger(self.dir) as book:
            book['ornn:r-1']['deleted'] = True
        sent = []
        with mock.patch.object(usage, 'send', side_effect=lambda events: sent.extend(events) or len(events)):
            commands.flush_pending()
        self.assertEqual(sent[0]['properties']['cost_usd'], 60.0)
        with usage.ledger(self.dir) as book:
            self.assertNotIn('ornn:r-1', book)

    def test_meter_fails_when_events_cannot_be_delivered(self):
        cloud = SimpleNamespace(name='ornn', list=lambda: [vm()])
        with mock.patch.object(commands, 'provider', return_value=cloud), \
                mock.patch.object(usage, 'send', side_effect=OSError('PostHog unreachable')):
            with self.assertRaises(OSError):
                commands.meter(SimpleNamespace(provider=None))

    def test_a_vm_created_elsewhere_is_unattributed_from_its_creation_time(self):
        with mock.patch.object(usage, 'send', return_value=1):
            events = commands.meter_vms(self.cloud, [vm(name='other', created_at=(T0 - timedelta(hours=1)).isoformat())],
                                        T0, 'test')
        p = events[0]['properties']
        self.assertEqual((p['customer'], p['cost_usd']), (usage.UNATTRIBUTED, 60.0))


class RecordUsage(unittest.TestCase):
    def test_records_fleet_gpu_time_with_its_tags(self):
        args = SimpleNamespace(end=None, start=None, hours=2.0, customer='bild-ai', stage='rollout', run_id='r',
                               workstream='bildy', provider='fleet', resource='b300-pool', region=None, term='reserved',
                               gpu_type='nvidia_b300', gpu_count=8, usd_per_gpu_hour=4.0)
        with mock.patch.object(usage, 'send', return_value=1) as send:
            result = commands.record_usage(args)
        self.assertAlmostEqual(result.data['cost_usd'], 64.0, places=3)
        self.assertEqual(send.call_args[0][0][0]['properties']['provider'], 'fleet')


if __name__ == '__main__':
    unittest.main()
