# OpenRouter model alias map for usage/cost reports

Use these mappings when runtime model names do not match OpenRouter names 1:1.

## Canonical mappings

- `MiniMax-M2.5-highspeed` → `minimax/minimax-m2.5`
- `minimax/MiniMax-M2.5-highspeed` → `minimax/minimax-m2.5`
- `gpt-5.3-codex` → `openai-codex/gpt-5.3-codex`
- `openai-codex/gpt-5.3-codex` → `openai-codex/gpt-5.3-codex`
- `k2p5` → `moonshotai/kimi-k2.5`
- `kimi-coding/k2p5` → `moonshotai/kimi-k2.5`

## Hard reporting rule

For these models, do **not** answer:
- "это не OpenRouter"
- "нет прямых цен"
- "не могу посчитать"

Correct behavior:
- say that exact names may differ,
- use the mapped OpenRouter equivalent,
- clearly label it as `ближайший OpenRouter-аналог` when needed.

## Response wording

Preferred:
- `Точного 1:1 имени в OpenRouter может не быть, поэтому беру ближайший официальный аналог:`

Avoid:
- `это не OpenRouter, значит посчитать нельзя`
