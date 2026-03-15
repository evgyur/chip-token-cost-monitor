---
name: chip-token-cost-monitor
description: "Публичный skill для расчёта usage и стоимости токенов OpenClaw по всем агентам и провайдерам без секретов. Используй, когда нужно получить отчёт по токенам, моделям, провайдерам и known cost за 24h/day/week."
metadata:
  clawdbot:
    emoji: 📊
    command: /usage
---

# chip-token-cost-monitor

Публичный skill для отчётов по токенам и стоимости OpenClaw.

## Что делает
- считает usage по всем agent stores из `~/.openclaw/agents/*/sessions/*`
- агрегирует токены по `provider / api / model`
- считает `Known cost` только по известным pricing map
- отдельно показывает `Unpriced tokens`, если для части usage нет цены
- умеет отчёты за `24h`, `today`, `week`

## Основной файл
- `monitor.py`

## Быстрые команды
```bash
# Dry run за 24 часа
python3 monitor.py --period 24h --dry-run

# Dry run за today
python3 monitor.py --period today --dry-run

# Dry run за week
python3 monitor.py --period week --dry-run
```

## Правила
- не подменять неизвестную цену фейковой оценкой
- если pricing неизвестен, относить токены в `Unpriced tokens`
- не писать `OpenRouter cost`, если отчёт считает multi-provider usage
- source of truth для usage: message-level usage из session jsonl

## References
- `references/model-aliases.md`

## Quick test checklist
- [ ] `python3 monitor.py --period 24h --dry-run` отрабатывает без traceback
- [ ] в отчёте есть `Known cost`
- [ ] если есть неизвестные модели, они попадают в `Unpriced tokens`
- [ ] в breakdown видны `provider / api / model`

## Manual review checklist
- [ ] нет chat ids, bot tokens, usernames, секретов
- [ ] README не ссылается на приватные чаты или личные маршруты доставки
- [ ] pricing map не маскирует unknown как known
- [ ] формулировка отчёта не вводит в заблуждение про billing provider
