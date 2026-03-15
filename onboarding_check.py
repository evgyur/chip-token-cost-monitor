#!/usr/bin/env python3
import glob
import json
from pathlib import Path


def main():
    base = Path.home() / '.openclaw' / 'agents'
    print('chip-token-cost-monitor onboarding')
    print(f'Agents path: {base}')

    if not base.exists():
        print('ERROR: ~/.openclaw/agents not found')
        print('This skill expects an OpenClaw runtime with local agent session stores.')
        raise SystemExit(1)

    agent_dirs = sorted([p for p in base.iterdir() if p.is_dir()])
    print(f'Agents found: {len(agent_dirs)}')

    total_sessions_index = 0
    total_jsonl = 0
    total_usage_rows = 0

    for agent_dir in agent_dirs:
        sessions_json = agent_dir / 'sessions' / 'sessions.json'
        jsonl_files = sorted(glob.glob(str(agent_dir / 'sessions' / '*.jsonl')))
        indexed = 0
        if sessions_json.exists():
            try:
                raw = json.loads(sessions_json.read_text())
                if isinstance(raw, dict):
                    indexed = len(raw)
                elif isinstance(raw, list):
                    indexed = len(raw)
            except Exception:
                indexed = 0

        usage_rows = 0
        for jf in jsonl_files:
            try:
                with open(jf, 'r', encoding='utf-8') as fh:
                    for line in fh:
                        if 'totalTokens' in line:
                            usage_rows += 1
            except Exception:
                pass

        total_sessions_index += indexed
        total_jsonl += len(jsonl_files)
        total_usage_rows += usage_rows
        print(f'- {agent_dir.name}: indexed_sessions={indexed}, jsonl_files={len(jsonl_files)}, usage_rows={usage_rows}')

    print('---')
    print(f'Total indexed sessions: {total_sessions_index}')
    print(f'Total jsonl session files: {total_jsonl}')
    print(f'Total usage rows found: {total_usage_rows}')
    print('---')
    print('Next step:')
    print('python3 monitor.py --period 24h --dry-run')


if __name__ == '__main__':
    main()
