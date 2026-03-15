#!/usr/bin/env python3
"""
Usage Monitor for OpenClaw
Tracks token usage and sends visual reports to Telegram
"""

import os
import sys
import json
import argparse
import glob
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

# USD per 1M tokens (input/output). Used when provider config lacks explicit model cost.
# Values aligned with current OpenRouter public pricing for equivalent model IDs.
DEFAULT_MODEL_PRICING = {
    'openai-codex/gpt-5.3-codex': {'input': 1.75, 'output': 14.0},
    'gpt-5.3-codex': {'input': 1.75, 'output': 14.0},
    'openai-codex/gpt-5.3-chat-latest': {'input': 1.75, 'output': 14.0},
    'gpt-5.3-chat-latest': {'input': 1.75, 'output': 14.0},
    'openai-codex/gpt-5.4': {'input': 2.5, 'output': 20.0},
    'gpt-5.4': {'input': 2.5, 'output': 20.0},

    'anthropic/claude-sonnet-4-6': {'input': 3.0, 'output': 15.0},
    'claude-sonnet-4-6': {'input': 3.0, 'output': 15.0},
    'anthropic/claude-opus-4-5': {'input': 15.0, 'output': 75.0},
    'claude-opus-4-5': {'input': 15.0, 'output': 75.0},
    'anthropic/claude-opus-4-6': {'input': 15.0, 'output': 75.0},
    'claude-opus-4-6': {'input': 15.0, 'output': 75.0},

    'kimi-coding/k2p5': {'input': 0.45, 'output': 2.2},
    'moonshotai/kimi-k2.5': {'input': 0.45, 'output': 2.2},
    'moonshot/kimi-k2.5': {'input': 0.45, 'output': 2.2},
    'k2p5': {'input': 0.45, 'output': 2.2},

    'minimax/MiniMax-M2.5-highspeed': {'input': 0.27, 'output': 0.95},
    'minimax/MiniMax-M2.5': {'input': 0.27, 'output': 0.95},
    'MiniMax-M2.5-highspeed': {'input': 0.27, 'output': 0.95},
    'MiniMax-M2.5': {'input': 0.27, 'output': 0.95},
    'minimax/minimax-m2.5': {'input': 0.27, 'output': 0.95},
}

# With sessions list we only have totalTokens, no in/out split.
# Use a conservative blended estimate (90% input, 10% output).
DEFAULT_OUTPUT_SHARE = 0.10
from pathlib import Path

# Add openclaw to path for imports
sys.path.insert(0, '/usr/lib/node_modules/openclaw')

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.text import Text
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


