# chip-token-cost-monitor

![OpenClaw](https://img.shields.io/badge/OpenClaw-skill-6f42c1)
![Public Repo](https://img.shields.io/badge/repo-public-2da44e)
![Python](https://img.shields.io/badge/python-3.x-blue)
![Status](https://img.shields.io/badge/status-working-brightgreen)

Public OpenClaw skill for token and cost reporting across all agents/providers.

## Quick start

```bash
cd /opt/clawd-workspace/skills/public/chip-token-cost-monitor
python3 onboarding_check.py
python3 monitor.py --period 24h --dry-run
```

In under a minute, this verifies that the skill can see:
- all local OpenClaw agents
- all indexed sessions
- raw session jsonl files
- usage rows with `totalTokens`

## What it does
- reads usage from `~/.openclaw/agents/*/sessions/*.jsonl`
- auto-discovers all local agents and session stores
- aggregates token usage by `provider / api / model`
- computes `Known cost` from available pricing maps
- keeps unknown pricing explicit via `Unpriced tokens`

## 60-second onboarding

```bash
cd /opt/clawd-workspace/skills/public/chip-token-cost-monitor
python3 onboarding_check.py
python3 monitor.py --period 24h --dry-run
```

What onboarding does:
- checks that `~/.openclaw/agents/` exists
- discovers all local agents
- counts indexed sessions from `sessions.json`
- counts raw `*.jsonl` session files
- counts usage rows with `totalTokens`

So after install, a user can immediately verify that the skill sees **all agents and sessions**, not just the main one.

## Example output

```text
📊 Usage 24h
• Active sessions: 302
• Total sessions: 360
• Tokens: 101,104,469
• Known cost: $262.59
• Unpriced tokens: 0

Top usage paths:
• openai-codex / openai-codex-responses / gpt-5.3-codex — 54,500,193 tokens — $162.14
• minimax / anthropic-messages / MiniMax-M2.5-highspeed — 23,667,315 tokens — $8.00
• openai-codex / openai-codex-responses / gpt-5.4 — 21,549,789 tokens — $91.59
• kimi-coding / anthropic-messages / k2p5 — 1,387,172 tokens — $0.87
```

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
- source of truth for usage = message-level session jsonl

## Files
- `SKILL.md`
- `monitor.py`
- `onboarding_check.py`
- `requirements.txt`
- `references/model-aliases.md`

## Safe for public repo
This folder contains no chat ids, no secrets, no private delivery routes, and no personal policy files.
