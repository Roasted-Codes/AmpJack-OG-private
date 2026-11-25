#!/usr/bin/env python3
"""Read-only, script-only AmpJack-OG owner check-in. Never dispatch work."""
import json
from pathlib import Path

STATE = Path(__file__).resolve().parent / 'sol-audit' / 'COORDINATOR_STATE.json'


def render(data):
    result = data.get('owner_verified_result')
    next_step = data.get('owner_next_check')
    if not isinstance(result, str) or not result.strip():
        return 'No newer verified controller result is available in the progress record.'
    pieces = [result.strip()]
    if isinstance(next_step, str) and next_step.strip():
        pieces.append(next_step.strip())
    action = data.get('owner_required_action')
    if isinstance(action, str) and action.strip():
        pieces.append(action.strip())
    return ' '.join(pieces)


def main(state_path=STATE, last_path=STATE.with_name('progress-last-emitted.txt')):
    try:
        data = json.loads(state_path.read_text())
        if not isinstance(data, dict):
            raise ValueError('Expected object')
        message = render(data)
    except (OSError, ValueError):
        message = 'The controller progress record is unavailable; I cannot verify a newer result.'
    if last_path.exists() and last_path.read_text().strip() == message.strip():
        return
    last_path.write_text(message + '\n')
    print(message)


if __name__ == '__main__':
    main()