class UsageMonitor:
    """Main usage monitoring class"""
    
    def __init__(self):
        self.console = Console() if RICH_AVAILABLE else None
        self.data_dir = Path.home() / '.openclaw' / 'usage-monitor'
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.history_file = self.data_dir / 'history.json'
        self.config = self._load_openclaw_config()
    
    def _load_openclaw_config(self) -> Dict:
        """Load OpenClaw config with fallback chain and model prices"""
        config_path = Path.home() / '.openclaw' / 'openclaw.json'
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    
    def get_fallback_chain(self) -> List[Dict]:
        """Get fallback chain from config"""
        agents = self.config.get('agents', {})
        defaults = agents.get('defaults', {})
        model_config = defaults.get('model', {})
        
        primary = model_config.get('primary', 'unknown')
        fallbacks = model_config.get('fallbacks', [])
        
        chain = [{'model': primary, 'type': 'primary', 'status': 'active'}]
        for i, fb in enumerate(fallbacks):
            if fb != primary:  # Skip if same as primary
                chain.append({
                    'model': fb, 
                    'type': 'fallback', 
                    'status': 'standby'
                })
        
        return chain
    
    def _normalize_model_id(self, model_id: str) -> str:
        return (model_id or '').strip()

    def _canonical_model_keys(self, model_id: str, provider: Optional[str] = None) -> List[str]:
        model_id = self._normalize_model_id(model_id)
        provider = (provider or '').strip()
        short = model_id.split('/')[-1] if '/' in model_id else model_id
        keys = []
        if provider and short:
            keys.append(f'{provider}/{short}')
        if model_id:
            keys.append(model_id)
        if short:
            keys.append(short)

        alias_map = {
            'MiniMax-M2.5-highspeed': 'minimax/minimax-m2.5',
            'minimax/MiniMax-M2.5-highspeed': 'minimax/minimax-m2.5',
            'gpt-5.3-codex': 'openai-codex/gpt-5.3-codex',
            'openai-codex/gpt-5.3-codex': 'openai-codex/gpt-5.3-codex',
            'k2p5': 'moonshotai/kimi-k2.5',
            'kimi-coding/k2p5': 'moonshotai/kimi-k2.5',
        }
        for k in list(keys):
            mapped = alias_map.get(k)
            if mapped:
                keys.append(mapped)
                keys.append(mapped.split('/')[-1])
        # preserve order, dedupe
        seen = set()
        out = []
        for k in keys:
            if k and k not in seen:
                seen.add(k)
                out.append(k)
        return out

    def get_model_cost(self, model_id: str, provider: Optional[str] = None) -> Dict:
        """Get cost info for a model from config, with sane fallback pricing."""
        model_id = self._normalize_model_id(model_id)
        providers = self.config.get('models', {}).get('providers', {})
        candidate_keys = self._canonical_model_keys(model_id, provider)

        # 1) Explicit prices from config providers
        for provider_name, provider_cfg in providers.items():
            for model in provider_cfg.get('models', []):
                model_raw_id = str(model.get('id', ''))
                full_id = f"{provider_name}/{model_raw_id}"
                if full_id in candidate_keys or model_raw_id in candidate_keys:
                    cost = model.get('cost') or {}
                    if cost.get('input', 0) or cost.get('output', 0):
                        return {
                            'input': float(cost.get('input', 0) or 0),
                            'output': float(cost.get('output', 0) or 0),
                            'cacheRead': float(cost.get('cacheRead', 0) or 0),
                            'cacheWrite': float(cost.get('cacheWrite', 0) or 0),
                        }

        # 2) Static fallback pricing for known models/providers
        for key in candidate_keys:
            if key in DEFAULT_MODEL_PRICING:
                return DEFAULT_MODEL_PRICING[key]

        return {'input': 0.0, 'output': 0.0}
        
    def get_session_data(self) -> Dict:
        """Get session list across all agents + raw message usage from filesystem stores."""
        try:
            data = {'sessions': self._collect_sessions_index()}
            base = self._process_sessions(data)
            base['usage_messages'] = self._collect_message_usage()
            return base
        except Exception as e:
            return self._get_empty_data(reason=str(e))

    def _collect_sessions_index(self) -> List[Dict]:
        sessions: List[Dict] = []
        for path in glob.glob('/home/chip/.openclaw/agents/*/sessions/sessions.json'):
            try:
                raw = json.load(open(path, 'r', encoding='utf-8'))
            except Exception:
                continue
            if isinstance(raw, dict):
                values = list(raw.values())
            elif isinstance(raw, list):
                values = raw
            else:
                continue
            for s in values:
                if not isinstance(s, dict):
                    continue
                sessions.append(s)
        return sessions

    def _parse_record_dt(self, value) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc).astimezone().replace(tzinfo=None)
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return None
            try:
                if s.endswith('Z'):
                    return datetime.fromisoformat(s.replace('Z', '+00:00')).astimezone().replace(tzinfo=None)
                dt = datetime.fromisoformat(s)
                if dt.tzinfo is not None:
                    return dt.astimezone().replace(tzinfo=None)
                return dt
            except Exception:
                return None
        return None

    def _collect_message_usage(self) -> List[Dict]:
        records: List[Dict] = []
        seen = set()
        for path in glob.glob('/home/chip/.openclaw/agents/*/sessions/*.jsonl'):
            session_key = Path(path).stem
            if session_key == 'sessions':
                continue
            try:
                with open(path, 'r', encoding='utf-8') as fh:
                    for line_no, line in enumerate(fh, 1):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            row = json.loads(line)
                        except Exception:
                            continue
                        msg = row.get('message') or {}
                        usage = msg.get('usage') or {}
                        total_tokens = int(usage.get('totalTokens') or 0)
                        provider = msg.get('provider') or row.get('provider') or 'unknown'
                        api = msg.get('api') or row.get('api') or 'unknown'
                        model = msg.get('model') or row.get('model') or 'unknown'
                        if total_tokens <= 0 or provider == 'unknown' or model == 'unknown':
                            continue
                        dt = self._parse_record_dt(row.get('timestamp')) or self._parse_record_dt(msg.get('timestamp'))
                        if dt is None:
                            continue
                        rid = row.get('id') or f'{path}:{line_no}'
                        key = (rid, provider, model, total_tokens)
                        if key in seen:
                            continue
                        seen.add(key)
                        records.append({
                            'sessionKey': session_key,
                            'timestamp': dt.isoformat(),
                            'timestampMs': int(dt.timestamp() * 1000),
                            'seq': line_no,
                            'provider': provider,
                            'api': api,
                            'model': model,
                            'totalTokens': total_tokens,
                        })
            except Exception:
                continue
        return records
    
    def _process_sessions(self, data: Dict) -> Dict:
        """Process sessions JSON data"""
        sessions = data.get('sessions', [])

        # Normalize session shapes from sessions.json stores
        norm_sessions = []
        for s in sessions:
            updated_at = s.get('updatedAt') or s.get('updatedAtMs') or s.get('lastMessageAt') or s.get('lastMessageAtMs') or 0
            total_tokens = s.get('totalTokens') or 0
            norm_sessions.append({**s, 'updatedAt': updated_at, 'totalTokens': total_tokens})
        sessions = norm_sessions

        total_tokens = sum(s.get('totalTokens') or 0 for s in sessions)
        active_sessions = len([s for s in sessions if (s.get('totalTokens') or 0) > 0])
        
        # Group by provider+model
        model_stats = {}
        for s in sessions:
            model = s.get('model', 'unknown')
            provider = s.get('modelProvider') or 'unknown'
            tokens = s.get('totalTokens') or 0
            key = (provider, model)
            if key not in model_stats:
                model_stats[key] = {'tokens': 0, 'sessions': 0, 'provider': provider, 'model': model}
            model_stats[key]['tokens'] += tokens
            model_stats[key]['sessions'] += 1
        
        # Convert to list and sort
        models = []
        for _, stats in sorted(model_stats.items(), key=lambda x: x[1]['tokens'], reverse=True):
            models.append({
                'provider': stats['provider'],
                'model': stats['model'],
                'tokens': stats['tokens'],
                'sessions': stats['sessions'],
                'percent': 0  # Will calculate later
            })
        
        # Calculate percentages
        if total_tokens > 0:
            for m in models:
                m['percent'] = round(m['tokens'] / total_tokens * 100)
        
        return {
            'sessions': sessions,
            'total_tokens': total_tokens,
            'active_sessions': active_sessions,
            'models': models,
            'session_count': len(sessions),
            'usage_messages': [],
        }
    
    def _parse_sessions_text(self, output: str) -> Dict:
        """Parse text output as fallback (conservative, no fabricated models)."""
        return self._get_empty_data(reason="non-json sessions output")
    
    def _get_empty_data(self, reason: str = "unknown") -> Dict:
        """Safe empty dataset when source data is unavailable."""
        return {
            'sessions': [],
            'total_tokens': 0,
            'active_sessions': 0,
            'session_count': 0,
            'models': [],
            'usage_messages': [],
            'error': reason,
        }
    
    def _resolve_period_start(self, now: datetime, period: str) -> datetime:
        """Resolve period alias to a concrete start datetime."""
        if period in ('today',):
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        if period in ('day', '24h'):
            return now - timedelta(hours=24)
        if period in ('48h',):
            return now - timedelta(hours=48)
        if period in ('week',):
            return now - timedelta(days=7)
        if period in ('month',):
            return now - timedelta(days=30)
        # Fallback: last 24h
        return now - timedelta(hours=24)

    def generate_report(self, period: str = 'today', all_data: Optional[Dict] = None) -> Dict:
        """Generate usage report for specified period."""
        now = datetime.now()
        start_time = self._resolve_period_start(now, period)

        if all_data is None:
            all_data = self.get_session_data()

        # Filter by period
        start_ms = int(start_time.timestamp() * 1000)
        filtered_sessions = [s for s in all_data.get('sessions', []) if (s.get('updatedAt') or 0) >= start_ms]
        usage_messages_all = sorted(
            all_data.get('usage_messages', []),
            key=lambda m: (m.get('sessionKey') or '', m.get('provider') or '', m.get('api') or '', m.get('model') or '', m.get('timestampMs') or 0, m.get('seq') or 0)
        )

        # Delta accounting: totalTokens in jsonl is cumulative-ish inside a session/model stream.
        deltas = []
        prev_totals = {}
        for m in usage_messages_all:
            key = (m.get('sessionKey'), m.get('provider'), m.get('api'), m.get('model'))
            current_total = int(m.get('totalTokens') or 0)
            prev_total = prev_totals.get(key)
            if prev_total is None:
                delta = current_total
            else:
                delta = current_total - prev_total if current_total >= prev_total else current_total
            prev_totals[key] = current_total
            if (m.get('timestampMs') or 0) >= start_ms and delta > 0:
                deltas.append({**m, 'deltaTokens': delta})

        total_tokens = sum(m.get('deltaTokens') or 0 for m in deltas)
        active_session_keys = {m.get('sessionKey') for m in deltas if (m.get('deltaTokens') or 0) > 0}
        active_sessions = len(active_session_keys)

        # Group by provider/api/model for filtered data
        model_stats = {}
        for m in deltas:
            model = m.get('model', 'unknown')
            provider = m.get('provider') or 'unknown'
            api = m.get('api') or 'unknown'
            tokens = m.get('deltaTokens') or 0
            key = (provider, api, model)
            if key not in model_stats:
                model_stats[key] = {'tokens': 0, 'sessions': set(), 'provider': provider, 'api': api, 'model': model}
            model_stats[key]['tokens'] += tokens
            if m.get('sessionKey'):
                model_stats[key]['sessions'].add(m.get('sessionKey'))

        models = []
        for _, stats in sorted(model_stats.items(), key=lambda x: x[1]['tokens'], reverse=True):
            model_cost = self.get_model_cost(stats['model'], stats['provider'])
            priced = bool((model_cost.get('input', 0) or 0) or (model_cost.get('output', 0) or 0))
            blended_per_1m = ((model_cost.get('input', 0) or 0) * (1 - DEFAULT_OUTPUT_SHARE)) + ((model_cost.get('output', 0) or 0) * DEFAULT_OUTPUT_SHARE)
            estimated_cost = round((stats['tokens'] / 1_000_000) * blended_per_1m, 2) if priced else 0.0
            models.append({
                'provider': stats['provider'],
                'api': stats['api'],
                'model': stats['model'],
                'tokens': stats['tokens'],
                'sessions': len(stats['sessions']),
                'percent': round(stats['tokens'] / total_tokens * 100) if total_tokens > 0 else 0,
                'priced': priced,
                'estimated_cost': estimated_cost,
            })

        cost_summary = self._estimate_cost(total_tokens, models=models)

        return {
            'timestamp': now.isoformat(),
            'period': period,
            'summary': {
                'total_sessions': active_sessions,
                'session_count': len(filtered_sessions),
                'total_tokens': total_tokens,
                'estimated_cost': cost_summary['known_cost'],
                'known_cost': cost_summary['known_cost'],
                'priced_tokens': cost_summary['priced_tokens'],
                'unpriced_tokens': cost_summary['unpriced_tokens'],
                'provider_costs': cost_summary['provider_costs'],
            },
            'models': models,
            'top_sessions': filtered_sessions[:5]
        }

    def generate_spend_windows(self, all_data: Optional[Dict] = None) -> Dict:
        """Generate spend snapshots for 24h/48h/week/month windows."""
        if all_data is None:
            all_data = self.get_session_data()

        windows = {}
        for key in ('24h', '48h', 'week', 'month'):
            report = self.generate_report(period=key, all_data=all_data)
            windows[key] = {
                'cost': report['summary']['estimated_cost'],
                'known_cost': report['summary'].get('known_cost', report['summary']['estimated_cost']),
                'unpriced_tokens': report['summary'].get('unpriced_tokens', 0),
                'tokens': report['summary']['total_tokens'],
                'sessions': report['summary']['total_sessions'],
            }
        return windows
    
    def _estimate_cost(self, tokens: int, models: Optional[List[Dict]] = None) -> Dict:
        """Estimate known cost only; keep unknown/unpriced explicit."""
        models = models or []
        if tokens <= 0 or not models:
            return {'known_cost': 0.0, 'priced_tokens': 0, 'unpriced_tokens': tokens or 0, 'provider_costs': []}

        total_cost = 0.0
        priced_tokens = 0
        unpriced_tokens = 0
        provider_costs = {}
        for m in models:
            model_tokens = int(m.get('tokens', 0) or 0)
            if model_tokens <= 0:
                continue
            provider = m.get('provider') or 'unknown'
            prices = self.get_model_cost(m.get('model', ''), provider)
            in_price = float(prices.get('input', 0) or 0)
            out_price = float(prices.get('output', 0) or 0)
            if in_price == 0 and out_price == 0:
                unpriced_tokens += model_tokens
                continue
            blended_per_1m = (in_price * (1 - DEFAULT_OUTPUT_SHARE)) + (out_price * DEFAULT_OUTPUT_SHARE)
            model_cost = (model_tokens / 1_000_000) * blended_per_1m
            total_cost += model_cost
            priced_tokens += model_tokens
            provider_costs[provider] = provider_costs.get(provider, 0.0) + model_cost

        provider_costs_list = [
            {'provider': provider, 'cost': round(cost, 2)}
            for provider, cost in sorted(provider_costs.items(), key=lambda x: x[1], reverse=True)
        ]
        return {
            'known_cost': round(total_cost, 2),
            'priced_tokens': priced_tokens,
            'unpriced_tokens': unpriced_tokens,
            'provider_costs': provider_costs_list,
        }
    
    def _get_model_breakdown(self, data: Dict = None) -> List[Dict]:
        """Get breakdown by model"""
        if data and 'models' in data:
            return data['models']
        return []
    
    def render_terminal(self, report: Dict) -> str:
        """Render rich terminal output"""
        if not RICH_AVAILABLE:
            return self._render_simple(report)
        
        # Create layout
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3)
        )
        
        # Header
        timestamp = datetime.fromisoformat(report['timestamp'])
        header_text = Text()
        header_text.append("📊 ", style="bold yellow")
        header_text.append("OpenClaw Usage Report", style="bold white")
        header_text.append(f"\n{timestamp.strftime('%d %B %Y, %H:%M MSK')}", style="dim")
        layout["header"].update(Panel(header_text, border_style="blue"))
        
        # Main content - split into two columns
        main_layout = Layout()
        main_layout.split_row(
            Layout(name="left", ratio=1),
            Layout(name="right", ratio=1)
        )
        
        # Left column - Summary
        summary = report['summary']
        windows = report.get('spend_windows', {})

        left_content = Text()
        left_content.append("💸 Траты по окнам\n", style="bold cyan")
        left_content.append(f"24ч: ${windows.get('24h', {}).get('cost', 0):.2f}\n", style="white")
        left_content.append(f"48ч: ${windows.get('48h', {}).get('cost', 0):.2f}\n", style="white")
        left_content.append(f"7д:  ${windows.get('week', {}).get('cost', 0):.2f}\n", style="white")
        left_content.append(f"30д: ${windows.get('month', {}).get('cost', 0):.2f}\n", style="white")
        left_content.append(f"\n📈 Сессий активных: ", style="bold")
        left_content.append(f"{summary['total_sessions']}\n", style="white")
        left_content.append(f"📁 Всего сессий: ", style="bold")
        left_content.append(f"{summary.get('session_count', 0)}\n", style="white")
        left_content.append(f"🔤 Токенов: ", style="bold")
        left_content.append(f"{summary['total_tokens']:,}\n", style="white")
        
        main_layout["left"].update(Panel(left_content, title="Сводка", border_style="green"))
        
        # Right column - Models
        table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
        table.add_column("Модель", style="cyan")
        table.add_column("Токены", justify="right", style="green")
        table.add_column("%", justify="right", style="yellow")
        
        for model in report['models'][:5]:
            table.add_row(
                model['model'],
                f"{model['tokens']:,}",
                f"{model['percent']}%"
            )
        
        main_layout["right"].update(Panel(table, title="🏆 Топ модели", border_style="magenta"))
        
        layout["main"].update(main_layout)
        
        # Footer
        footer_text = Text("Нажмите Ctrl+C для выхода • Автообновление каждые 60 сек", style="dim", justify="center")
        layout["footer"].update(footer_text)
        
        # Capture output
        with self.console.capture() as capture:
            self.console.print(layout)
        
        return capture.get()
    
    def _make_progress_bar(self, percent: int, width: int = 20) -> str:
        """Create ASCII progress bar"""
        filled = int(width * percent / 100)
        return "█" * filled + "░" * (width - filled)
    
    def _render_simple(self, report: Dict) -> str:
        """Simple text rendering without rich"""
        windows = report.get('spend_windows', {})
        lines = [
            "📊 OpenClaw Usage Report",
            "=" * 40,
            "",
            f"💸 24h:  ${windows.get('24h', {}).get('cost', 0):.2f}",
            f"💸 48h:  ${windows.get('48h', {}).get('cost', 0):.2f}",
            f"💸 Week: ${windows.get('week', {}).get('cost', 0):.2f}",
            f"💸 Month:${windows.get('month', {}).get('cost', 0):.2f}",
            f"📈 Sessions: {report['summary']['total_sessions']}",
            f"🔤 Tokens: {report['summary']['total_tokens']:,}",
            "",
            "🏆 Top Models:",
        ]
        for model in report['models'][:3]:
            lines.append(f"  • {model['model']}: {model['tokens']:,}")
        
        return "\n".join(lines)
    
    def generate_image(self, report: Dict) -> str:
        """Generate beautiful image report with Jersey 25 font"""
        if not PIL_AVAILABLE:
            print("PIL not available, cannot generate image")
            return None
        
        # Colors - dark modern theme
        BG_COLOR = '#0d1117'
        CARD_BG = '#161b22'
        BORDER_COLOR = '#30363d'
        TEXT_PRIMARY = '#f0f6fc'
        TEXT_SECONDARY = '#8b949e'
        ACCENT_GREEN = '#3fb950'
        ACCENT_YELLOW = '#d29922'
        ACCENT_RED = '#f85149'
        ACCENT_BLUE = '#58a6ff'
        ACCENT_PURPLE = '#a371f7'
        
        # Create image
        width, height = 800, 600
        img = Image.new('RGB', (width, height), color=BG_COLOR)
        draw = ImageDraw.Draw(img)
        
        # Load fonts
        font_dir = Path(__file__).parent / 'fonts'
        try:
            font_title = ImageFont.truetype(str(font_dir / 'Jersey25-Regular.ttf'), 48)
            font_header = ImageFont.truetype(str(font_dir / 'Jersey25-Regular.ttf'), 32)
            font_large = ImageFont.truetype(str(font_dir / 'Jersey25-Regular.ttf'), 28)
            font_medium = ImageFont.truetype(str(font_dir / 'Jersey25-Regular.ttf'), 24)
            font_small = ImageFont.truetype(str(font_dir / 'Jersey25-Regular.ttf'), 20)
        except:
            # Fallback to default
            font_title = font_header = font_large = font_medium = font_small = ImageFont.load_default()
        
        # Helper function to draw rounded rectangle
        def draw_rounded_rect(x, y, w, h, radius, fill, outline=None):
            draw.rounded_rectangle([x, y, x+w, y+h], radius=radius, fill=fill, outline=outline)
        
        # Helper function to draw progress bar
        def draw_progress_bar(x, y, w, h, percent, color):
            # Background
            draw.rounded_rectangle([x, y, x+w, y+h], radius=h//2, fill=BORDER_COLOR)
            # Fill
            fill_w = int(w * percent / 100)
            if fill_w > 0:
                draw.rounded_rectangle([x, y, x+fill_w, y+h], radius=h//2, fill=color)
        
        # Header
        y = 30
        # Title card
        draw_rounded_rect(30, y, 740, 80, 15, CARD_BG, BORDER_COLOR)
        draw.text((50, y+20), "⚡ OPENCLAW USAGE", fill=ACCENT_BLUE, font=font_title)
        
        timestamp = datetime.fromisoformat(report['timestamp'])
        date_str = timestamp.strftime('%d %B %Y').upper()
        draw.text((520, y+25), date_str, fill=TEXT_SECONDARY, font=font_small)
        
        y += 100
        
        # Summary cards row
        summary = report['summary']
        cost = summary['estimated_cost']
        cost_percent = min(int(cost / 10 * 100), 100)
        
        # Fallback chain card (replacing budget)
        fallback_chain = self.get_fallback_chain()
        draw_rounded_rect(30, y, 360, 160, 15, CARD_BG, BORDER_COLOR)
        draw.text((50, y+15), "🔄 FALLBACK CHAIN", fill=TEXT_SECONDARY, font=font_small)
        
        # Draw chain
        chain_y = y + 45
        colors = [ACCENT_GREEN, ACCENT_BLUE, ACCENT_YELLOW, ACCENT_PURPLE, TEXT_SECONDARY]
        for i, item in enumerate(fallback_chain[:4]):
            color = colors[i % len(colors)]
            model_name = item['model'].split('/')[-1][:15]
            prefix = "▶" if item['type'] == 'primary' else "└"
            draw.text((50, chain_y), f"{prefix} {model_name}", fill=color, font=font_small)
            chain_y += 28
        
        # Stats card
        draw_rounded_rect(410, y, 360, 160, 15, CARD_BG, BORDER_COLOR)
        draw.text((430, y+20), "📊 SESSIONS", fill=TEXT_SECONDARY, font=font_small)
        draw.text((430, y+55), f"{summary['total_sessions']}", fill=ACCENT_PURPLE, font=font_header)
        draw.text((550, y+65), "ACTIVE", fill=TEXT_SECONDARY, font=font_small)
        
        draw.text((430, y+105), f"📁 {summary.get('session_count', 0)} TOTAL", fill=TEXT_SECONDARY, font=font_small)
        draw.text((430, y+130), f"🔤 {summary['total_tokens']:,} TOKENS", fill=ACCENT_GREEN, font=font_small)
        
        y += 190
        
        # Models section
        draw_rounded_rect(30, y, 740, 240, 15, CARD_BG, BORDER_COLOR)
        draw.text((50, y+20), "🏆 TOP MODELS", fill=ACCENT_YELLOW, font=font_large)
        
        # Model bars
        models = report['models'][:4]
        bar_y = y + 70
        max_tokens = max(m['tokens'] for m in models) if models else 1
        
        colors = [ACCENT_BLUE, ACCENT_PURPLE, ACCENT_GREEN, ACCENT_YELLOW]
        
        for i, model in enumerate(models):
            color = colors[i % len(colors)]
            bar_percent = int(model['tokens'] / max_tokens * 100)
            
            # Model name
            model_name = model['model'][:20]  # Truncate long names
            draw.text((50, bar_y), f"{model_name}", fill=TEXT_PRIMARY, font=font_medium)
            
            # Percentage
            draw.text((650, bar_y), f"{model['percent']}%", fill=color, font=font_small)
            
            # Bar
            draw_progress_bar(50, bar_y+30, 650, 12, bar_percent, color)
            
            # Token count
            draw.text((50, bar_y+48), f"{model['tokens']:,} tokens", fill=TEXT_SECONDARY, font=font_small)
            
            bar_y += 75
        
        # Footer
        draw.text((250, 570), "⚡ OPENCLAW USAGE MONITOR", fill=TEXT_SECONDARY, font=font_small)
        
        # Save
        output_path = self.data_dir / 'report.png'
        img.save(output_path, quality=95)
        return str(output_path)
    
    def send_to_telegram(self, image_path: str, caption: str = None):
        """Send report to Telegram via Bot API"""
        try:
            import requests
            
            # Get credentials from env
            bot_token = os.environ.get('SERVER_BOT_TOKEN', '')
            chat_id = int(os.environ.get('USAGE_MONITOR_CHAT_ID', -1003849089910))
            
            if not bot_token:
                print("SERVER_BOT_TOKEN not configured")
                return False
            
            # Send via Bot API
            url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
            
            with open(image_path, 'rb') as photo_file:
                files = {'photo': photo_file}
                data = {
                    'chat_id': chat_id,
                    'caption': caption or "📊 Usage Report",
                    'parse_mode': 'HTML'
                }
                
                resp = requests.post(url, files=files, data=data, timeout=30)
                
                if resp.status_code == 200:
                    print("✅ Report sent to Telegram")
                    return True
                else:
                    print(f"❌ Failed to send: {resp.text}")
                    return False
            
        except Exception as e:
            print(f"Failed to send to Telegram: {e}")
            return False
    
    def run(self, period: str = 'today', send: bool = False, dry_run: bool = False):
        """Main run method"""
        print(f"Generating {period} usage report...")
        
        # Generate report + spend windows from one dataset
        all_data = self.get_session_data()
        report = self.generate_report(period, all_data=all_data)
        report['spend_windows'] = self.generate_spend_windows(all_data=all_data)

        # Render terminal output
        terminal_output = self.render_terminal(report)
        print(terminal_output)

        # Print explicit spend windows (easy to parse by automations)
        windows = report['spend_windows']
        print("\nSpend windows:")
        print(f"- 24h: ${windows['24h']['cost']:.2f}")
        print(f"- 48h: ${windows['48h']['cost']:.2f}")
        print(f"- week: ${windows['week']['cost']:.2f}")
        print(f"- month: ${windows['month']['cost']:.2f}")

        # Generate image
        image_path = self.generate_image(report)

        if dry_run:
            print(f"\n[Dry run] Image saved to: {image_path}")
            return

        if send and image_path:
            print("\nSending to Telegram...")
            summary = report['summary']

            # Get fallback chain for caption
            fallback_chain = self.get_fallback_chain()

            # Styled HTML caption
            caption = f"""<b>⚡ OPENCLAW USAGE REPORT</b>

💸 <b>Spend windows:</b>
• 24h: ${windows['24h']['cost']:.2f}
• 48h: ${windows['48h']['cost']:.2f}
• week: ${windows['week']['cost']:.2f}
• month: ${windows['month']['cost']:.2f}

🔄 <b>Fallback Chain:</b>"""

            for item in fallback_chain[:4]:
                emoji = "▶" if item['type'] == 'primary' else "└"
                model_short = item['model'].split('/')[-1]
                caption += f"\n{emoji} {model_short}"

            caption += f"""
📊 <b>Sessions:</b> {summary['total_sessions']} active / {summary.get('session_count', 0)} total
🔤 <b>Tokens:</b> {summary['total_tokens']:,}

🏆 <b>Top Models:</b>"""

            for i, model in enumerate(report['models'][:3]):
                emoji = ["🥇", "🥈", "🥉"][i]
                caption += f"\n{emoji} {model['model']}: {model['tokens']:,} ({model['percent']}%)"

            self.send_to_telegram(image_path, caption)


def main():
    parser = argparse.ArgumentParser(description='OpenClaw Usage Monitor')
    parser.add_argument('--period', choices=['today', 'day', '24h', '48h', 'week', 'month'], default='today',
                       help='Report period')
    parser.add_argument('--now', action='store_true',
                       help='Generate and send report now')
    parser.add_argument('--send', action='store_true',
                       help='Send to Telegram')
    parser.add_argument('--dry-run', action='store_true',
                       help='Generate without sending')
    parser.add_argument('--test', action='store_true',
                       help='Test mode')
    
    args = parser.parse_args()
    
    monitor = UsageMonitor()
    
    if args.test:
        print("✅ Usage monitor is working!")
        print(f"Data directory: {monitor.data_dir}")
        return
    
    monitor.run(
        period=args.period,
        send=args.send or args.now,
        dry_run=args.dry_run
    )


if __name__ == '__main__':
    main()
