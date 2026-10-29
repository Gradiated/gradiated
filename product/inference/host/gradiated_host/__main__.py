import json
import sys

from .paths import Layout

USAGE = 'usage: gradiated-host start | enroll | control'


def main(arguments=None):
    arguments = sys.argv[1:] if arguments is None else arguments
    if arguments == ['start']:
        from . import start
        start.main()
        return 0
    if arguments == ['control']:
        from . import control
        control.main(Layout())
        return 0
    if arguments == ['enroll']:
        try:
            from . import enroll
            result = enroll.enroll(json.load(sys.stdin))
        except Exception as error:  # noqa: BLE001 - every failure is reported the same way
            # Refusals and validation errors name fields, never payload values. Other errors
            # can carry the signed bundle URL, so only their type is shown.
            safe = isinstance(error, ValueError) and '://' not in str(error)
            print(f'Enrollment failed: {error if safe else type(error).__name__}', file=sys.stderr)
            return 1
        print(json.dumps(result))
        return 0
    print(USAGE, file=sys.stderr)
    return 64


if __name__ == '__main__':
    sys.exit(main())
