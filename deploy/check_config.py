"""Read-only validation/comparison of rendered Compose JSON; never calls Docker.

validate FILE checks the production deployment contract.
compare EXPECTED ACTUAL checks every resolved field (no ignored differences).
Use '-' to read one JSON input from stdin. Captured configuration wrappers work.
Only differing field paths are reported, never settings or credential values.
"""
import argparse
import json
from pathlib import Path
import re
import sys


def load(path):
    text = sys.stdin.read() if path == '-' else Path(path).read_text(encoding='utf-8-sig')
    value = json.loads(text)
    return value.get('resolved_configuration', value)


def differences(expected, actual, path='$'):
    if type(expected) is not type(actual):
        return [path]
    if isinstance(expected, dict):
        result = []
        for key in sorted(expected.keys() | actual.keys()):
            field = path+'.'+key
            result.extend(differences(expected[key], actual[key], field)
                          if key in expected and key in actual else [field])
        return result
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return [path]
        return [field for index, (left, right) in enumerate(zip(expected, actual))
                for field in differences(left, right, f'{path}[{index}]')]
    return [] if expected == actual else [path]


def validate(config):
    errors = []
    def require(condition, field):
        if not condition:
            errors.append(field)

    require(config.get('name') == 'hevy-fatigue', '$.name')
    services = config.get('services', {})
    require(set(services) == {'hevy-fatigue'}, '$.services')
    service = services.get('hevy-fatigue', {})
    require(service.get('container_name') == 'hevy-fatigue', '$.services.hevy-fatigue.container_name')
    require(bool(re.fullmatch(r'ghcr\.io/bross84/hevy-fatigue@sha256:[0-9a-f]{64}', service.get('image', ''))),
            '$.services.hevy-fatigue.image')
    require('build' not in service, '$.services.hevy-fatigue.build')
    require(service.get('pull_policy') == 'never', '$.services.hevy-fatigue.pull_policy')
    require(service.get('restart') == 'unless-stopped', '$.services.hevy-fatigue.restart')
    require(service.get('command') is None and service.get('entrypoint') is None,
            '$.services.hevy-fatigue.command/entrypoint')
    expected_env = {
        'DB_PATH': '/data/hevy_fatigue.db', 'FERNET_KEY_PATH': '/data/app.key',
        'HEVY_FATIGUE_DB_PATH': '/data/hevy_fatigue.db', 'HEVY_WRITES_ENABLED': '1',
        'RACKBOOK_DB_PATH': '/training-data/rackbook.db', 'RACKBOOK_READ_ONLY_PREVIEW': '0',
        'TZ': 'America/New_York',
    }
    errors.extend(differences(expected_env, service.get('environment', {}), '$.services.hevy-fatigue.environment'))
    expected_mounts = {'/data': 'hevy-data', '/training-data': 'training-data'}
    mounts = service.get('volumes', [])
    require(len(mounts) == 2 and all(
        mount.get('type') == 'volume' and mount.get('source') == expected_mounts.get(mount.get('target'))
        and not mount.get('read_only', False) and not mount.get('volume', {}).get('subpath')
        for mount in mounts) and {m.get('target') for m in mounts} == set(expected_mounts),
        '$.services.hevy-fatigue.volumes')
    ports = service.get('ports', [])
    require(len(ports) == 1 and ports[0].get('target') == 8000
            and ports[0].get('published') == '8125' and ports[0].get('protocol') == 'tcp'
            and ports[0].get('mode') == 'ingress' and not ports[0].get('host_ip'),
            '$.services.hevy-fatigue.ports')
    require(set(service.get('networks', {})) == {'hevy-net'}, '$.services.hevy-fatigue.networks')
    for alias, name in [('hevy-data', 'hevy-fatigue_hevy-data'), ('training-data', 'hevy-fatigue_training-data')]:
        volume = config.get('volumes', {}).get(alias, {})
        require(volume.get('external') is True and volume.get('name') == name,
                '$.volumes.'+alias)
    network = config.get('networks', {}).get('hevy-net', {})
    require(network.get('external') is True and network.get('name') == 'hevy-fatigue_hevy-net', '$.networks.hevy-net')
    casaos = config.get('x-casaos', {})
    require(casaos.get('port_map') == '8125' and casaos.get('index') == '/'
            and casaos.get('title', {}).get('custom') == 'hevy-fatigue'
            and casaos.get('icon') == service.get('labels', {}).get('icon')
            and bool(casaos.get('icon')), '$.x-casaos')
    require(bool(service.get('healthcheck', {}).get('test')), '$.services.hevy-fatigue.healthcheck')
    require(not config.get('secrets') and not config.get('configs'), '$.secrets/configs')
    return sorted(set(errors))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    sub.add_parser('validate').add_argument('file')
    compare = sub.add_parser('compare')
    compare.add_argument('expected')
    compare.add_argument('actual')
    args = parser.parse_args()
    try:
        errors = validate(load(args.file)) if args.mode == 'validate' else differences(load(args.expected), load(args.actual))
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        print('Could not read valid configuration JSON; no action taken.', file=sys.stderr)
        return 2
    print(json.dumps({'mode': args.mode, 'matches': not errors, 'different_fields': errors}, indent=2))
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
