"""Guard the minimum persistence of non-event production pages."""
import re


def check_critical_persistence(rules):
    immediate = {'AwsRootAccountUsed',
                 'FalcoCriticalEvents', 'GatewayFinalizationFailure'}
    for rule in rules:
        if rule.get('labels', {}).get('severity') != 'critical' or rule.get('alert') in immediate:
            continue
        duration = str(rule.get('for', '0s'))
        units = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400, 'w': 604800}
        assert re.fullmatch(r'(\d+[smhdw])+', duration), duration
        seconds = sum(int(count) * units[unit] for count, unit in re.findall(r'(\d+)([smhdw])', duration))
        assert seconds >= 60, f'{rule["alert"]} can page on a sub-minute interruption'
