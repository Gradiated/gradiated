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

    def test_known_expiry_caps_first_and_previously_running_observations(self):
        ended = T0 + timedelta(hours=1)
        terminal = vm(state='COMPLETED', billing_ended_at=ended.isoformat())
        with mock.patch.object(usage, 'send', return_value=1):
            first = commands.meter_vms(self.cloud, [terminal], T0 + timedelta(hours=2), 'test')
            self.assertEqual(first[0]['properties']['cost_usd'], 60)
            self.assertEqual(first[0]['properties']['gpu_hours'], 8)
            self.assertEqual(first[0]['properties']['interval_end'], ended.isoformat())
            self.assertEqual(commands.meter_vms(self.cloud, [terminal], T0 + timedelta(hours=3), 'test'), [])
        # Repeat with an earlier running observation in a fresh ledger interval.
        with usage.ledger(self.dir) as book:
            book.clear()
            book['ornn:train-1'] = {'started_at': T0.isoformat()}
        self.meter(T0 + timedelta(minutes=30))
        with mock.patch.object(usage, 'send', return_value=1):
            final = commands.meter_vms(self.cloud, [terminal], T0 + timedelta(hours=2), 'test')
        self.assertEqual(final[0]['properties']['cost_usd'], 30)
        self.assertEqual(final[0]['properties']['interval_end'], ended.isoformat())

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

    def test_billing_starts_when_the_provider_starts_charging(self):
        started = T0 + timedelta(minutes=30)
        with mock.patch.object(usage, 'send', return_value=1):
            events = commands.meter_vms(self.cloud, [vm(billing_started_at=started.isoformat())],
                                        T0 + timedelta(hours=1, minutes=30), 'test')
        # The half hour spent deploying before Spheron's startedAt costs nothing and is not sent.
        self.assertEqual((events[0]['properties']['interval_start'], events[0]['properties']['cost_usd']),
                         (started.isoformat(), 60.0))

    def test_the_interval_after_billing_starts_is_billed_even_if_the_last_meter_saw_it_deploying(self):
        started = T0 + timedelta(minutes=30)
        with mock.patch.object(usage, 'send', return_value=1):
            commands.meter_vms(self.cloud, [vm(state='DEPLOYING')], T0 + timedelta(minutes=10), 'test')
            events = commands.meter_vms(self.cloud, [vm(billing_started_at=started.isoformat())],
                                        T0 + timedelta(hours=1, minutes=30), 'test')
        self.assertEqual((events[0]['properties']['interval_start'], events[0]['properties']['cost_usd']),
                         (started.isoformat(), 60.0))

    def test_down_waits_for_the_provider_then_meters_the_vm_as_it_is_after_the_wait(self):
        order, running = [], vm(billing_started_at=T0.isoformat())
        cloud = SimpleNamespace(name='spheron', delete=lambda v: order.append('delete'),
                                wait_until_deletable=lambda v: order.append('wait') or running)
        with mock.patch.object(commands, 'locate', return_value=(cloud, vm(state='DEPLOYING'))), \
                mock.patch.object(commands, 'meter_vms', side_effect=lambda c, vms, *a: order.append(vms[0])), \
                mock.patch.object(commands, 'tailscale_token', return_value='t'), \
                mock.patch.object(commands, 'tailscale', return_value={'devices': []}), mock.patch('sys.stderr'):
            commands.down(SimpleNamespace(name='train-1', provider=None))
        self.assertEqual(order, ['wait', running, 'delete'])

    def test_down_closes_a_vm_reclaimed_during_the_wait_by_its_end_time(self):
        cloud = SimpleNamespace(name='spheron', wait_until_deletable=lambda v: None, delete=lambda v: None)
        with mock.patch.object(commands, 'locate', return_value=(cloud, vm(state='DEPLOYING'))), \
                mock.patch.object(commands, 'meter_vms') as metered, \
                mock.patch.object(commands, 'close_ended') as closed, \
                mock.patch.object(commands, 'tailscale_token', return_value='t'), \
                mock.patch.object(commands, 'tailscale', return_value={'devices': []}), mock.patch('sys.stderr'):
            commands.down(SimpleNamespace(name='train-1', provider=None))
        metered.assert_not_called()
        self.assertEqual(closed.call_args.kwargs['only'], 'train-1')

    def test_down_keeps_the_ledger_when_an_ended_vm_cannot_be_closed(self):
        cloud = SimpleNamespace(name='ornn', wait_until_deletable=lambda v: None, delete=lambda v: None)
        with mock.patch.object(commands, 'locate', return_value=(cloud, vm())), \
                mock.patch.object(commands, 'close_ended', side_effect=SystemExit('Spheron GET: HTTP 503')), \
                mock.patch.object(commands, 'tailscale_token', return_value='t'), \
                mock.patch.object(commands, 'tailscale', return_value={'devices': []}), mock.patch('sys.stderr'):
            commands.down(SimpleNamespace(name='train-1', provider=None))
        with usage.ledger(self.dir) as book:
            self.assertIn('ornn:train-1', book)

    def test_a_vm_the_provider_ended_gets_its_final_interval_and_is_forgotten(self):
        ended = vm(state='TERMINATED-PROVIDER', billing_started_at=T0.isoformat(),
                   ended_at=(T0 + timedelta(hours=2)).isoformat())
        asked = []
        cloud = SimpleNamespace(name='ornn', ended=lambda tracked: asked.extend(tracked) or [('train-1', ended)])
        sent = []
        with mock.patch.object(usage, 'send', side_effect=lambda events: sent.extend(events) or len(events)):
            commands.close_ended(cloud, set(), T0 + timedelta(hours=5), 'test')
        self.assertEqual(asked, [('train-1', T0.isoformat())])
        # Billed up to the reclaim, not up to now, and the ledger entry is gone.
        self.assertEqual((sent[0]['properties']['interval_end'], sent[0]['properties']['cost_usd']),
                         ((T0 + timedelta(hours=2)).isoformat(), 120.0))
        with usage.ledger(self.dir) as book:
            self.assertEqual(book, {})

    def test_listed_vms_are_not_closed(self):
        cloud = SimpleNamespace(name='ornn', ended=mock.Mock(return_value=[]))
        commands.close_ended(cloud, {'ornn:train-1'}, T0 + timedelta(hours=1), 'test')
        cloud.ended.assert_not_called()

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
