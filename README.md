# chip-token-cost-monitor

Public OpenClaw skill for token and cost reporting across all agents/providers.

## What it does
- reads usage from `~/.openclaw/agents/*/sessions/*.jsonl`
- aggregates token usage by `provider / api / model`
- computes `Known cost` from available pricing maps
- keeps unknown pricing explicit via `Unpriced tokens`

## Usage

```bash
cd /opt/clawd-workspace/skills/public/chip-token-cost-monitor
python3 monitor.py --period 24h --dry-run
python3 monitor.py --period today --dry-run
python3 monitor.py --period week --dry-run
```

## Output philosophy
- provider-aware
- no fake global fallback cost
- unknown pricing stays visible
- compatible with rolling 24h usage reports

## Files
- `SKILL.md`
- `monitor.py`
- `requirements.txt`
- `references/model-aliases.md`

## Safe for public repo
This folder contains no chat ids, no secrets, no private delivery routes, and no personal policy files.
