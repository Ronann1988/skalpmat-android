"""
SKALPMAT V7 — Полная интеграция со всеми улучшениями
✅ Раздельные лимиты позиций для MR и AS стратегий
✅ Раздельные cooldown для каждой стратегии
✅ Auto-restart мониторинга при запуске бота
✅ Smart Trailing Stop (ATR-based + step-based)
✅ Anti-spam система сигналов
✅ Fallback расчет PnL
✅ Улучшенные настройки на русском языке
✅ Checkbox для включения/отключения Smart Trailing Stop
✅ Гибкая система закрытия позиций (TP/Trailing/частичное)
✅ Проверка асимметричного исполнения MR ног
"""
import flet as ft
import threading
import queue
import os
import sys
import time
import math
import json
import logging
import sqlite3
import hashlib
import re
import requests
import pandas as pd
import numpy as np
import telebot
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dotenv import load_dotenv
from decimal import Decimal, ROUND_DOWN
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set
from enum import Enum
from threading import Thread, Lock
import gate_api
from gate_api.exceptions import ApiException, GateApiException
from scipy import stats as scipy_stats

# ==================== БАЗОВЫЕ ПУТИ ====================
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent.resolve()
else:
    BASE_DIR = Path(__file__).parent.resolve()

ENV_PATH = BASE_DIR / ".env"
DB_PATH = BASE_DIR / "synergy_bot.db"
LOG_FILE = BASE_DIR / "synergy_bot.log"
ICON_PATH = BASE_DIR / "1.ico"

# ==================== ЛОГИРОВАНИЕ ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('skalpMat')

# ==================== ГЛОБАЛЬНЫЕ БЛОКИРОВКИ ====================
lock = Lock()
message_lock = Lock()
sent_messages = set()
last_signal_time = {}
last_close_time = {}
last_signal_candle = {}

# ✅ Раздельные cooldown для каждой стратегии
mr_last_close_time = {}
as_last_close_time = {}

# ✅ Для предотвращения дублирования сообщений о закрытии
recently_closed = {}

# ✅ ANTI-SPAM: Хранилище последних сигналов
signal_cooldowns = {}
SIGNAL_COOLDOWN_SECONDS = 300  # 5 минут между одинаковыми сигналами

# ==================== КОНФИГ ПО УМОЛЧАНИЮ ====================
DEFAULT_ENV = """# ============================================================================
SKALPMAT V7 — НАСТРОЙКИ (ПОЛНАЯ ВЕРСИЯ)
============================================================================

==================== Telegram ====================
TELEGRAM_TOKEN=
TELEGRAM_CHAT_ID=

==================== Gate.io DEMO ====================
DEMO_API_KEY=
DEMO_API_SECRET=

==================== Gate.io REAL ====================
REAL_API_KEY=
REAL_API_SECRET=

==================== Текущий тип аккаунта ====================
ACCOUNT_TYPE=demo

==================== Режим работы ====================
TRADING_MODE=signals_only

==================== Стратегии ====================
STRATEGY_MEAN_REVERSION=True
STRATEGY_ADAPTIVE_SCALPING=True

==================== Mean Reversion Strategy ====================
MR_SYMBOLS=BTC_USDT,ETH_USDT
MR_TIMEFRAMES=15m,30m
MR_LOOKBACK_WINDOW=60
MR_ENTRY_ZSCORE=1.5
MR_TAKE_PROFIT_ZSCORE=0.5
MR_HURST_THRESHOLD=0.5
MR_POSITION_SIZE_PCT=5.0
MR_STOP_LOSS_PCT=2.0
MR_MAX_POSITIONS=2
MR_COOLDOWN_SECONDS=120

==================== Adaptive Scalping Strategy (PRICE-BASED) ====================
AS_SYMBOLS=BTC_USDT,ETH_USDT,SOL_USDT,XRP_USDT
AS_TIMEFRAMES=5m,15m
AS_INITIAL_CAPITAL=1000.0
AS_POSITION_SIZE_PCT=10.0
AS_MAX_POSITIONS=3
AS_COOLDOWN_SECONDS=60

# Price-based параметры
AS_TAKE_PROFIT_PCT=0.6
AS_STOP_LOSS_PCT=0.3
AS_RSI_OVERSOLD=35.0
AS_RSI_OVERBOUGHT=65.0
AS_BB_STD=2.5
AS_VOLUME_THRESHOLD=1.3

# Smart Trailing Stop
AS_USE_SMART_TRAILING=True
AS_TRAILING_START_PCT=0.3
AS_TRAILING_MIN_DISTANCE=0.2
AS_TRAILING_ATR_MULT=1.5
AS_TRAILING_STEP_PCT=0.1

# Режим закрытия при триггере трейлинга
# trailing - использовать трейлинг-стоп (перемещать стоп)
# tp - закрыть позицию полностью или частично на уровне триггера
TRAILING_CLOSE_MODE=trailing
TRAILING_CLOSE_PERCENT=100

# Self-optimization
AS_AUTO_ADJUST=True
AS_ADAPTATION_WINDOW=50
AS_MIN_WIN_RATE=0.50
AS_MAX_DRAWDOWN_PCT=5.0

==================== Общие настройки ====================
LEVERAGE=10
MARGIN_MODE=cross
ORDER_TYPE=percentage
QTY_PERCENTAGE=5.0
FIXED_VOLUME=100.0
TRADING_FEE=0.1
MAX_OPEN_POSITIONS=5
SCAN_INTERVAL=15
TRAILING_INTERVAL=3.0

# TP/SL настройки
INITIAL_STOP_PERCENTAGE=3.0
TRIGGER_PROFIT_PERCENTAGE=5.0
PROFIT_LOCK_PERCENTAGE=2.0
TRAILING_PERCENTAGE=1.0

# Защита
DAILY_LOSS_LIMIT=3
USE_TP=True
USE_SL=True
TP_CLOSE_PERCENT=100

# Усреднение
AVERAGING_ENABLED=False
AVERAGING_PAUSE=300
"""

def ensure_env_exists():
    if not ENV_PATH.exists():
        with open(ENV_PATH, 'w', encoding='utf-8') as f:
            f.write(DEFAULT_ENV)
        return True
    return False

def load_config():
    load_dotenv(ENV_PATH, override=True)

    def get_bool(key, default=False):
        val = os.getenv(key, str(default)).strip().lower()
        return val in ('true', '1', 'yes')

    account_type = os.getenv('ACCOUNT_TYPE', 'demo').strip().lower()

    if account_type == 'real':
        api_key = os.getenv('REAL_API_KEY', '').strip()
        api_secret = os.getenv('REAL_API_SECRET', '').strip()
    else:
        api_key = os.getenv('DEMO_API_KEY', '').strip()
        api_secret = os.getenv('DEMO_API_SECRET', '').strip()

    return {
        'TELEGRAM_TOKEN': os.getenv('TELEGRAM_TOKEN', '').strip(),
        'TELEGRAM_CHAT_ID': os.getenv('TELEGRAM_CHAT_ID', '').strip(),
        'GATEIO_API_KEY': api_key,
        'GATEIO_API_SECRET': api_secret,
        'DEMO_API_KEY': os.getenv('DEMO_API_KEY', '').strip(),
        'DEMO_API_SECRET': os.getenv('DEMO_API_SECRET', '').strip(),
        'REAL_API_KEY': os.getenv('REAL_API_KEY', '').strip(),
        'REAL_API_SECRET': os.getenv('REAL_API_SECRET', '').strip(),
        'ACCOUNT_TYPE': account_type,
        'TRADING_MODE': os.getenv('TRADING_MODE', 'signals_only').strip().lower(),
        'STRATEGY_MEAN_REVERSION': get_bool('STRATEGY_MEAN_REVERSION', True),
        'STRATEGY_ADAPTIVE_SCALPING': get_bool('STRATEGY_ADAPTIVE_SCALPING', True),
        'MR_SYMBOLS': [s.strip() for s in os.getenv('MR_SYMBOLS', 'BTC_USDT,ETH_USDT').split(',') if s.strip()],
        'MR_TIMEFRAMES': [t.strip() for t in os.getenv('MR_TIMEFRAMES', '15m,30m').split(',') if t.strip()],
        'MR_LOOKBACK_WINDOW': int(os.getenv('MR_LOOKBACK_WINDOW', '60')),
        'MR_ENTRY_ZSCORE': float(os.getenv('MR_ENTRY_ZSCORE', '1.5')),
        'MR_TAKE_PROFIT_ZSCORE': float(os.getenv('MR_TAKE_PROFIT_ZSCORE', '0.5')),
        'MR_HURST_THRESHOLD': float(os.getenv('MR_HURST_THRESHOLD', '0.5')),
        'MR_POSITION_SIZE_PCT': float(os.getenv('MR_POSITION_SIZE_PCT', '5.0')),
        'MR_STOP_LOSS_PCT': float(os.getenv('MR_STOP_LOSS_PCT', '2.0')),
        'MR_MAX_POSITIONS': int(os.getenv('MR_MAX_POSITIONS', '2')),
        'MR_COOLDOWN_SECONDS': int(os.getenv('MR_COOLDOWN_SECONDS', '120')),
        'AS_SYMBOLS': [s.strip() for s in os.getenv('AS_SYMBOLS', 'BTC_USDT,ETH_USDT,SOL_USDT,XRP_USDT').split(',') if s.strip()],
        'AS_TIMEFRAMES': [t.strip() for t in os.getenv('AS_TIMEFRAMES', '5m,15m').split(',') if t.strip()],
        'AS_INITIAL_CAPITAL': float(os.getenv('AS_INITIAL_CAPITAL', '1000.0')),
        'AS_POSITION_SIZE_PCT': float(os.getenv('AS_POSITION_SIZE_PCT', '10.0')),
        'AS_MAX_POSITIONS': int(os.getenv('AS_MAX_POSITIONS', '3')),
        'AS_COOLDOWN_SECONDS': int(os.getenv('AS_COOLDOWN_SECONDS', '60')),
        'AS_TAKE_PROFIT_PCT': float(os.getenv('AS_TAKE_PROFIT_PCT', '0.6')),
        'AS_STOP_LOSS_PCT': float(os.getenv('AS_STOP_LOSS_PCT', '0.3')),
        'AS_RSI_OVERSOLD': float(os.getenv('AS_RSI_OVERSOLD', '35.0')),
        'AS_RSI_OVERBOUGHT': float(os.getenv('AS_RSI_OVERBOUGHT', '65.0')),
        'AS_BB_STD': float(os.getenv('AS_BB_STD', '2.5')),
        'AS_VOLUME_THRESHOLD': float(os.getenv('AS_VOLUME_THRESHOLD', '1.3')),
        'AS_USE_SMART_TRAILING': get_bool('AS_USE_SMART_TRAILING', True),
        'AS_TRAILING_START_PCT': float(os.getenv('AS_TRAILING_START_PCT', '0.3')),
        'AS_TRAILING_MIN_DISTANCE': float(os.getenv('AS_TRAILING_MIN_DISTANCE', '0.2')),
        'AS_TRAILING_ATR_MULT': float(os.getenv('AS_TRAILING_ATR_MULT', '1.5')),
        'AS_TRAILING_STEP_PCT': float(os.getenv('AS_TRAILING_STEP_PCT', '0.1')),
        'TRAILING_CLOSE_MODE': os.getenv('TRAILING_CLOSE_MODE', 'trailing').strip().lower(),
        'TRAILING_CLOSE_PERCENT': float(os.getenv('TRAILING_CLOSE_PERCENT', '100')),
        'AS_AUTO_ADJUST': get_bool('AS_AUTO_ADJUST', True),
        'AS_ADAPTATION_WINDOW': int(os.getenv('AS_ADAPTATION_WINDOW', '50')),
        'AS_MIN_WIN_RATE': float(os.getenv('AS_MIN_WIN_RATE', '0.50')),
        'AS_MAX_DRAWDOWN_PCT': float(os.getenv('AS_MAX_DRAWDOWN_PCT', '5.0')),
        'LEVERAGE': int(os.getenv('LEVERAGE', '10')),
        'MARGIN_MODE': os.getenv('MARGIN_MODE', 'cross').strip().lower(),
        'ORDER_TYPE': os.getenv('ORDER_TYPE', 'percentage').strip().lower(),
        'QTY_PERCENTAGE': float(os.getenv('QTY_PERCENTAGE', '5.0')),
        'FIXED_VOLUME': float(os.getenv('FIXED_VOLUME', '100.0')),
        'TRADING_FEE': float(os.getenv('TRADING_FEE', '0.1')),
        'MAX_OPEN_POSITIONS': int(os.getenv('MAX_OPEN_POSITIONS', '5')),
        'SCAN_INTERVAL': int(os.getenv('SCAN_INTERVAL', '15')),
        'TRAILING_INTERVAL': float(os.getenv('TRAILING_INTERVAL', '3.0')),
        'INITIAL_STOP_PERCENTAGE': float(os.getenv('INITIAL_STOP_PERCENTAGE', '3.0')),
        'TRIGGER_PROFIT_PERCENTAGE': float(os.getenv('TRIGGER_PROFIT_PERCENTAGE', '5.0')),
        'PROFIT_LOCK_PERCENTAGE': float(os.getenv('PROFIT_LOCK_PERCENTAGE', '2.0')),
        'TRAILING_PERCENTAGE': float(os.getenv('TRAILING_PERCENTAGE', '1.0')),
        'DAILY_LOSS_LIMIT': int(os.getenv('DAILY_LOSS_LIMIT', '3')),
        'USE_TP': get_bool('USE_TP', True),
        'USE_SL': get_bool('USE_SL', True),
        'TP_CLOSE_PERCENT': float(os.getenv('TP_CLOSE_PERCENT', '100')),
        'AVERAGING_ENABLED': get_bool('AVERAGING_ENABLED', False),
        'AVERAGING_PAUSE': float(os.getenv('AVERAGING_PAUSE', '300')),
    }

# ==================== БАЗА ДАННЫХ ====================
def get_db_connection():
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        logger.error(f"Ошибка подключения к БД {DB_PATH}: {e}")
        raise

def init_database():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                side TEXT,
                price REAL,
                amount REAL,
                timestamp INTEGER,
                status TEXT,
                timescale TEXT,
                current_stop_price REAL,
                open_order_id TEXT,
                close_order_id TEXT,
                average_entry_price REAL,
                trailing_active INTEGER DEFAULT 0,
                highest_price REAL,
                lowest_price REAL,
                close_reason TEXT,
                close_price REAL,
                pnl REAL DEFAULT 0.0,
                fees REAL DEFAULT 0.0,
                original_stop_price REAL,
                trailing_stop_price REAL,
                margin REAL,
                balance_at_open REAL,
                signal_id TEXT,
                open_time INTEGER,
                trailing_start_time INTEGER,
                signal_tp_price REAL,
                signal_sl_price REAL,
                strategy TEXT,
                market_regime TEXT,
                optimized_params TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tp_config (
                timescale TEXT PRIMARY KEY,
                stop_loss_percentage REAL,
                trigger_profit_percentage REAL,
                trailing_percentage REAL,
                profit_lock_percentage REAL,
                pnl_based_trailing BOOLEAN DEFAULT 0
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stats (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                closed_trades_counter INTEGER DEFAULT 0
            )
        ''')
        cursor.execute("INSERT OR IGNORE INTO stats (id, closed_trades_counter) VALUES (1, 0)")
        cursor.execute("PRAGMA table_info(trades)")
        existing_columns = [col[1] for col in cursor.fetchall()]

        migrations = {
            'market_regime': 'TEXT',
            'optimized_params': 'TEXT',
            'signal_tp_price': 'REAL',
            'signal_sl_price': 'REAL',
            'open_time': 'INTEGER',
            'trailing_start_time': 'INTEGER',
            'margin': 'REAL',
            'balance_at_open': 'REAL',
            'signal_id': 'TEXT',
            'original_stop_price': 'REAL',
            'trailing_stop_price': 'REAL',
            'close_price': 'REAL',
            'strategy': 'TEXT',
        }

        for col_name, col_type in migrations.items():
            if col_name not in existing_columns:
                try:
                    cursor.execute(f'ALTER TABLE trades ADD COLUMN {col_name} {col_type}')
                    logger.info(f"✅ Миграция: добавлен столбец {col_name}")
                except Exception as e:
                    logger.error(f"❌ Ошибка миграции {col_name}: {e}")

        conn.commit()
        logger.info("✅ База данных инициализирована")

def add_trade(symbol, side, price, amount, timestamp, status, timescale,
              current_stop_price=None, open_order_id=None, average_entry_price=None,
              trailing_active=0, highest_price=None, lowest_price=None,
              close_reason=None, original_stop_price=None, trailing_stop_price=None,
              margin=None, balance_at_open=None, signal_id=None, open_time=None,
              signal_tp_price=None, signal_sl_price=None, strategy=None,
              market_regime=None, optimized_params=None):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO trades (symbol, side, price, amount, timestamp, status, timescale,
                current_stop_price, open_order_id, average_entry_price, trailing_active,
                highest_price, lowest_price, close_reason, original_stop_price,
                trailing_stop_price, margin, balance_at_open, signal_id, open_time,
                signal_tp_price, signal_sl_price, strategy, market_regime, optimized_params)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (symbol, side, price, amount, timestamp, status, timescale,
              current_stop_price, open_order_id, average_entry_price, trailing_active,
              highest_price, lowest_price, close_reason, original_stop_price,
              trailing_stop_price, margin, balance_at_open, signal_id, open_time,
              signal_tp_price, signal_sl_price, strategy, market_regime, optimized_params))
        conn.commit()
        return cursor.lastrowid

def get_open_trades():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trades WHERE status = 'OPEN'")
        return [dict(t) for t in cursor.fetchall()]

def get_open_trades_by_strategy(strategy):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trades WHERE status = 'OPEN' AND strategy = ?", (strategy,))
        return [dict(t) for t in cursor.fetchall()]

def get_open_trades_by_symbol_and_side(symbol, side):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''SELECT * FROM trades
                WHERE symbol = ? AND side = ? AND status = 'OPEN' ''', (symbol, side))
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Ошибка получения сделок {symbol} ({side}): {e}")
        return []

def get_trade_by_id(trade_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM trades WHERE trade_id = ?', (trade_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def update_trade_status(trade_id, status, **kwargs):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        fields = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        values = list(kwargs.values()) + [trade_id]
        query = f"UPDATE trades SET status = ?, {fields} WHERE trade_id = ?"
        cursor.execute(query, [status] + values)
        conn.commit()

        if status == "CLOSED":
            cursor.execute("UPDATE trades SET timestamp = ? WHERE trade_id = ?",
                           (int(time.time()), trade_id))
            cursor.execute("UPDATE trades SET trailing_active = 0, trailing_stop_price = NULL WHERE trade_id = ?",
                           (trade_id,))
            cursor.execute("UPDATE stats SET closed_trades_counter = COALESCE(closed_trades_counter, 0) + 1 WHERE id = 1")
        conn.commit()

def get_tp_config(timescale='1h'):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''SELECT stop_loss_percentage, trigger_profit_percentage,
            trailing_percentage, profit_lock_percentage, pnl_based_trailing
            FROM tp_config WHERE timescale = ?''', (timescale,))
        result = cursor.fetchone()
        if result:
            return {
                'stop_loss_percentage': result[0],
                'trigger_profit_percentage': result[1],
                'trailing_percentage': result[2],
                'profit_lock_percentage': result[3],
                'pnl_based_trailing': result[4] if len(result) > 4 else False
            }
        return {
            'stop_loss_percentage': 0.3,
            'trigger_profit_percentage': 0.6,
            'trailing_percentage': 0.2,
            'profit_lock_percentage': 0.3,
            'pnl_based_trailing': False
        }

def set_tp_config(timescale, stop_loss, trigger_profit, trailing_limit, profit_lock, pnl_based=False):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO tp_config
            (timescale, stop_loss_percentage, trigger_profit_percentage,
             trailing_percentage, profit_lock_percentage, pnl_based_trailing)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (timescale, stop_loss, trigger_profit, trailing_limit, profit_lock, pnl_based))
        conn.commit()
        logger.info(f"✅ Настройки TP/SL сохранены для {timescale}")

def check_daily_loss_limit(daily_limit):
    today = int(time.time() // 86400) * 86400
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM trades
            WHERE status = 'CLOSED' AND timestamp >= ?
            AND close_price IS NOT NULL
            AND ((side = 'buy' AND close_price < price)
                 OR (side = 'sell' AND close_price > price))
        ''', (today,))
        loss_count = cursor.fetchone()[0]
        return loss_count >= daily_limit

def check_max_open_trades(max_trades):
    open_trades = get_open_trades()
    return len(open_trades) >= max_trades

def check_max_open_trades_by_strategy(strategy, max_trades):
    open_trades = get_open_trades_by_strategy(strategy)
    return len(open_trades) >= max_trades

# ✅ ANTI-SPAM: Проверка cooldown для сигнала
def can_send_signal(symbol, side, signal_type='entry'):
    key = (symbol, side, signal_type)
    current_time = time.time()

    if key in signal_cooldowns:
        time_since_last = current_time - signal_cooldowns[key]
        if time_since_last < SIGNAL_COOLDOWN_SECONDS:
            remaining = int(SIGNAL_COOLDOWN_SECONDS - time_since_last)
            logger.info(f"⏳ Signal cooldown для {symbol} ({side}): осталось {remaining}с")
            return False

    signal_cooldowns[key] = current_time
    return True

# ✅ AUTO-RESTART: Сброс состояния мониторинга
def reset_monitoring_state():
    global last_signal_time, last_close_time, last_signal_candle
    global signal_cooldowns, recently_closed
    logger.info("🔄 Сброс состояния мониторинга...")

    current_time = time.time()
    cutoff_time = current_time - 3600

    last_signal_time = {k: v for k, v in last_signal_time.items() if v > cutoff_time}
    last_close_time = {k: v for k, v in last_close_time.items() if v > cutoff_time}
    last_signal_candle = {k: v for k, v in last_signal_candle.items() if v > cutoff_time}
    signal_cooldowns = {k: v for k, v in signal_cooldowns.items() if v > cutoff_time}
    recently_closed = {k: v for k, v in recently_closed.items() if v > cutoff_time}

    logger.info(f"✅ Состояние сброшено. Активных сигналов: {len(last_signal_time)}")

def _format_duration(seconds):
    if seconds < 0:
        return "N/A"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"

# ==================== TELEGRAM УВЕДОМЛЕНИЯ ====================
class TelegramNotifier:
    def __init__(self, token, chat_id):
        self.token = token
        self.chat_id = chat_id
        self.bot = None
        if token and chat_id:
            try:
                self.bot = telebot.TeleBot(token)
                # ✅ Отключаем встроенный polling, он будет запущен в TelegramCommands
                logger.info("✅ Telegram бот инициализирован (без polling)")
            except Exception as e:
                logger.error(f"Ошибка инициализации Telegram: {e}")

    def send(self, text, parse_mode=None):
        if not self.bot or not self.chat_id:
            return
        try:
            if parse_mode is None:
                text = re.sub(r'[*_`]', '', text)
            self.bot.send_message(chat_id=self.chat_id, text=text, parse_mode=parse_mode)
        except Exception as e:
            error_msg = str(e)
            if '409' in error_msg:
                logger.warning(f"⚠️ Telegram 409: конфликт polling, сообщение не отправлено")
            else:
                logger.error(f"⚠️ Ошибка отправки Telegram: {e}")

# ==================== SMART TRAILING STOP ====================
class SmartTrailingStop:
    def __init__(self, config):
        self.config = config
        self.initial_stop = None
        self.current_stop = None
        self.highest_price = None
        self.lowest_price = None
        self.entry_price = None
        self.entry_time = None
        self.max_profit_seen = 0
        self.side = None
        self.trailing_activated = False

    def start(self, entry_price: float, entry_time, side: str, initial_sl_pct: float, atr: float = None):
        self.entry_price = entry_price
        self.entry_time = entry_time
        self.side = side
        self.highest_price = entry_price if side == 'buy' else None
        self.lowest_price = entry_price if side == 'sell' else None
        self.max_profit_seen = 0
        self.trailing_activated = False

        initial_sl = initial_sl_pct / 100
        if side == 'buy':
            self.initial_stop = entry_price * (1 - initial_sl)
        else:
            self.initial_stop = entry_price * (1 + initial_sl)

        self.current_stop = self.initial_stop

        if self.config.get('AS_USE_SMART_TRAILING', True) and atr:
            atr_distance = atr * self.config.get('AS_TRAILING_ATR_MULT', 1.5)
            if side == 'buy':
                atr_stop = entry_price - atr_distance
                self.current_stop = max(self.initial_stop, atr_stop)
            else:
                atr_stop = entry_price + atr_distance
                self.current_stop = min(self.initial_stop, atr_stop)

        logger.info(f"🎯 SmartTrailingStop START: {side} @ {entry_price:.4f}, SL={self.current_stop:.4f}")
        return self.current_stop

    def update(self, current_price: float, atr: float = None) -> Tuple[float, bool, str]:
        triggered = False
        trigger_type = 'none'

        if self.side == 'buy' and self.highest_price and current_price <= self.current_stop:
            triggered = True
            if self.trailing_activated:
                trigger_type = 'trailing_stop'
                logger.info(f"🛑 TRAILING STOP triggered: {self.side} @ {current_price:.4f} <= {self.current_stop:.4f}")
            else:
                trigger_type = 'initial_sl'
                logger.info(f"🛑 INITIAL STOP LOSS triggered: {self.side} @ {current_price:.4f} <= {self.current_stop:.4f}")
            return self.current_stop, triggered, trigger_type

        if self.side == 'sell' and self.lowest_price and current_price >= self.current_stop:
            triggered = True
            if self.trailing_activated:
                trigger_type = 'trailing_stop'
                logger.info(f"🛑 TRAILING STOP triggered: {self.side} @ {current_price:.4f} >= {self.current_stop:.4f}")
            else:
                trigger_type = 'initial_sl'
                logger.info(f"🛑 INITIAL STOP LOSS triggered: {self.side} @ {current_price:.4f} >= {self.current_stop:.4f}")
            return self.current_stop, triggered, trigger_type

        if self.highest_price is not None and current_price > self.highest_price:
            self.highest_price = current_price
            self.max_profit_seen = (current_price - self.entry_price) / self.entry_price

        if self.lowest_price is not None and current_price < self.lowest_price:
            self.lowest_price = current_price
            self.max_profit_seen = (self.entry_price - current_price) / self.entry_price

        trailing_start_pct = self.config.get('AS_TRAILING_START_PCT', 0.3) / 100
        if self.max_profit_seen >= trailing_start_pct:
            self.trailing_activated = True

        if not self.trailing_activated:
            return self.current_stop, triggered, trigger_type

        new_stop = None
        min_distance = self.config.get('AS_TRAILING_MIN_DISTANCE', 0.2) / 100

        if self.highest_price:
            fixed_stop = self.highest_price * (1 - min_distance)
            if self.config.get('AS_USE_SMART_TRAILING', True) and atr:
                atr_distance = atr * self.config.get('AS_TRAILING_ATR_MULT', 1.5)
                atr_stop = self.highest_price - atr_distance
                new_stop = max(fixed_stop, atr_stop)
            else:
                new_stop = fixed_stop
            new_stop = max(new_stop, self.current_stop)

        elif self.lowest_price:
            fixed_stop = self.lowest_price * (1 + min_distance)
            if self.config.get('AS_USE_SMART_TRAILING', True) and atr:
                atr_distance = atr * self.config.get('AS_TRAILING_ATR_MULT', 1.5)
                atr_stop = self.lowest_price + atr_distance
                new_stop = min(fixed_stop, atr_stop)
            else:
                new_stop = fixed_stop
            new_stop = min(new_stop, self.current_stop)

        step_pct = self.config.get('AS_TRAILING_STEP_PCT', 0.1) / 100
        if new_stop and step_pct > 0:
            profit_step = int(self.max_profit_seen / step_pct)
            if self.highest_price:
                step_stop = self.entry_price * (1 + profit_step * step_pct - min_distance)
                new_stop = max(new_stop, step_stop)
            elif self.lowest_price:
                step_stop = self.entry_price * (1 - profit_step * step_pct + min_distance)
                new_stop = min(new_stop, step_stop)

        if new_stop:
            self.current_stop = new_stop

        return self.current_stop, triggered, trigger_type

# ==================== MARKET REGIME DETECTOR ====================
class MarketRegime(Enum):
    FLAT_LOW_VOL = "flat_low_vol"
    FLAT_NORMAL = "flat_normal"
    TRENDING_WEAK = "trending_weak"
    TRENDING_STRONG = "trending_strong"
    VOLATILE = "volatile"
    CRASH = "crash"
    RECOVERY = "recovery"

class MarketRegimeDetector:
    def __init__(self, lookback=50):
        self.lookback = lookback

    def calculate_metrics(self, df: pd.DataFrame) -> Dict:
        if len(df) < self.lookback:
            return None

        recent = df.iloc[-self.lookback:]

        high_low = recent['high'] - recent['low']
        high_close = np.abs(recent['high'] - recent['close'].shift())
        low_close = np.abs(recent['low'] - recent['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = ranges.mean()
        atr_pct = atr / recent['close'].mean() * 100

        closes = recent['close'].values
        slope, intercept, r_value, p_value, std_err = scipy_stats.linregress(range(len(closes)), closes)
        trend_strength = abs(slope) / recent['close'].std() if recent['close'].std() > 0 else 0

        lags = range(2, 20)
        tau = [np.sqrt(np.std(np.subtract(closes[lag:], closes[:-lag]))) for lag in lags]
        try:
            hurst = np.polyfit(np.log(lags), np.log(tau), 1)[0]
        except:
            hurst = 0.5

        vol_ma = recent['volume'].mean()
        current_vol = df.iloc[-1]['volume']
        vol_spike = current_vol / vol_ma if vol_ma > 0 else 1.0

        price_range = (recent['high'].max() - recent['low'].min()) / recent['low'].min() * 100

        recent_returns = recent['close'].pct_change()
        max_move = abs(recent_returns).max() * 100

        return {
            'volatility_pct': atr_pct,
            'trend_strength': trend_strength,
            'hurst': hurst,
            'volume_spike': vol_spike,
            'price_range_pct': price_range,
            'max_move_pct': max_move,
            'rsi': df.iloc[-1].get('rsi', 50),
            'bb_width': self._calculate_bb_width(recent)
        }

    def _calculate_bb_width(self, df: pd.DataFrame) -> float:
        middle = df['close'].rolling(20).mean()
        std = df['close'].rolling(20).std()
        upper = middle + (std * 2.5)
        lower = middle - (std * 2.5)
        width = (upper - lower) / middle * 100
        return width.iloc[-1] if not pd.isna(width.iloc[-1]) else 0

    def detect_regime(self, df: pd.DataFrame) -> Tuple[MarketRegime, Dict]:
        metrics = self.calculate_metrics(df)
        if not metrics:
            return MarketRegime.FLAT_NORMAL, metrics

        if metrics['max_move_pct'] > 3.0:
            return MarketRegime.CRASH, metrics
        if metrics['volatility_pct'] > 2.0:
            return MarketRegime.VOLATILE, metrics
        if metrics['trend_strength'] > 0.8 and metrics['hurst'] > 0.6:
            return MarketRegime.TRENDING_STRONG, metrics
        if metrics['trend_strength'] > 0.4 or 0.55 < metrics['hurst'] < 0.6:
            return MarketRegime.TRENDING_WEAK, metrics
        if metrics['price_range_pct'] < 0.5 and metrics['volatility_pct'] < 0.3:
            return MarketRegime.FLAT_LOW_VOL, metrics
        if metrics['hurst'] < 0.5 and metrics['trend_strength'] < 0.4:
            return MarketRegime.FLAT_NORMAL, metrics
        if metrics['volatility_pct'] > 1.0 and metrics['max_move_pct'] > 2.0:
            return MarketRegime.RECOVERY, metrics

        return MarketRegime.FLAT_NORMAL, metrics

# ==================== SELF-OPTIMIZER ====================
class SelfOptimizer:
    def __init__(self):
        self.history = []
        self.base_params = {
            'take_profit_pct': [0.004, 0.005, 0.006, 0.008, 0.010],
            'stop_loss_pct': [0.002, 0.003, 0.004, 0.005],
            'rsi_oversold': [25, 30, 35, 40],
            'rsi_overbought': [60, 65, 70, 75],
            'volume_threshold': [1.2, 1.3, 1.5, 2.0],
            'trailing_start_pct': [0.002, 0.003, 0.005, 0.008],
            'trailing_min_distance': [0.001, 0.002, 0.003, 0.004],
            'trailing_atr_mult': [1.0, 1.5, 2.0, 2.5],
        }

    def optimize(self, df: pd.DataFrame, current_params: Dict) -> Dict:
        if len(df) < 100:
            return current_params

        logger.info("Запуск self-optimization...")

        best_params = current_params.copy()
        best_pf = 0

        for tp in self.base_params['take_profit_pct']:
            for sl in self.base_params['stop_loss_pct']:
                if tp <= sl:
                    continue
                for rsi_os in self.base_params['rsi_oversold']:
                    for rsi_ob in self.base_params['rsi_overbought']:
                        if rsi_os >= rsi_ob:
                            continue

                        trades = self._quick_backtest(
                            df, tp, sl, rsi_os, rsi_ob,
                            current_params.get('volume_threshold', 1.3)
                        )

                        if trades:
                            winning = sum(1 for t in trades if t > 0)
                            losing = sum(1 for t in trades if t <= 0)
                            win_rate = winning / len(trades)

                            if win_rate < 0.3:
                                continue

                            if losing > 0:
                                pf = sum(t for t in trades if t > 0) / abs(sum(t for t in trades if t <= 0))
                            else:
                                pf = float('inf') if winning > 0 else 0

                            if pf > best_pf and len(trades) >= 3:
                                best_pf = pf
                                best_params = {
                                    'take_profit_pct': tp,
                                    'stop_loss_pct': sl,
                                    'rsi_oversold': rsi_os,
                                    'rsi_overbought': rsi_ob,
                                    'volume_threshold': current_params.get('volume_threshold', 1.3),
                                    'trailing_start_pct': current_params.get('trailing_start_pct', 0.003),
                                    'trailing_min_distance': current_params.get('trailing_min_distance', 0.002),
                                    'trailing_atr_mult': current_params.get('trailing_atr_mult', 1.5),
                                }

        if best_params['take_profit_pct'] <= 0:
            best_params['take_profit_pct'] = 0.006
        if best_params['stop_loss_pct'] <= 0:
            best_params['stop_loss_pct'] = 0.003
        if best_params['take_profit_pct'] <= best_params['stop_loss_pct']:
            best_params['take_profit_pct'] = best_params['stop_loss_pct'] * 2

        logger.info(f"✅ Optimization complete. Best PF: {best_pf:.2f}")
        logger.info(f"New params: TP={best_params['take_profit_pct']:.4f}, SL={best_params['stop_loss_pct']:.4f}")
        return best_params

    def _quick_backtest(self, df: pd.DataFrame, tp: float, sl: float,
                        rsi_os: float, rsi_ob: float, vol_thresh: float) -> List[float]:
        trades = []
        position = None

        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        middle = df['close'].rolling(20).mean()
        std = df['close'].rolling(20).std()
        upper = middle + (std * 2.5)
        lower = middle - (std * 2.5)
        bb_pct = (df['close'] - lower) / (upper - lower)

        for i in range(50, len(df)):
            if position:
                if position['side'] == 'LONG':
                    high_pct = (df.iloc[i]['high'] - position['entry']) / position['entry']
                    low_pct = (df.iloc[i]['low'] - position['entry']) / position['entry']

                    if high_pct >= tp:
                        trades.append(tp)
                        position = None
                    elif low_pct <= -sl:
                        trades.append(-sl)
                        position = None

                elif position['side'] == 'SHORT':
                    low_pct = (position['entry'] - df.iloc[i]['low']) / position['entry']
                    high_pct = (position['entry'] - df.iloc[i]['high']) / position['entry']

                    if low_pct >= tp:
                        trades.append(tp)
                        position = None
                    elif high_pct <= -sl:
                        trades.append(-sl)
                        position = None
            else:
                if pd.isna(rsi.iloc[i]) or pd.isna(bb_pct.iloc[i]):
                    continue

                if bb_pct.iloc[i] < 0.1 and rsi.iloc[i] < rsi_os:
                    position = {'side': 'LONG', 'entry': df.iloc[i]['close']}
                elif bb_pct.iloc[i] > 0.9 and rsi.iloc[i] > rsi_ob:
                    position = {'side': 'SHORT', 'entry': df.iloc[i]['close']}

        return trades

# ==================== ADAPTIVE SCALPING STRATEGY ====================
class AdaptiveScalpingStrategy:
    def __init__(self, config, symbol_tf_key: str = "unknown"):
        self.config = config
        self.symbol_tf_key = symbol_tf_key
        self.regime_detector = MarketRegimeDetector()
        self.optimizer = SelfOptimizer()
        self.trailing_stops = {}
        self.current_regime = MarketRegime.FLAT_NORMAL
        self.optimized_params = {
            'take_profit_pct': config['AS_TAKE_PROFIT_PCT'] / 100,
            'stop_loss_pct': config['AS_STOP_LOSS_PCT'] / 100,
            'rsi_oversold': config['AS_RSI_OVERSOLD'],
            'rsi_overbought': config['AS_RSI_OVERBOUGHT'],
            'volume_threshold': config['AS_VOLUME_THRESHOLD'],
            'bb_std': config['AS_BB_STD'],
            'trailing_start_pct': config['AS_TRAILING_START_PCT'] / 100,
            'trailing_min_distance': config['AS_TRAILING_MIN_DISTANCE'] / 100,
            'trailing_atr_mult': config['AS_TRAILING_ATR_MULT'],
            'trailing_step_pct': config['AS_TRAILING_STEP_PCT'] / 100,
        }
        self.positions = {}
        self.trade_history = []
        self.last_optimization = 0
        self.trading_enabled = True
        self.last_regime_update = 0
        self.regime_update_interval = 60
        self.regime_limits = {
            MarketRegime.FLAT_LOW_VOL: {
                'enabled': False,
                'position_size_pct': 0.0,
                'reason': 'Too flat, no edge'
            },
            MarketRegime.FLAT_NORMAL: {
                'enabled': True,
                'position_size_pct': 0.15,
                'take_profit_pct': 0.005,
                'stop_loss_pct': 0.002,
                'rsi_oversold': 30.0,
                'rsi_overbought': 70.0,
                'trailing_start_pct': 0.003,
                'trailing_min_distance': 0.002,
                'trailing_atr_mult': 1.0,
            },
            MarketRegime.TRENDING_WEAK: {
                'enabled': True,
                'position_size_pct': 0.10,
                'take_profit_pct': 0.008,
                'stop_loss_pct': 0.004,
                'rsi_oversold': 35.0,
                'rsi_overbought': 65.0,
                'trailing_start_pct': 0.004,
                'trailing_min_distance': 0.003,
                'trailing_atr_mult': 1.5,
            },
            MarketRegime.TRENDING_STRONG: {
                'enabled': True,
                'position_size_pct': 0.25,
                'take_profit_pct': 0.012,
                'stop_loss_pct': 0.006,
                'rsi_oversold': 40.0,
                'rsi_overbought': 60.0,
                'trend_following': True,
                'trailing_start_pct': 0.005,
                'trailing_min_distance': 0.004,
                'trailing_atr_mult': 2.0,
            },
            MarketRegime.VOLATILE: {
                'enabled': True,
                'position_size_pct': 0.10,
                'take_profit_pct': 0.015,
                'stop_loss_pct': 0.008,
                'bb_std': 3.0,
                'volume_threshold': 2.0,
                'trailing_start_pct': 0.008,
                'trailing_min_distance': 0.006,
                'trailing_atr_mult': 2.5,
            },
            MarketRegime.CRASH: {
                'enabled': False,
                'position_size_pct': 0.0,
                'reason': 'Market crash, preserve capital'
            },
            MarketRegime.RECOVERY: {
                'enabled': True,
                'position_size_pct': 0.05,
                'take_profit_pct': 0.010,
                'stop_loss_pct': 0.003,
                'reason': 'Post-crash, high risk',
                'trailing_start_pct': 0.004,
                'trailing_min_distance': 0.003,
                'trailing_atr_mult': 1.5,
            }
        }

    def update_regime(self, df: pd.DataFrame) -> None:
        current_time = time.time()
        if current_time - self.last_regime_update < self.regime_update_interval:
            return

        self.last_regime_update = current_time
        self.current_regime, metrics = self.regime_detector.detect_regime(df)

        logger.info(f"[{self.symbol_tf_key}] Market Regime: {self.current_regime.value}")

        regime_config = self.regime_limits[self.current_regime]

        if not regime_config['enabled']:
            self.trading_enabled = False
            logger.warning(f"⚠️ [{self.symbol_tf_key}] TRADING PAUSED: {regime_config.get('reason', 'Unfavorable conditions')}")
        else:
            self.trading_enabled = True
            if self.config.get('AS_AUTO_ADJUST', True):
                for key, value in regime_config.items():
                    if key in self.optimized_params and key != 'trend_following':
                        self.optimized_params[key] = value
                        logger.info(f"  [{self.symbol_tf_key}] Adjusted {key}: {value}")

    def maybe_optimize(self, df: pd.DataFrame) -> None:
        adaptation_window = self.config.get('AS_ADAPTATION_WINDOW', 50)
        if len(df) - self.last_optimization < adaptation_window:
            return

        logger.info("=" * 60)
        logger.info(f"SELF-OPTIMIZATION TRIGGERED for [{self.symbol_tf_key}]")
        logger.info("=" * 60)

        new_params = self.optimizer.optimize(df, self.optimized_params)
        if new_params != self.optimized_params:
            self.optimized_params = new_params
            logger.info(f"✅ [{self.symbol_tf_key}] Parameters updated")

        self.last_optimization = len(df)

    def check_performance_limits(self) -> None:
        if len(self.trade_history) < 5:
            return

        recent = self.trade_history[-10:]
        recent_wins = sum(1 for t in recent if t.get('pnl_usd', 0) > 0)
        recent_win_rate = recent_wins / len(recent)

        if recent_win_rate < self.config['AS_MIN_WIN_RATE']:
            self.trading_enabled = False
            logger.warning(f"⚠️ [{self.symbol_tf_key}] TRADING PAUSED: Win rate {recent_win_rate*100:.1f}% < {self.config['AS_MIN_WIN_RATE']*100:.0f}%")

    def calculate_indicators(self, df):
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        bb_std = self.optimized_params.get('bb_std', 2.5)
        middle = df['close'].rolling(20).mean()
        std = df['close'].rolling(20).std()
        df['bb_upper'] = middle + (std * bb_std)
        df['bb_lower'] = middle - (std * bb_std)
        df['bb_pct'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])

        vol_ma = df['volume'].rolling(20).mean()
        df['vol_ratio'] = df['volume'] / vol_ma

        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = tr.rolling(14).mean()

        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()

        return df

    def analyze(self, df, symbol):
        if not self.trading_enabled:
            return {'signal': None, 'regime': self.current_regime.value, 'reason': 'Trading paused'}

        if len(df) < 60:
            return None

        df = self.calculate_indicators(df.copy())
        regime, metrics = self.regime_detector.detect_regime(df)

        if regime in [MarketRegime.FLAT_LOW_VOL, MarketRegime.CRASH]:
            return {'signal': None, 'regime': regime.value, 'reason': f'Regime: {regime.value}'}

        row = df.iloc[-1]

        if pd.isna(row['rsi']) or pd.isna(row['bb_pct']) or pd.isna(row['vol_ratio']):
            return None

        signal = None
        rsi_os = self.optimized_params['rsi_oversold']
        rsi_ob = self.optimized_params['rsi_overbought']
        vol_thresh = self.optimized_params['volume_threshold']

        trend_following = self.regime_limits[self.current_regime].get('trend_following', False)

        if not trend_following:
            if row['bb_pct'] < 0.1 and row['rsi'] < rsi_os and row['vol_ratio'] > vol_thresh:
                signal = 'BUY'
        else:
            if row['rsi'] < 45 and row['vol_ratio'] > 1.0 and row['close'] > row['ema50']:
                signal = 'BUY'

        if not signal:
            if not trend_following:
                if row['bb_pct'] > 0.9 and row['rsi'] > rsi_ob and row['vol_ratio'] > vol_thresh:
                    signal = 'SELL'
            else:
                if row['rsi'] > 55 and row['vol_ratio'] > 1.0 and row['close'] < row['ema50']:
                    signal = 'SELL'

        return {
            'signal': signal,
            'regime': regime.value,
            'rsi': row['rsi'],
            'bb_pct': row['bb_pct'],
            'vol_ratio': row['vol_ratio'],
            'atr': row['atr'],
            'price': row['close'],
            'metrics': metrics,
        }

# ==================== MEAN REVERSION STRATEGY ====================
class HurstExponent:
    @staticmethod
    def calculate(prices: np.ndarray, max_lag: int = 20) -> float:
        if len(prices) < max_lag * 2:
            return 0.5
        lags = range(2, max_lag)
        tau = [max(1e-8, np.std(np.subtract(prices[lag:], prices[:-lag]))) for lag in lags]
        try:
            poly = np.polyfit(np.log(lags), np.log(tau), 1)
            return poly[0]
        except Exception:
            return 0.5

class MeanReversionStrategy:
    def __init__(self, config):
        self.config = config
        self.lookback = config['MR_LOOKBACK_WINDOW']
        self.entry_zscore = config['MR_ENTRY_ZSCORE']
        self.tp_zscore = config['MR_TAKE_PROFIT_ZSCORE']
        self.hurst_threshold = config['MR_HURST_THRESHOLD']
        self.positions = {}

    def calculate_hedge_ratio(self, price_a: np.ndarray, price_b: np.ndarray) -> float:
        if len(price_a) != len(price_b) or len(price_a) < 10:
            return 1.0
        try:
            A = np.vstack([price_b, np.ones(len(price_b))]).T
            beta, _, _, _ = np.linalg.lstsq(A, price_a, rcond=None)
            return beta[0] if beta[0] > 0 else 1.0
        except Exception:
            return 1.0

    def is_mean_reverting(self, prices: np.ndarray) -> bool:
        hurst = HurstExponent.calculate(prices, max_lag=min(10, len(prices) // 2))
        return hurst < self.hurst_threshold + 0.05

    def analyze_pair(self, df_a, df_b, symbol_a, symbol_b):
        if len(df_a) < self.lookback or len(df_b) < self.lookback:
            return None

        prices_a = df_a['close'].values[-self.lookback:]
        prices_b = df_b['close'].values[-self.lookback:]

        if not self.is_mean_reverting(prices_a) or not self.is_mean_reverting(prices_b):
            return None

        hedge_ratio = self.calculate_hedge_ratio(prices_a, prices_b)
        spread = prices_a[-1] - hedge_ratio * prices_b[-1]
        spread_series = prices_a - hedge_ratio * prices_b
        spread_mean = np.mean(spread_series)
        spread_std = np.std(spread_series)

        if spread_std < 1e-8:
            return None

        z_score = (spread - spread_mean) / spread_std

        signal = None
        if z_score > self.entry_zscore:
            signal = 'SELL_SPREAD'
        elif z_score < -self.entry_zscore:
            signal = 'BUY_SPREAD'

        key = (symbol_a, symbol_b)
        if key in self.positions:
            pos = self.positions[key]
            if pos['side'] == 'LONG' and z_score > -self.tp_zscore:
                signal = 'CLOSE_LONG'
            elif pos['side'] == 'SHORT' and z_score < self.tp_zscore:
                signal = 'CLOSE_SHORT'

        return {
            'signal': signal,
            'z_score': z_score,
            'hedge_ratio': hedge_ratio,
            'spread': spread,
            'price_a': prices_a[-1],
            'price_b': prices_b[-1],
        }

# ==================== GATE.IO API ====================
class GateIO:
    def __init__(self, api_key, api_secret, account_type='demo', leverage=10, margin_mode='cross',
                 order_type='percentage', qty_percentage=5.0, fixed_volume=100.0,
                 trailing_interval=3.0, config=None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.account_type = account_type
        self.leverage = leverage
        self.margin_mode = margin_mode
        self.order_type = order_type
        self.qty_percentage = min(qty_percentage, 50.0)
        self.fixed_volume = fixed_volume
        self.trailing_interval = trailing_interval
        self.config = config or {}
        self._unavailable_contracts = set()
        self._available_contracts_cache = None

        if account_type == 'real':
            api_url = "https://api.gateio.ws/api/v4"
        else:
            api_url = "https://api-testnet.gateapi.io/api/v4"

        logger.info(f"Gate.io API: {api_url} (тип: {account_type})")

        configuration = gate_api.Configuration(host=api_url, key=api_key, secret=api_secret)
        self.api_client = gate_api.ApiClient(configuration)
        self.futures_api = gate_api.FuturesApi(self.api_client)
        self.spot_api = gate_api.SpotApi(self.api_client)

        self.trailing_stop_manager = TrailingStopManager(self)

    def _normalize_positions(self, positions):
        if not positions:
            return positions
        for pos in positions:
            try:
                pos.size = float(float(getattr(pos, "size", 0))) if getattr(pos, 'size', None) is not None else 0.0
            except Exception:
                pos.size = 0.0
            try:
                if hasattr(pos, 'entry_price') and pos.entry_price is not None:
                    pos.entry_price = float(pos.entry_price)
            except Exception:
                pos.entry_price = 0.0
            try:
                if hasattr(pos, 'margin') and pos.margin is not None:
                    pos.margin = float(pos.margin)
            except Exception:
                pass
            try:
                if hasattr(pos, 'unrealised_pnl') and pos.unrealised_pnl is not None:
                    pos.unrealised_pnl = float(pos.unrealised_pnl)
            except Exception:
                pass
        return positions

    def check_permissions(self):
        try:
            self.futures_api.list_futures_accounts(settle='usdt')
            return True, "✅ API ключи валидны"
        except GateApiException as ex:
            return False, f"Ошибка API: {ex.label} - {ex.message}"
        except Exception as e:
            return False, f"❌ Ошибка проверки API: {e}"

    def test_connection(self):
        try:
            contracts = self.futures_api.list_futures_contracts(settle='usdt')
            return True, f"✅ Подключено. Доступно контрактов: {len(contracts)}"
        except Exception as e:
            return False, f"❌ Ошибка подключения: {e}"

    def validate_symbol(self, symbol):
        try:
            self.futures_api.get_futures_contract(settle='usdt', contract=symbol)
            return True
        except Exception:
            return False

    def get_balance_usdt(self):
        try:
            account = self.futures_api.list_futures_accounts(settle='usdt')
            balance = float(account.total)
            logger.debug(f"💰 Баланс: {balance:.2f} USDT")
            return balance
        except Exception as e:
            logger.error(f"❌ Ошибка получения баланса: {e}")
            return None

    def get_current_price(self, symbol, retries=3, delay=1.0):
        for attempt in range(retries):
            try:
                ticker = self.futures_api.list_futures_tickers(settle='usdt', contract=symbol)
                price = float(ticker[0].last)
                if price > 0:
                    return price
            except GateApiException as e:
                if e.label == 'CONTRACT_NOT_FOUND':
                    self._unavailable_contracts.add(symbol)
                    logger.error(f"❌ Контракт {symbol} НЕ СУЩЕСТВУЕТ на фьючерсах")
                    return None
                logger.error(f"⚠️ Ошибка получения цены {symbol}: {e}")
                if attempt < retries - 1:
                    time.sleep(delay)
            except Exception as e:
                logger.error(f"⚠️ Ошибка получения цены {symbol}: {e}")
                if attempt < retries - 1:
                    time.sleep(delay)
        return None

    def get_ohlcv(self, symbol, timeframe, limit=200):
        if symbol in self._unavailable_contracts:
            return pd.DataFrame()
        try:
            candles = self.futures_api.list_futures_candlesticks(
                settle='usdt', contract=symbol, interval=timeframe, limit=limit
            )
            data = []
            for c in candles:
                data.append({
                    'timestamp': datetime.fromtimestamp(float(c.t)),
                    'open': float(c.o),
                    'high': float(c.h),
                    'low': float(c.l),
                    'close': float(c.c),
                    'volume': float(c.v) if c.v else 0
                })
            df = pd.DataFrame(data)
            if not df.empty:
                df = df.iloc[::-1].reset_index(drop=True)
            return df
        except GateApiException as e:
            if e.label == 'CONTRACT_NOT_FOUND':
                self._unavailable_contracts.add(symbol)
            logger.error(f"❌ Ошибка получения OHLCV {symbol}: {e}")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"❌ Ошибка получения OHLCV {symbol}: {e}")
            return pd.DataFrame()

    def calculate_qty(self, symbol, position_size_usdt=None):
        try:
            if position_size_usdt is None:
                if self.order_type == 'percentage':
                    balance = self.get_balance_usdt()
                    if not balance:
                        return None
                    position_size_usdt = balance * (self.qty_percentage / 100)
                else:
                    position_size_usdt = self.fixed_volume

            price = self.get_current_price(symbol)
            if not price:
                return None

            leverage = Decimal(str(self.leverage))
            contract = self.futures_api.get_futures_contract(settle='usdt', contract=symbol)
            quanto_multiplier = Decimal(str(contract.quanto_multiplier))
            min_size = Decimal(str(getattr(contract, 'order_size_min', 1)))
            max_size = Decimal(str(getattr(contract, 'order_size_max', 1000000)))
            size_increment = Decimal(str(getattr(contract, 'order_size_increment', 1)))

            nominal_value = Decimal(str(position_size_usdt)) * leverage
            qty = nominal_value / (Decimal(str(price)) * quanto_multiplier)
            qty = qty.quantize(Decimal('0.0001'), rounding=ROUND_DOWN)

            if qty < min_size:
                logger.error(f"❌ qty {qty} меньше минимального {min_size}")
                return None
            if qty > max_size:
                qty = max_size

            qty = (qty // size_increment) * size_increment
            return float(qty)
        except Exception as e:
            logger.error(f"❌ Ошибка расчёта qty для {symbol}: {e}")
            return None

    def get_position(self, symbol, side):
        try:
            positions = self._normalize_positions(self.futures_api.list_positions(settle='usdt'))
            for pos in positions:
                if pos.contract == symbol:
                    pos_side = 'buy' if float(pos.size) > 0 else 'sell'
                    if pos_side == side and float(pos.size) != 0:
                        return pos
            return None
        except Exception as e:
            logger.error(f"Ошибка получения позиции {symbol}: {e}")
            return None

    def place_order(self, symbol, side, timescale='1h', qty=None, usdt_amount=None,
                    retries=3, delay=1.0, signal_tp=None, signal_sl=None, strategy=None,
                    notifier=None, market_regime=None, optimized_params=None):
        config = self.config or {}
        use_tp = config.get('USE_TP', True)
        use_sl = config.get('USE_SL', True)

        for attempt in range(retries):
            try:
                balance = self.get_balance_usdt()
                if not balance or balance < 10:
                    msg = f"⚠️ Недостаточный баланс ({balance:.2f} USDT) для {symbol}"
                    logger.warning(msg)
                    if notifier:
                        notifier.send(msg)
                    return None, None

                positions = self._normalize_positions(self.futures_api.list_positions(settle='usdt'))
                if positions is None:
                    return None, None

                existing_trade = None
                existing_qty = 0
                existing_entry_price = 0

                for pos in positions:
                    if pos.contract == symbol and float(pos.size) != 0:
                        existing_side = 'buy' if float(pos.size) > 0 else 'sell'

                        if side != existing_side:
                            close_qty = abs(float(pos.size))
                            close_order_size = -close_qty if existing_side == 'buy' else close_qty

                            close_order = gate_api.FuturesOrder(
                                contract=symbol, size=close_order_size,
                                price="0", tif='ioc', reduce_only=True
                            )
                            response = self.futures_api.create_futures_order(
                                settle='usdt', futures_order=close_order
                            )
                            if response is None:
                                return None, None

                            order_id = response.id
                            actual_qty = abs(float(response.size))

                            existing_trades = get_open_trades_by_symbol_and_side(symbol, existing_side)
                            if existing_trades:
                                trade = existing_trades[0]
                                trade_id = trade['trade_id']
                                entry_price = trade['average_entry_price'] or trade['price']

                                current_price = self.get_current_price(symbol)
                                if not current_price:
                                    current_price = float(response.fill_price) if response.fill_price else entry_price

                                total_profit = 0.0
                                total_fees = 0.0
                                try:
                                    closed_positions = self.futures_api.list_position_close(
                                        settle='usdt', contract=symbol
                                    )
                                    for closed_pos in closed_positions:
                                        if int(closed_pos.time) >= trade['timestamp'] and closed_pos.contract == symbol:
                                            if (closed_pos.side == 'long' and existing_side == 'buy') or \
                                               (closed_pos.side == 'short' and existing_side == 'sell'):
                                                total_profit = float(getattr(closed_pos, 'pnl', 0.0) or 0.0)
                                                total_fees = float(getattr(closed_pos, 'fee', 0.0) or 0.0)
                                                break
                                except Exception as e:
                                    logger.error(f"Ошибка получения прибыли для {symbol}: {e}")

                                update_trade_status(
                                    trade_id, "CLOSED",
                                    close_price=current_price, close_order_id=order_id,
                                    close_reason="reverse_signal", pnl=total_profit, fees=total_fees
                                )

                                profit_label = "Прибыль" if total_profit >= 0 else "Убыток"
                                margin = float(pos.margin) if pos.margin else 0
                                profit_percentage = (total_profit / margin * 100) if margin > 0.01 else 0.0

                                msg = (
                                    f"✅ Закрыта {existing_side}: {symbol}\n"
                                    f"Причина: обратный сигнал\n"
                                    f"💰 {profit_label}: {total_profit:+.2f} USDT ({profit_percentage:+.2f}%)\n"
                                    f"💳 Баланс: {balance:.2f} USDT"
                                )
                                with message_lock:
                                    msg_key = (symbol, existing_side, 'close_reverse', int(time.time() // 60))
                                    if msg_key not in sent_messages:
                                        if notifier:
                                            notifier.send(msg)
                                        sent_messages.add(msg_key)

                                last_close_time[(symbol, existing_side)] = time.time()
                                recently_closed[(symbol, existing_side)] = time.time()

                                if trade.get('strategy') == 'MR':
                                    mr_last_close_time[(symbol, existing_side)] = time.time()
                                elif trade.get('strategy') == 'AS':
                                    as_last_close_time[(symbol, existing_side)] = time.time()

                                time.sleep(5)

                        elif side == existing_side:
                            existing_qty = abs(float(pos.size))
                            existing_entry_price = float(pos.entry_price)
                            existing_trades = get_open_trades_by_symbol_and_side(symbol, side)
                            existing_trade = existing_trades[0] if existing_trades else None

                            if not existing_trade:
                                price = self.get_current_price(symbol)
                                if not price:
                                    return None, None
                                tp_cfg = get_tp_config(timescale)
                                stop_price = price * (
                                    1 - tp_cfg['stop_loss_percentage'] / 100 if side == 'buy'
                                    else 1 + tp_cfg['stop_loss_percentage'] / 100
                                )
                                margin = float(pos.margin) if pos.margin else 0
                                balance = self.get_balance_usdt()

                                trade_id = add_trade(
                                    symbol, side, price, existing_qty, int(time.time()), "OPEN",
                                    timescale, current_stop_price=stop_price,
                                    average_entry_price=existing_entry_price,
                                    highest_price=price if side == 'buy' else None,
                                    lowest_price=price if side == 'sell' else None,
                                    original_stop_price=stop_price,
                                    trailing_stop_price=stop_price,
                                    margin=margin, balance_at_open=balance,
                                    open_time=int(time.time()), strategy=strategy,
                                    market_regime=market_regime,
                                    optimized_params=json.dumps(optimized_params) if optimized_params else None
                                )
                                existing_trade = {'trade_id': trade_id, 'timestamp': int(time.time()),
                                                   'amount': existing_qty}

                                self.trailing_stop_manager.start_monitoring(symbol, side, notifier)

                daily_limit = config.get('DAILY_LOSS_LIMIT', 3)
                if check_daily_loss_limit(daily_limit):
                    msg = f"⚠️ Достигнут дневной лимит убытков для {symbol} ({side})"
                    logger.warning(msg)
                    if notifier:
                        notifier.send(msg)
                    return None, None

                if strategy == 'MR':
                    max_trades = config.get('MR_MAX_POSITIONS', 2)
                    if check_max_open_trades_by_strategy('MR', max_trades) and not existing_trade:
                        msg = f"⚠️ Лимит MR позиций достигнут ({max_trades}) для {symbol} ({side})"
                        logger.warning(msg)
                        if notifier:
                            notifier.send(msg)
                        return None, None
                elif strategy == 'AS':
                    max_trades = config.get('AS_MAX_POSITIONS', 3)
                    if check_max_open_trades_by_strategy('AS', max_trades) and not existing_trade:
                        msg = f"⚠️ Лимит AS позиций достигнут ({max_trades}) для {symbol} ({side})"
                        logger.warning(msg)
                        if notifier:
                            notifier.send(msg)
                        return None, None

                close_key = (symbol, side)
                if close_key in last_close_time:
                    elapsed = time.time() - last_close_time[close_key]
                    if elapsed < 10:
                        logger.warning(f"Позиция {symbol} ({side}) закрыта менее 10 сек назад, ждём")
                        time.sleep(10 - elapsed)

                if existing_trade:
                    last_trade_time = existing_trade['timestamp']
                    time_diff = int(time.time()) - last_trade_time
                    averaging_pause = 300

                    if time_diff < averaging_pause:
                        logger.info(f"Пауза между усреднениями для {symbol} не истекла")
                        return None, None

                price = self.get_current_price(symbol)
                if not price:
                    return None, None

                if qty is None and usdt_amount is None:
                    qty = self.calculate_qty(symbol)
                    if not qty:
                        return None, None
                elif usdt_amount:
                    qty = usdt_amount / price
                    qty = float(Decimal(str(qty)).quantize(Decimal('0.0001'), rounding=ROUND_DOWN))
                    if qty <= 0:
                        return None, None

                contract = self.futures_api.get_futures_contract(settle='usdt', contract=symbol)
                max_size = Decimal(str(getattr(contract, 'order_size_max', 1000000)))
                min_size = Decimal(str(getattr(contract, 'order_size_min', 1)))
                size_increment = Decimal(str(getattr(contract, 'order_size_increment', 1)))

                qty = Decimal(str(qty)).quantize(Decimal('0.0001'), rounding=ROUND_DOWN)
                qty = (qty // size_increment) * size_increment
                if qty < min_size or qty > max_size:
                    logger.error(f"qty {qty} для {symbol} вне диапазона [{min_size}, {max_size}]")
                    return None, None

                if side == 'buy':
                    order_size = int(qty)
                else:
                    order_size = -int(qty)

                order = gate_api.FuturesOrder(
                    contract=symbol, size=order_size,
                    price="0", tif='ioc', reduce_only=False
                )
                response = self.futures_api.create_futures_order(settle='usdt', futures_order=order)
                order_id = response.id
                actual_qty = abs(float(response.size))

                order_status = self.futures_api.get_futures_order(settle='usdt', order_id=order_id)
                if order_status.status not in ['filled', 'finished'] or float(order_status.size) == 0:
                    logger.error(f"Ордер {order_id} для {symbol} не выполнен, статус: {order_status.status}")
                    if attempt < retries - 1:
                        time.sleep(delay)
                        continue
                    return None, None

                positions = self.futures_api.list_positions(settle='usdt')
                margin = 0
                for pos in positions:
                    if pos.contract == symbol and (
                        (float(pos.size) > 0 and side == 'buy') or
                        (float(pos.size) < 0 and side == 'sell')
                    ):
                        margin = float(pos.margin)
                        break
                balance = self.get_balance_usdt()

                tp_cfg = get_tp_config(timescale)
                stop_price = price * (
                    1 - tp_cfg['stop_loss_percentage'] / 100 if side == 'buy'
                    else 1 + tp_cfg['stop_loss_percentage'] / 100
                )

                signal_id = hashlib.md5(
                    f"{side}_{symbol}_{timescale}_{int(time.time() // 60)}".encode()
                ).hexdigest()

                if existing_trade:
                    total_qty = existing_trade['amount'] + actual_qty
                    new_avg_price = (
                        (existing_entry_price * existing_trade['amount']) + (price * actual_qty)
                    ) / total_qty
                    stop_price = new_avg_price * (
                        1 - tp_cfg['stop_loss_percentage'] / 100 if side == 'buy'
                        else 1 + tp_cfg['stop_loss_percentage'] / 100
                    )

                    update_trade_status(
                        existing_trade['trade_id'], "OPEN",
                        current_stop_price=stop_price,
                        average_entry_price=new_avg_price,
                        highest_price=price if side == 'buy' else None,
                        lowest_price=price if side == 'sell' else None,
                        original_stop_price=stop_price,
                        trailing_stop_price=stop_price
                    )
                    with get_db_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute('''
                            UPDATE trades SET amount = amount + ?, timestamp = ?
                            WHERE trade_id = ?
                        ''', (actual_qty, int(time.time()), existing_trade['trade_id']))
                        conn.commit()

                    msg = (
                        f"🔄 Усреднена {side}: {symbol} ({timescale})\n"
                        f"Маржа: {margin:.2f} USDT\n"
                        f"Новая средняя цена: {new_avg_price:.4f}\n"
                        f"Стоп: {stop_price:.4f}\n"
                        f"Общий объем: {total_qty:.4f}\n"
                        f"Баланс: {balance:.2f} USDT"
                    )
                    if notifier:
                        notifier.send(msg)
                else:
                    trade_id = add_trade(
                        symbol, side, price, actual_qty, int(time.time()), "OPEN", timescale,
                        current_stop_price=stop_price, open_order_id=order_id,
                        average_entry_price=price,
                        highest_price=price if side == 'buy' else None,
                        lowest_price=price if side == 'sell' else None,
                        original_stop_price=stop_price,
                        trailing_stop_price=stop_price,
                        margin=margin, balance_at_open=balance,
                        signal_id=signal_id, open_time=int(time.time()),
                        signal_tp_price=(signal_tp if (use_tp and signal_tp is not None) else None),
                        signal_sl_price=(signal_sl if (use_sl and signal_sl is not None) else None),
                        strategy=strategy,
                        market_regime=market_regime,
                        optimized_params=json.dumps(optimized_params) if optimized_params else None
                    )

                    msg = (
                        f"✅ Открыта {side}: {symbol} ({timescale})\n"
                        f"Маржа: {margin:.2f} USDT\n"
                        f"Цена: {price:.4f}\n"
                        f"Стоп: {stop_price:.4f}\n"
                        f"Объем: {actual_qty:.4f}\n"
                        f"Баланс: {balance:.2f} USDT"
                    )
                    if notifier:
                        notifier.send(msg)

                self.trailing_stop_manager.start_monitoring(symbol, side, notifier)

                return order_id, actual_qty

            except GateApiException as ex:
                logger.error(f"Ошибка размещения ордера (попытка {attempt + 1}): {ex.label}, {ex.message}")
                if attempt >= retries - 1:
                    return None, None
                time.sleep(delay)
            except Exception as e:
                logger.error(f"Ошибка размещения ордера (попытка {attempt + 1}): {e}")
                if attempt >= retries - 1:
                    return None, None
                time.sleep(delay)

        return None, None

    def close_position_enhanced(self, symbol, side, qty, partial_qty=None,
                                 reason="manual", max_retries=3, notifier=None):
        for attempt in range(max_retries):
            try:
                logger.info(f"🔄 [{reason.upper()}] Попытка {attempt + 1}/{max_retries} закрытия {symbol} ({side})")

                positions = self._normalize_positions(self.futures_api.list_positions(settle='usdt'))
                position_size = 0
                entry_price = 0
                current_pnl = 0

                for pos in positions:
                    if pos.contract == symbol and (
                        (float(pos.size) > 0 and side == 'buy') or
                        (float(pos.size) < 0 and side == 'sell')
                    ):
                        position_size = abs(float(pos.size))
                        entry_price = float(pos.entry_price)
                        current_pnl = float(pos.unrealised_pnl)
                        break

                if position_size == 0:
                    logger.info(f"✅ Позиция {symbol} ({side}) уже закрыта")
                    return None, None

                contract = self.futures_api.get_futures_contract(settle='usdt', contract=symbol)
                quanto_multiplier = Decimal(str(contract.quanto_multiplier))
                min_size = Decimal(str(getattr(contract, 'order_size_min', 1)))
                max_size = Decimal(str(getattr(contract, 'order_size_max', 1000000)))
                size_increment = Decimal(str(getattr(contract, 'order_size_increment', 1)))

                if partial_qty is not None:
                    qty_to_close = Decimal(str(partial_qty))
                else:
                    qty_to_close = Decimal(str(position_size)) * quanto_multiplier

                qty_in_coins = Decimal(str(qty_to_close))
                qty_in_contracts = qty_in_coins / quanto_multiplier

                if qty_in_contracts < min_size or qty_in_contracts > max_size:
                    logger.error(f"❌ qty вне диапазона")
                    return None, None

                qty_in_contracts = (qty_in_contracts // size_increment) * size_increment
                qty_in_contracts = qty_in_contracts.quantize(Decimal('1'), rounding=ROUND_DOWN)
                if qty_in_contracts <= 0:
                    return None, None

                if side == 'buy':
                    order_size = -int(qty_in_contracts)
                else:
                    order_size = int(qty_in_contracts)

                order = gate_api.FuturesOrder(
                    contract=symbol, size=order_size,
                    price="0", tif='ioc', reduce_only=True
                )

                response = self.futures_api.create_futures_order(settle='usdt', futures_order=order)
                order_id = response.id
                actual_qty = Decimal(str(abs(float(response.size)))) * quanto_multiplier

                order_status = None
                for status_attempt in range(5):
                    try:
                        order_status = self.futures_api.get_futures_order(settle='usdt', order_id=order_id)
                        if order_status.status in ['filled', 'finished'] and float(order_status.size) != 0:
                            break
                        elif order_status.status in ['cancelled', 'expired']:
                            break
                        time.sleep(0.5)
                    except Exception:
                        if status_attempt < 4:
                            time.sleep(1)

                if order_status and order_status.status in ['filled', 'finished'] and float(order_status.size) != 0:
                    time.sleep(2)
                    positions_after = self._normalize_positions(self.futures_api.list_positions(settle='usdt'))
                    position_still_open = False
                    remaining_size = 0

                    for pos in positions_after:
                        if pos.contract == symbol and (
                            (float(pos.size) > 0 and side == 'buy') or
                            (float(pos.size) < 0 and side == 'sell')
                        ):
                            remaining_size = abs(float(pos.size))
                            if remaining_size > 0.001:
                                position_still_open = True
                                break

                    if not position_still_open:
                        logger.info(f"✅ Позиция {symbol} ({side}) успешно закрыта полностью")
                        last_close_time[(symbol, side)] = time.time()
                        recently_closed[(symbol, side)] = time.time()
                        time.sleep(5)
                        return order_id, float(actual_qty)
                    else:
                        logger.info(f"🔁 Закрываем остаток {symbol} ({side}), осталось: {remaining_size}")
                        remaining_qty_in_coins = Decimal(str(remaining_size)) * quanto_multiplier
                        remaining_order_id, remaining_actual_qty = self.close_position_enhanced(
                            symbol, side, qty=float(remaining_qty_in_coins),
                            partial_qty=float(remaining_qty_in_coins),
                            reason=f"{reason}_remainder", max_retries=2, notifier=notifier
                        )
                        if remaining_order_id:
                            return order_id, float(actual_qty) + (float(remaining_actual_qty) if remaining_actual_qty else 0)
                        return order_id, float(actual_qty)
                else:
                    if attempt < max_retries - 1:
                        time.sleep(3)
                        continue
                    return None, None

            except Exception as e:
                logger.error(f"❌ Ошибка при попытке {attempt + 1} закрытия {symbol}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(3)
                else:
                    return None, None

        return None, None

    def is_position_open(self, symbol, side):
        try:
            positions = self._normalize_positions(self.futures_api.list_positions(settle='usdt'))
            for pos in positions:
                if hasattr(pos, 'contract') and pos.contract == symbol:
                    if (hasattr(pos, 'size') and float(pos.size) > 0 and side == 'buy') or \
                       (hasattr(pos, 'size') and float(pos.size) < 0 and side == 'sell'):
                        return float(pos.size) != 0
            return False
        except Exception as e:
            logger.error(f"Ошибка проверки позиции {symbol} ({side}): {e}")
            return True

    def sync_positions(self, notifier=None):
        try:
            positions = self._normalize_positions(self.futures_api.list_positions(settle='usdt'))
            open_trades = get_open_trades()

            # ✅ AUTO-RESTART: При первом запуске перезапускаем мониторинг для всех открытых позиций
            if not hasattr(self, '_monitoring_restarted'):
                self._monitoring_restarted = True
                for trade in open_trades:
                    symbol = trade['symbol']
                    side = trade['side']
                    self.trailing_stop_manager.start_monitoring(symbol, side, notifier)
                    logger.info(f"🔄 Перезапуск мониторинга для {symbol} ({side})")

            for trade in open_trades:
                symbol = trade['symbol']
                side = trade['side']
                trade_id = trade['trade_id']
                found = False

                for pos in positions:
                    if pos.contract == symbol and (
                        (float(pos.size) > 0 and side == 'buy') or
                        (float(pos.size) < 0 and side == 'sell')
                    ):
                        found = True
                        current_price = self.get_current_price(symbol)
                        if current_price:
                            update_trade_status(
                                trade_id, "OPEN",
                                current_stop_price=trade['current_stop_price'],
                                average_entry_price=float(pos.entry_price),
                                highest_price=max(trade['highest_price'] or current_price, current_price) if side == 'buy' else None,
                                lowest_price=min(trade['lowest_price'] or current_price, current_price) if side == 'sell' else None
                            )
                        break

                if not found:
                    with get_db_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT close_reason, status FROM trades WHERE trade_id = ?", (trade_id,))
                        row = cursor.fetchone()
                        if row and row[1] == "CLOSED" and row[0] and row[0] != "closed_on_exchange":
                            continue

                    current_price = self.get_current_price(symbol) or trade['average_entry_price'] or trade['price']

                    total_profit = 0.0
                    total_fees = 0.0
                    try:
                        closed_positions = self.futures_api.list_position_close(settle='usdt', contract=symbol)
                        for closed_pos in closed_positions:
                            if int(closed_pos.time) >= trade['timestamp'] and closed_pos.contract == symbol:
                                if (closed_pos.side == 'long' and side == 'buy') or \
                                   (closed_pos.side == 'short' and side == 'sell'):
                                    total_profit = float(getattr(closed_pos, 'pnl', 0.0) or 0.0)
                                    total_fees = float(getattr(closed_pos, 'fee', 0.0) or 0.0)
                                    break
                    except Exception as e:
                        logger.error(f"Ошибка получения прибыли для {symbol}: {e}")

                    # 🔧 FALLBACK: Если биржа вернула 0, считаем PnL вручную
                    if total_profit == 0.0:
                        entry_p = trade.get('average_entry_price') or trade.get('price', 0)
                        amount = trade.get('amount', 0)
                        if entry_p > 0 and amount > 0 and current_price > 0:
                            if side == 'buy':
                                total_profit = (current_price - entry_p) * amount
                            else:
                                total_profit = (entry_p - current_price) * amount
                            logger.info(f"🔧 Fallback PnL для {symbol}: {total_profit:.4f} USDT (API биржи вернул 0)")

                    update_trade_status(
                        trade_id, "CLOSED",
                        close_price=current_price, close_order_id=None,
                        close_reason="closed_on_exchange",
                        pnl=total_profit, fees=total_fees
                    )

                    close_key = (symbol, side)
                    if close_key in recently_closed:
                        elapsed = time.time() - recently_closed[close_key]
                        if elapsed < 120:
                            logger.info(f"⏸️ Пропуск дублирующего сообщения для {symbol} ({side})")
                            continue

                    open_time = trade.get('open_time') or trade.get('timestamp')
                    profit_label = "Прибыль" if total_profit >= 0 else "Убыток"
                    margin = float(trade.get('margin', 0) or 0)
                    profit_percentage = (total_profit / margin * 100) if margin > 0.01 else 0.0

                    msg = (
                        f"✅ Закрыта {side}: {symbol}\n"
                        f"📋 Причина: закрыто на бирже\n"
                        f"⏱️ Время жизни: {_format_duration(int(time.time()) - open_time) if open_time else 'N/A'}\n"
                        f"💰 {profit_label}: {total_profit:+.2f} USDT ({profit_percentage:+.2f}%)"
                    )
                    with message_lock:
                        msg_key = (symbol, side, 'close_exchange', int(time.time() // 60))
                        if msg_key not in sent_messages:
                            if notifier:
                                notifier.send(msg)
                            sent_messages.add(msg_key)

                    logger.info(f"Позиция {side} для {symbol} закрыта на бирже")

            for pos in positions:
                if float(pos.size) != 0:
                    symbol = pos.contract
                    side = 'buy' if float(pos.size) > 0 else 'sell'
                    existing_trades = get_open_trades_by_symbol_and_side(symbol, side)

                    if not existing_trades:
                        contract = self.futures_api.get_futures_contract(settle='usdt', contract=symbol)
                        quanto_multiplier = float(contract.quanto_multiplier)
                        amount = abs(float(pos.size)) * quanto_multiplier
                        current_price = self.get_current_price(symbol)
                        if not current_price:
                            continue

                        tp_cfg = get_tp_config('1h')
                        stop_price = current_price * (
                            1 - tp_cfg['stop_loss_percentage'] / 100 if side == 'buy'
                            else 1 + tp_cfg['stop_loss_percentage'] / 100
                        )
                        margin = float(pos.margin) if pos.margin else 0
                        balance = self.get_balance_usdt()

                        trade_id = add_trade(
                            symbol, side, float(pos.entry_price), amount,
                            int(time.time()), "OPEN", '1h',
                            current_stop_price=stop_price,
                            average_entry_price=float(pos.entry_price),
                            highest_price=current_price if side == 'buy' else None,
                            lowest_price=current_price if side == 'sell' else None,
                            margin=margin, signal_id=None, open_time=int(time.time())
                        )

                        msg = (
                            f"Обнаружена новая позиция {side} для {symbol} на бирже\n"
                            f"💰 Маржа: {margin:.2f} USDT\n"
                            f"📊 Цена: {current_price:.4f}\n"
                            f"Стоп: {stop_price:.4f}\n"
                            f"📦 Объем: {amount:.4f}"
                        )
                        if notifier:
                            notifier.send(msg)

                        self.trailing_stop_manager.start_monitoring(symbol, side, notifier)

        except Exception as e:
            logger.error(f"Ошибка синхронизации позиций: {e}")

# ==================== TRAILING STOP MANAGER ====================
class TrailingStopManager:
    def __init__(self, gate_io_instance):
        self.gate_io = gate_io_instance
        self.trailing_threads = {}
        self.smart_trailing_stops = {}

    def start_monitoring(self, symbol, side, notifier=None):
        thread_key = (symbol, side)
        if thread_key in self.trailing_threads and self.trailing_threads[thread_key].is_alive():
            return

        thread = Thread(
            target=self._monitor_position,
            args=(symbol, side, notifier),
            daemon=True
        )
        thread.start()
        self.trailing_threads[thread_key] = thread
        logger.info(f"🎯 Запущен мониторинг трейлинг-стопа для {symbol} ({side})")

    def stop_monitoring(self, symbol, side):
        thread_key = (symbol, side)
        if thread_key in self.trailing_threads:
            del self.trailing_threads[thread_key]
        if thread_key in self.smart_trailing_stops:
            del self.smart_trailing_stops[thread_key]

    def _is_position_open(self, symbol, side):
        return self.gate_io.is_position_open(symbol, side)

    def _get_position_pnl(self, symbol, side):
        try:
            positions = self.gate_io._normalize_positions(self.gate_io.futures_api.list_positions(settle='usdt'))
            for pos in positions:
                if pos.contract == symbol and (
                    (float(pos.size) > 0 and side == 'buy') or
                    (float(pos.size) < 0 and side == 'sell')
                ):
                    current_pnl = float(pos.unrealised_pnl)
                    margin = float(pos.margin)

                    entry_price = float(getattr(pos, 'entry_price', 0))
                    current_price = self.gate_io.get_current_price(symbol)
                    contract = self.gate_io.futures_api.get_futures_contract(settle='usdt', contract=symbol)
                    quanto_multiplier = float(contract.quanto_multiplier)
                    amount = float(pos.size) * quanto_multiplier
                    side_calc = 'buy' if float(pos.size) > 0 else 'sell'

                    if current_price and entry_price and amount:
                        manual_pnl = (current_price - entry_price) * amount if side_calc == 'buy' \
                                     else (entry_price - current_price) * amount
                        if abs(current_pnl) < 0.001 and abs(manual_pnl) > 0.001:
                            current_pnl = manual_pnl

                    leverage = float(self.gate_io.leverage)
                    if margin > 0.01:
                        pnl_percentage = (current_pnl / margin * 100)
                        calc_method = "(API-margin)"
                    elif hasattr(pos, 'size') and hasattr(pos, 'entry_price'):
                        try:
                            size = abs(float(pos.size))
                            entry_price_calc = float(pos.entry_price)
                            amount = size * quanto_multiplier
                            calculated_margin = (entry_price_calc * amount) / leverage
                            if calculated_margin > 0.01:
                                pnl_percentage = (current_pnl / calculated_margin * 100)
                                calc_method = "(calculated-margin)"
                            else:
                                pnl_percentage = 0.0
                                calc_method = "(N/A)"
                        except Exception:
                            pnl_percentage = 0.0
                            calc_method = "(error)"
                    else:
                        pnl_percentage = 0.0
                        calc_method = "(N/A)"

                    return current_pnl, pnl_percentage, margin, calc_method

            return 0.0, 0.0, 0.0, "(N/A)"
        except Exception as e:
            logger.error(f"❌ Ошибка получения PnL: {e}")
            return 0.0, 0.0, 0.0, "(error)"

    def _monitor_position(self, symbol, side, notifier=None):
        try:
            trades = get_open_trades_by_symbol_and_side(symbol, side)
            if not trades:
                return

            trade = trades[0]
            timescale = trade.get('timescale', '1h')
            tp_config = get_tp_config(timescale)

            signal_sl_price = trade.get('signal_sl_price')
            signal_tp_price = trade.get('signal_tp_price')

            config = self.gate_io.config or {}
            use_sl = config.get('USE_SL', True)
            use_tp = config.get('USE_TP', True)
            tp_close_percent = config.get('TP_CLOSE_PERCENT', 100)

            thread_key = (symbol, side)
            entry_price = trade.get('average_entry_price') or trade.get('price')
            open_time = trade.get('open_time') or trade.get('timestamp')

            if thread_key not in self.smart_trailing_stops:
                smart_ts = SmartTrailingStop(config)
                atr = None
                try:
                    df = self.gate_io.get_ohlcv(symbol, timescale, limit=50)
                    if not df.empty and 'atr' in df.columns:
                        atr = float(df['atr'].iloc[-1])
                except Exception:
                    pass
                smart_ts.start(entry_price, open_time, side, tp_config['stop_loss_percentage'], atr)
                self.smart_trailing_stops[thread_key] = smart_ts

            logger.info(f"START MONITORING {symbol} ({side}) — price-based trailing only")

            while self._is_position_open(symbol, side):
                current_price = self.gate_io.get_current_price(symbol)
                if not current_price:
                    time.sleep(self.gate_io.trailing_interval)
                    continue

                position_age = time.time() - (trade.get('open_time') or trade.get('timestamp'))
                if position_age < 30:
                    time.sleep(self.gate_io.trailing_interval)
                    continue

                using_signal_sl = use_sl and signal_sl_price is not None
                if using_signal_sl:
                    sl_hit = (side == 'buy' and current_price <= signal_sl_price) or \
                             (side == 'sell' and current_price >= signal_sl_price)
                    if sl_hit:
                        logger.info(f"🛑 SL из сигнала сработал для {symbol} ({side})")
                        self._execute_stop_loss(symbol, side, current_price, notifier)
                        break

                if use_tp and signal_tp_price:
                    tp_hit = (side == 'buy' and current_price >= signal_tp_price) or \
                             (side == 'sell' and current_price <= signal_tp_price)
                    if tp_hit:
                        logger.info(f"🎯 TP из сигнала сработал для {symbol} ({side})")
                        fresh_trades = get_open_trades_by_symbol_and_side(symbol, side)
                        if fresh_trades:
                            trade = fresh_trades[0]
                        self._execute_take_profit(symbol, side, current_price, trade, tp_close_percent, notifier)
                        break

                smart_ts = self.smart_trailing_stops.get(thread_key)
                if smart_ts:
                    atr = None
                    try:
                        df = self.gate_io.get_ohlcv(symbol, timescale, limit=50)
                        if not df.empty and 'atr' in df.columns:
                            atr = float(df['atr'].iloc[-1])
                    except Exception:
                        pass

                    new_stop, triggered, trigger_type = smart_ts.update(current_price, atr)
                    if triggered:
                        # ✅ Проверяем режим закрытия
                        close_mode = config.get('TRAILING_CLOSE_MODE', 'trailing')
                        close_percent = config.get('TRAILING_CLOSE_PERCENT', 100)

                        if close_mode == 'tp':
                            # Закрываем позицию полностью или частично
                            logger.info(f"🎯 TP режим: закрываем {close_percent}% позиции {symbol} ({side})")
                            self._execute_take_profit(symbol, side, current_price, trade, close_percent, notifier)
                        else:
                            # Используем трейлинг-стоп
                            if trigger_type == 'trailing_stop':
                                logger.info(f"🛑 Smart Trailing Stop сработал для {symbol} ({side})")
                                self._execute_trailing_stop(symbol, side, current_price, notifier)
                            else:
                                logger.info(f"🛑 Initial Stop Loss сработал для {symbol} ({side})")
                                self._execute_stop_loss(symbol, side, current_price, notifier)
                        break

                    if new_stop != trade.get('current_stop_price'):
                        update_trade_status(
                            trade['trade_id'], "OPEN",
                            current_stop_price=new_stop,
                            trailing_stop_price=new_stop
                        )

                time.sleep(self.gate_io.trailing_interval)

            logger.info(f"🏁 Мониторинг завершён для {symbol} ({side})")
            if thread_key in self.smart_trailing_stops:
                del self.smart_trailing_stops[thread_key]

        except Exception as e:
            logger.error(f"❌ Ошибка в мониторинге {symbol} ({side}): {e}")

    def _execute_take_profit(self, symbol, side, current_price, trade, tp_close_percent, notifier=None):
        try:
            positions = self.gate_io._normalize_positions(self.gate_io.futures_api.list_positions(settle='usdt'))
            position_size = 0
            for pos in positions:
                if pos.contract == symbol and (
                    (float(pos.size) > 0 and side == 'buy') or
                    (float(pos.size) < 0 and side == 'sell')
                ):
                    position_size = abs(float(pos.size))
                    break
            if position_size == 0:
                return

            contract = self.gate_io.futures_api.get_futures_contract(settle='usdt', contract=symbol)
            quanto_multiplier = float(contract.quanto_multiplier)
            close_fraction = tp_close_percent / 100.0
            qty_to_close = position_size * quanto_multiplier * close_fraction
            is_partial = tp_close_percent < 100.0
            reason = 'take_profit_partial' if is_partial else 'take_profit'

            order_id, actual_qty = self.gate_io.close_position_enhanced(
                symbol, side, qty_to_close, reason=reason, notifier=notifier
            )

            if order_id:
                if is_partial:
                    update_trade_status(trade['trade_id'], 'OPEN', signal_tp_price=None)
                    if notifier:
                        notifier.send(f"Частичный TP ({tp_close_percent:.0f}%): {symbol} ({side})")
                else:
                    self._close_position(symbol, side, current_price, reason, trade_id=trade['trade_id'], notifier=notifier)
        except Exception as e:
            logger.error(f"Ошибка _execute_take_profit: {e}")

    def _execute_stop_loss(self, symbol, side, current_price, notifier=None):
        trades = get_open_trades_by_symbol_and_side(symbol, side)
        trade_id = trades[0]['trade_id'] if trades else None
        self._close_position(symbol, side, current_price, "stop_loss", trade_id, notifier)

    def _execute_trailing_stop(self, symbol, side, current_price, notifier=None):
        trades = get_open_trades_by_symbol_and_side(symbol, side)
        trade_id = trades[0]['trade_id'] if trades else None
        self._close_position(symbol, side, current_price, "trailing_stop", trade_id, notifier)

    def _close_position(self, symbol, side, current_price, reason, trade_id=None, notifier=None):
        try:
            positions = self.gate_io._normalize_positions(self.gate_io.futures_api.list_positions(settle='usdt'))
            position_size = 0
            entry_price = 0

            for pos in positions:
                if pos.contract == symbol and (
                    (float(pos.size) > 0 and side == 'buy') or
                    (float(pos.size) < 0 and side == 'sell')
                ):
                    position_size = abs(float(pos.size))
                    entry_price = float(pos.entry_price)
                    break

            if position_size == 0:
                return

            contract = self.gate_io.futures_api.get_futures_contract(settle='usdt', contract=symbol)
            quanto_multiplier = float(contract.quanto_multiplier)
            qty = position_size * quanto_multiplier

            order_id, actual_qty = self.gate_io.close_position_enhanced(
                symbol, side, qty, reason=reason, notifier=notifier
            )

            if order_id and actual_qty:
                trade = None
                if trade_id:
                    trade = get_trade_by_id(trade_id)
                else:
                    trades = get_open_trades_by_symbol_and_side(symbol, side)
                    if trades:
                        trade = trades[0]

                if trade:
                    total_profit = 0.0
                    try:
                        closed_positions = self.gate_io.futures_api.list_position_close(settle='usdt', contract=symbol)
                        for closed_pos in closed_positions:
                            if int(closed_pos.time) >= trade['timestamp'] and closed_pos.contract == symbol:
                                if (closed_pos.side == 'long' and side == 'buy') or \
                                   (closed_pos.side == 'short' and side == 'sell'):
                                    total_profit = float(getattr(closed_pos, 'pnl', 0.0) or 0.0)
                                    break
                    except Exception as e:
                        logger.error(f"Ошибка получения прибыли: {e}")

                    # 🔧 FALLBACK: Если биржа вернула 0, считаем PnL вручную
                    if total_profit == 0.0:
                        entry_p = trade.get('average_entry_price') or trade.get('price', 0)
                        amount = trade.get('amount', 0)
                        if entry_p > 0 and amount > 0 and current_price > 0:
                            if side == 'buy':
                                total_profit = (current_price - entry_p) * amount
                            else:
                                total_profit = (entry_p - current_price) * amount
                            logger.info(f"🔧 Fallback PnL для {symbol}: {total_profit:.4f} USDT (API биржи вернул 0)")

                    update_trade_status(
                        trade['trade_id'], "CLOSED",
                        close_price=current_price,
                        close_order_id=order_id,
                        close_reason=reason,
                        pnl=total_profit, fees=0.0
                    )

                    open_time = trade.get('open_time') or trade.get('timestamp')
                    trailing_start = trade.get('trailing_start_time')
                    profit_label = "Прибыль" if total_profit >= 0 else "Убыток"
                    margin = float(trade.get('margin', 0) or 0)
                    profit_percentage = (total_profit / margin * 100) if margin > 0.01 else 0.0

                    reason_text = {
                        "stop_loss": "стоп-лосс",
                        "trailing_stop": "трейлинг-стоп",
                        "take_profit": "тейк-профит",
                        "take_profit_partial": "тейк-профит (частичный)",
                        "manual": "вручную",
                        "reverse_signal": "обратный сигнал",
                        "closed_on_exchange": "закрыто на бирже"
                    }.get(reason, reason)

                    duration_lines = []
                    if open_time:
                        duration_lines.append(f"⏱️ Общее время: {_format_duration(int(time.time()) - open_time)}")
                    if trailing_start:
                        duration_lines.append(f"⏱️ Время трейлинга: {_format_duration(int(time.time()) - trailing_start)}")
                    duration_text = "\n".join(duration_lines) + "\n" if duration_lines else ""

                    balance = self.gate_io.get_balance_usdt() or 0.0
                    balance_percentage = (total_profit / balance * 100) if balance > 0 else 0.0

                    msg = (
                        f"✅ Закрыта {side}: {symbol}\n"
                        f"📋 Причина: {reason_text}\n"
                        f"{duration_text}"
                        f"💰 {profit_label}: {total_profit:+.2f} USDT ({profit_percentage:+.2f}%, {balance_percentage:+.2f}% от баланса)\n"
                        f"💳 Баланс: {balance:.2f} USDT"
                    )
                    with message_lock:
                        msg_key = (symbol, side, f'close_{reason}', int(time.time() // 60))
                        if msg_key not in sent_messages:
                            if notifier:
                                notifier.send(msg)
                            sent_messages.add(msg_key)

                    logger.info(f"Позиция {symbol} ({side}) закрыта: {reason}")

        except Exception as e:
            logger.error(f"Ошибка закрытия позиции {symbol} ({side}): {e}")

# ==================== ГЛАВНЫЙ БОТ ====================
class SynergyBot:
    def __init__(self, log_fn, status_fn):
        self.log = log_fn
        self.status = status_fn
        self.config = load_config()
        self.notifier = TelegramNotifier(self.config['TELEGRAM_TOKEN'], self.config['TELEGRAM_CHAT_ID'])
        self.gate = None
        self.mr_strategy = None
        self.as_strategies = {}
        self.is_running = False
        self.stop_event = threading.Event()
        self.stats = {
            'signals_generated': 0,
            'trades_opened': 0,
            'trades_closed': 0,
            'total_pnl': 0.0,
            'mr_signals': 0,
            'as_signals': 0,
        }

        self._init_strategies()
        self._init_gate()

    def _init_gate(self):
        if self.config['GATEIO_API_KEY'] and self.config['GATEIO_API_SECRET']:
            try:
                self.gate = GateIO(
                    api_key=self.config['GATEIO_API_KEY'],
                    api_secret=self.config['GATEIO_API_SECRET'],
                    account_type=self.config['ACCOUNT_TYPE'],
                    leverage=self.config['LEVERAGE'],
                    margin_mode=self.config['MARGIN_MODE'],
                    order_type=self.config['ORDER_TYPE'],
                    qty_percentage=self.config['QTY_PERCENTAGE'],
                    fixed_volume=self.config['FIXED_VOLUME'],
                    trailing_interval=self.config['TRAILING_INTERVAL'],
                    config=self.config
                )
                valid, msg = self.gate.check_permissions()
                if valid:
                    account_type_text = "REAL" if self.config['ACCOUNT_TYPE'] == 'real' else "DEMO"
                    self.log(f"✅ Gate.io инициализирован ({account_type_text}) — {msg}")

                    conn_valid, conn_msg = self.gate.test_connection()
                    if conn_valid:
                        self.log(f"✅ {conn_msg}")
                    else:
                        self.log(f"⚠️ {conn_msg}")

                    self._validate_symbols()
                else:
                    self.log(f"⚠️ Gate.io API: {msg}")
            except Exception as e:
                self.log(f"❌ Ошибка инициализации Gate.io: {e}")
        else:
            self.log("⚠️ Gate.io API ключи не настроены")

    def _validate_symbols(self):
        all_symbols = self.config['MR_SYMBOLS'] + self.config['AS_SYMBOLS']
        valid_symbols = []
        invalid_symbols = []

        for symbol in all_symbols:
            if self.gate.validate_symbol(symbol):
                valid_symbols.append(symbol)
            else:
                invalid_symbols.append(symbol)
                logger.warning(f"⚠️ Символ {symbol} не найден на фьючерсах Gate.io")

        if invalid_symbols:
            self.log(f"⚠️ Невалидные символы: {', '.join(invalid_symbols)}")
        if valid_symbols:
            self.log(f"✅ Валидные символы: {', '.join(valid_symbols)}")

    def _init_strategies(self):
        if self.config['STRATEGY_MEAN_REVERSION']:
            self.mr_strategy = MeanReversionStrategy(self.config)
            self.log("✅ Стратегия Mean Reversion включена")
        if self.config['STRATEGY_ADAPTIVE_SCALPING']:
            self.as_strategies = {}
            self.log("✅ Стратегия Adaptive Scalping включена (ленивая инициализация по парам)")

    def _get_or_create_as_strategy(self, symbol: str, tf: str) -> AdaptiveScalpingStrategy:
        key = (symbol, tf)
        if key not in self.as_strategies:
            strategy_key_label = f"{symbol}_{tf}"
            self.as_strategies[key] = AdaptiveScalpingStrategy(self.config, symbol_tf_key=strategy_key_label)
            self.log(f"🆕 Инициализирована адаптивная стратегия для {symbol} ({tf})")
        return self.as_strategies[key]

    def start(self):
        if self.is_running:
            self.log("⚠️ Бот уже запущен")
            return

        self.is_running = True
        self.stop_event.clear()

        # ✅ AUTO-RESTART: Сброс состояния при запуске
        reset_monitoring_state()

        mode = self.config['TRADING_MODE']
        account_type = "REAL" if self.config['ACCOUNT_TYPE'] == 'real' else "DEMO"

        self.log(f"Запуск skalpMat в режиме: {mode}")
        self.log(f"💼 Аккаунт: {account_type}")
        self.log(f"📊 Leverage: {self.config['LEVERAGE']}x")

        self.notifier.send(
            f"🚀 skalpMat запущен\n"
            f"📋 Режим: {mode}\n"
            f"💼 Аккаунт: {account_type}\n"
            f"📊 Leverage: {self.config['LEVERAGE']}x"
        )

        if self.gate:
            Thread(target=self._sync_loop, daemon=True).start()
        Thread(target=self._main_loop, daemon=True).start()

    def _sync_loop(self):
        while not self.stop_event.is_set():
            try:
                if self.gate:
                    self.gate.sync_positions(self.notifier)
                time.sleep(5)
            except Exception as e:
                logger.error(f"❌ Ошибка синхронизации: {e}")
                time.sleep(10)

    def stop(self):
        self.log("⏳ Остановка бота...")
        self.stop_event.set()
        self.is_running = False
        self.notifier.send("🛑 skalpMat остановлен")

    def _main_loop(self):
        scan_interval = self.config['SCAN_INTERVAL']
        last_cleanup = 0

        symbols_to_scan = []
        if self.mr_strategy and len(self.config['MR_SYMBOLS']) >= 2:
            symbols_to_scan.append((self.config['MR_SYMBOLS'][0], self.config['MR_SYMBOLS'][1], 'MR'))
        for symbol in self.config['AS_SYMBOLS']:
            symbols_to_scan.append((symbol, None, 'AS'))

        while not self.stop_event.is_set():
            try:
                now = time.time()

                if now - last_cleanup > 3600:
                    old_keys = [k for k, v in last_signal_candle.items() if now - v > 86400]
                    for key in old_keys:
                        del last_signal_candle[key]
                    if old_keys:
                        logger.info(f"🧹 Очищено {len(old_keys)} старых записей сигналов")
                    last_cleanup = now

                for symbol_a, symbol_b, strategy_type in symbols_to_scan:
                    if self.stop_event.is_set():
                        break

                    if strategy_type == 'MR':
                        timeframes = self.config['MR_TIMEFRAMES']
                        symbol_display = f"{symbol_a}/{symbol_b}"
                    else:
                        timeframes = self.config['AS_TIMEFRAMES']
                        symbol_display = symbol_a

                    for tf in timeframes:
                        if self.stop_event.is_set():
                            break
                        self.status(f"🔍 {symbol_display} ({tf})")
                        if strategy_type == 'MR':
                            self._scan_mean_reversion_pair(symbol_a, symbol_b, tf)
                        else:
                            self._scan_adaptive_scalping_symbol(symbol_a, tf)
                        time.sleep(0.5)

                for i in range(scan_interval * 2):
                    if self.stop_event.is_set():
                        break
                    self.status(f"⏱️ Следующий скан через {scan_interval - i // 2}с")
                    time.sleep(0.5)

            except Exception as e:
                self.log(f"❌ Ошибка в главном цикле: {e}")
                time.sleep(5)

        self.log("🏁 Бот остановлен")
        self.status("🛑 Бот остановлен")

    def _scan_mean_reversion_pair(self, symbol_a, symbol_b, tf):
        if not self.mr_strategy or not self.gate:
            return
        try:
            df_a = self.gate.get_ohlcv(symbol_a, tf, limit=200)
            df_b = self.gate.get_ohlcv(symbol_b, tf, limit=200)
            if df_a.empty or df_b.empty:
                return

            current_candle_time = int(df_a.iloc[-1]['timestamp'].timestamp())

            result = self.mr_strategy.analyze_pair(df_a, df_b, symbol_a, symbol_b)
            if result and result['signal']:
                signal = result['signal']

                if signal in ['BUY_SPREAD', 'SELL_SPREAD']:
                    side = 'buy' if signal == 'BUY_SPREAD' else 'sell'
                    candle_key = (symbol_a, side, tf)

                    if candle_key in last_signal_candle:
                        if last_signal_candle[candle_key] == current_candle_time:
                            logger.info(f"⏸️ MR сигнал {signal} пропущен: уже был на этой свече")
                            return

                    last_signal_candle[candle_key] = current_candle_time

                self.stats['mr_signals'] += 1
                self._handle_mr_signal(result, symbol_a, symbol_b, tf)
        except Exception as e:
            self.log(f"⚠️ Ошибка MR {symbol_a}/{symbol_b} ({tf}): {e}")

    def _scan_adaptive_scalping_symbol(self, symbol, tf):
        if not self.gate:
            return
        if not self.config['STRATEGY_ADAPTIVE_SCALPING']:
            return

        try:
            as_strategy = self._get_or_create_as_strategy(symbol, tf)

            df = self.gate.get_ohlcv(symbol, tf, limit=200)
            if df.empty:
                return

            current_candle_time = int(df.iloc[-1]['timestamp'].timestamp())

            as_strategy.update_regime(df)
            as_strategy.maybe_optimize(df)
            as_strategy.check_performance_limits()

            result = as_strategy.analyze(df, symbol)
            if result and result.get('signal'):
                signal = result['signal']

                if signal in ['BUY', 'SELL']:
                    side = 'buy' if signal == 'BUY' else 'sell'
                    candle_key = (symbol, side, tf)

                    # ✅ ANTI-SPAM: Проверка cooldown
                    if not can_send_signal(symbol, side, 'entry'):
                        logger.info(f"⏳ Сигнал {signal} для {symbol} ({tf}) пропущен: cooldown")
                        return

                    if candle_key in last_signal_candle:
                        if last_signal_candle[candle_key] == current_candle_time:
                            logger.info(f"⏸️ Сигнал {signal} для {symbol} ({tf}) пропущен: уже был на этой свече")
                            return

                    if self.gate.is_position_open(symbol, side):
                        logger.info(f"⚠️ Сигнал {signal} для {symbol} пропущен: позиция уже открыта")
                        return

                    last_signal_candle[candle_key] = current_candle_time

                self.stats['as_signals'] += 1
                self._handle_as_signal(result, symbol, tf, as_strategy)
        except Exception as e:
            self.log(f"⚠️ Ошибка AS {symbol} ({tf}): {e}")

    def _should_skip_opening(self, symbol, side, strategy='AS'):
        """Раздельные cooldown для MR и AS"""
        close_key = (symbol, side)

        cooldown_dict = mr_last_close_time if strategy == 'MR' else as_last_close_time
        cooldown_seconds = self.config.get('MR_COOLDOWN_SECONDS' if strategy == 'MR' else 'AS_COOLDOWN_SECONDS', 120)

        if close_key in cooldown_dict:
            elapsed = time.time() - cooldown_dict[close_key]
            if elapsed < cooldown_seconds:
                logger.warning(f"⏸️ [{strategy}] {symbol} ({side}) закрыта {elapsed:.0f}с назад (< {cooldown_seconds}с), пропускаем")
                return True

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT close_reason, timestamp, strategy
                    FROM trades
                    WHERE symbol = ? AND side = ? AND status = 'CLOSED' AND strategy = ?
                    ORDER BY timestamp DESC LIMIT 1
                """, (symbol, side, strategy))
                row = cursor.fetchone()
                if row:
                    close_reason = row[0]
                    close_time = row[1]
                    elapsed = time.time() - close_time

                    if close_reason in ["stop_loss", "trailing_stop", "closed_on_exchange"]:
                        if elapsed < cooldown_seconds * 2.5:
                            logger.warning(f"⚠️ [{strategy}] {symbol} ({side}) закрыта по {close_reason} {elapsed:.0f}с назад")
                            return True

                    if elapsed < cooldown_seconds:
                        logger.warning(f"⏸️ [{strategy}] {symbol} ({side}) закрыта {elapsed:.0f}с назад")
                        return True
        except Exception as e:
            logger.error(f"Ошибка проверки БД: {e}")

        return False

    def _handle_mr_signal(self, result, symbol_a, symbol_b, tf):
        signal = result['signal']
        mode = self.config['TRADING_MODE']
        self.stats['signals_generated'] += 1

        msg = (
            f"📊 Mean Reversion Signal\n"
            f"🎯 Сигнал: {signal}\n"
            f"💱 Пара: {symbol_a}/{symbol_b}\n"
            f"📊 ТФ: {tf}\n"
            f"📈 Z-Score: {result['z_score']:.3f}"
        )
        self.log(f"MR Signal: {signal} {symbol_a}/{symbol_b} ({tf})")
        self.notifier.send(msg)

        if mode == 'live' and self.gate:
            self._execute_mr_trade(signal, symbol_a, symbol_b, result, tf)

    def _handle_as_signal(self, result, symbol, tf, as_strategy: AdaptiveScalpingStrategy):
        signal = result['signal']
        mode = self.config['TRADING_MODE']
        self.stats['signals_generated'] += 1

        msg = (
            f"⚡ Adaptive Scalping Signal\n"
            f"🎯 Сигнал: {signal}\n"
            f"💱 Символ: {symbol}\n"
            f"📊 ТФ: {tf}\n"
            f"🌍 Режим: {result['regime']}\n"
            f"📉 RSI: {result.get('rsi', 0):.1f}"
        )
        self.log(f"⚡ AS Signal: {signal} {symbol} ({tf}) [regime={result['regime']}]")
        self.notifier.send(msg)

        if mode == 'live' and self.gate:
            self._execute_as_trade(signal, symbol, result, tf, as_strategy)

    def _execute_mr_trade(self, signal, symbol_a, symbol_b, result, tf):
        try:
            balance = self.gate.get_balance_usdt()
            if not balance:
                return

            max_trades = self.config.get('MR_MAX_POSITIONS', 2)
            if check_max_open_trades_by_strategy('MR', max_trades):
                msg = f"⚠️ Лимит MR позиций достигнут ({max_trades}), MR сделка пропущена"
                logger.warning(msg)
                self.notifier.send(msg)
                return

            if self.config['ORDER_TYPE'] == 'percentage':
                position_size = balance * (self.config['MR_POSITION_SIZE_PCT'] / 100)
            else:
                position_size = self.config['FIXED_VOLUME']

            if signal == 'BUY_SPREAD':
                if self._should_skip_opening(symbol_a, 'buy', 'MR'):
                    self.notifier.send(f"⏸️ MR пропущен: {symbol_a} (buy) на кулдауне")
                    return
                if self._should_skip_opening(symbol_b, 'sell', 'MR'):
                    self.notifier.send(f"⏸️ MR пропущен: {symbol_b} (sell) на кулдауне")
                    return

                qty_a = self.gate.calculate_qty(symbol_a, position_size / 2)
                qty_b = self.gate.calculate_qty(symbol_b, position_size / 2)

                if not qty_a or not qty_b:
                    err_msg = f"❌ MR: Не удалось рассчитать объем для {symbol_a} (qty={qty_a}) или {symbol_b} (qty={qty_b}). Проверьте баланс или мин. размер контракта."
                    logger.error(err_msg)
                    self.notifier.send(err_msg)
                    return

                id_a, actual_qty_a = self.gate.place_order(
                    symbol_a, 'buy', tf, qty_a, strategy='MR', notifier=self.notifier
                )
                id_b, actual_qty_b = self.gate.place_order(
                    symbol_b, 'sell', tf, qty_b, strategy='MR', notifier=self.notifier
                )

                if id_a and id_b:
                    self.stats['trades_opened'] += 1
                    self.mr_strategy.positions[(symbol_a, symbol_b)] = {
                        'side': 'LONG',
                        'entry_a': result['price_a'],
                        'entry_b': result['price_b'],
                    }
                else:
                    err_msg = f"⚠️ MR: Ошибка открытия ног! BTC(id={id_a}), ETH(id={id_b}). Проверьте маржу!"
                    logger.error(err_msg)
                    self.notifier.send(err_msg)

            elif signal == 'SELL_SPREAD':
                if self._should_skip_opening(symbol_a, 'sell', 'MR'):
                    self.notifier.send(f"⏸️ MR пропущен: {symbol_a} (sell) на кулдауне")
                    return
                if self._should_skip_opening(symbol_b, 'buy', 'MR'):
                    self.notifier.send(f"⏸️ MR пропущен: {symbol_b} (buy) на кулдауне")
                    return

                qty_a = self.gate.calculate_qty(symbol_a, position_size / 2)
                qty_b = self.gate.calculate_qty(symbol_b, position_size / 2)

                if not qty_a or not qty_b:
                    err_msg = f"❌ MR: Не удалось рассчитать объем для {symbol_a} (qty={qty_a}) или {symbol_b} (qty={qty_b})."
                    logger.error(err_msg)
                    self.notifier.send(err_msg)
                    return

                id_a, actual_qty_a = self.gate.place_order(
                    symbol_a, 'sell', tf, qty_a, strategy='MR', notifier=self.notifier
                )
                id_b, actual_qty_b = self.gate.place_order(
                    symbol_b, 'buy', tf, qty_b, strategy='MR', notifier=self.notifier
                )

                if id_a and id_b:
                    self.stats['trades_opened'] += 1
                    self.mr_strategy.positions[(symbol_a, symbol_b)] = {
                        'side': 'SHORT',
                        'entry_a': result['price_a'],
                        'entry_b': result['price_b'],
                    }
                else:
                    err_msg = f"⚠️ MR: Ошибка открытия ног! BTC(id={id_a}), ETH(id={id_b})."
                    logger.error(err_msg)
                    self.notifier.send(err_msg)

            elif signal in ['CLOSE_LONG', 'CLOSE_SHORT']:
                key = (symbol_a, symbol_b)
                if key in self.mr_strategy.positions:
                    pos = self.mr_strategy.positions[key]
                    qty_a = self.gate.calculate_qty(symbol_a, position_size / 2)
                    qty_b = self.gate.calculate_qty(symbol_b, position_size / 2)
                    if qty_a and qty_b:
                        if pos['side'] == 'LONG':
                            self.gate.close_position_enhanced(symbol_a, 'buy', qty_a, reason="mr_close", notifier=self.notifier)
                            self.gate.close_position_enhanced(symbol_b, 'sell', qty_b, reason="mr_close", notifier=self.notifier)
                        else:
                            self.gate.close_position_enhanced(symbol_a, 'sell', qty_a, reason="mr_close", notifier=self.notifier)
                            self.gate.close_position_enhanced(symbol_b, 'buy', qty_b, reason="mr_close", notifier=self.notifier)
                        self.stats['trades_closed'] += 1
                        del self.mr_strategy.positions[key]

        except Exception as e:
            self.log(f"❌ Ошибка исполнения MR: {e}")

    def _execute_as_trade(self, signal, symbol, result, tf, as_strategy: AdaptiveScalpingStrategy):
        try:
            balance = self.gate.get_balance_usdt()
            if not balance:
                return

            max_trades = self.config.get('AS_MAX_POSITIONS', 3)
            if check_max_open_trades_by_strategy('AS', max_trades):
                msg = f"⚠️ Лимит AS позиций достигнут ({max_trades}), AS сделка пропущена"
                logger.warning(msg)
                self.notifier.send(msg)
                return

            if self.config['ORDER_TYPE'] == 'percentage':
                position_size = balance * (self.config['AS_POSITION_SIZE_PCT'] / 100)
            else:
                position_size = self.config['FIXED_VOLUME']

            qty = self.gate.calculate_qty(symbol, position_size)
            if not qty:
                return

            regime = as_strategy.current_regime.value
            optimized_params = as_strategy.optimized_params

            if signal == 'BUY':
                if self._should_skip_opening(symbol, 'buy', 'AS'):
                    self.notifier.send(f"⏸️ AS пропущен: {symbol} (buy) на кулдауне")
                    return
                order_id, actual_qty = self.gate.place_order(
                    symbol, 'buy', tf, qty, strategy='AS', notifier=self.notifier,
                    market_regime=regime, optimized_params=optimized_params
                )
                if order_id:
                    self.stats['trades_opened'] += 1
                    as_strategy.positions[symbol] = {
                        'side': 'LONG',
                        'entry_price': result['price'],
                        'qty': actual_qty,
                    }

            elif signal == 'SELL':
                if self._should_skip_opening(symbol, 'sell', 'AS'):
                    self.notifier.send(f"⏸️ AS пропущен: {symbol} (sell) на кулдауне")
                    return
                order_id, actual_qty = self.gate.place_order(
                    symbol, 'sell', tf, qty, strategy='AS', notifier=self.notifier,
                    market_regime=regime, optimized_params=optimized_params
                )
                if order_id:
                    self.stats['trades_opened'] += 1
                    as_strategy.positions[symbol] = {
                        'side': 'SHORT',
                        'entry_price': result['price'],
                        'qty': actual_qty,
                    }

            elif signal.startswith('CLOSE_'):
                if symbol in as_strategy.positions:
                    pos = as_strategy.positions[symbol]
                    side = 'buy' if pos['side'] == 'LONG' else 'sell'
                    order_id, _ = self.gate.close_position_enhanced(
                        symbol, side, pos['qty'], reason="as_close", notifier=self.notifier
                    )
                    if order_id:
                        self.stats['trades_closed'] += 1
                        del as_strategy.positions[symbol]

        except Exception as e:
            self.log(f"❌ Ошибка исполнения AS: {e}")

    def get_stats_text(self):
        return (
            f"📊 Сигналов: {self.stats['signals_generated']}\n"
            f"  • MR: {self.stats['mr_signals']}\n"
            f"  • AS: {self.stats['as_signals']}\n"
            f"📈 Открыто сделок: {self.stats['trades_opened']}\n"
            f"📉 Закрыто сделок: {self.stats['trades_closed']}\n"
            f"💰 PnL: {self.stats['total_pnl']:+.2f} USDT\n"
            f"🎯 Активных AS-стратегий: {len(self.as_strategies)}"
        )

    def close_all_positions(self):
        if not self.gate:
            return "❌ Gate.io не инициализирован"

        positions = self.gate._normalize_positions(self.gate.futures_api.list_positions(settle='usdt'))
        closed_count = 0
        failed = []

        for pos in positions:
            if float(pos.size) != 0:
                symbol = pos.contract
                side = 'buy' if float(pos.size) > 0 else 'sell'
                contract = self.gate.futures_api.get_futures_contract(settle='usdt', contract=symbol)
                qty = abs(float(pos.size)) * float(contract.quanto_multiplier)

                order_id, actual_qty = self.gate.close_position_enhanced(
                    symbol, side, qty, reason="closeall_real", notifier=self.notifier
                )
                if order_id:
                    closed_count += 1
                else:
                    failed.append(f"{symbol} ({side})")

        if closed_count == 0:
            return "ℹ️ Нет открытых позиций"
        msg = f"✅ Закрыто {closed_count} позиций"
        if failed:
            msg += f"\n❌ Не удалось закрыть: {', '.join(set(failed))}"
        return msg

    def get_open_positions_status(self):
        if not self.gate:
            return "Gate.io не инициализирован"

        positions = self.gate._normalize_positions(self.gate.futures_api.list_positions(settle='usdt'))
        balance = self.gate.get_balance_usdt() or 0

        if not positions or all(float(pos.size) == 0 for pos in positions):
            return "📊 Нет открытых позиций"

        response = f"📊 Статус ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}):\n"
        response += f"💳 Свободный баланс: {balance:.2f} USDT\n\n"
        response += "Открытые позиции:\n"

        for pos in positions:
            if float(pos.size) != 0:
                symbol = pos.contract
                side = 'buy' if float(pos.size) > 0 else 'sell'
                entry_price = float(pos.entry_price)
                current_price = self.gate.get_current_price(symbol) or entry_price
                pnl = float(pos.unrealised_pnl)

                margin = 0
                margin_offline = False

                initial_margin = float(getattr(pos, 'initial_margin', 0))
                margin = float(getattr(pos, 'margin', initial_margin))

                if margin == 0 or str(margin) == '0':
                    margin_offline = True
                    try:
                        contract = self.gate.futures_api.get_futures_contract(settle='usdt', contract=symbol)
                        quanto_multiplier = float(contract.quanto_multiplier)
                        size = abs(float(pos.size))
                        leverage = float(getattr(pos, 'leverage', self.config['LEVERAGE']))

                        position_value = size * quanto_multiplier * entry_price
                        if leverage > 0:
                            margin = position_value / leverage
                            logger.info(f"🔧 MARGIN FALLBACK: {symbol} margin=0, calculated={margin:.2f} USDT (leverage={leverage}x)")
                    except Exception as e:
                        logger.error(f"❌ Error calculating fallback margin: {e}")
                        margin = 0

                leverage = float(getattr(pos, 'leverage', self.config['LEVERAGE']))

                pnl_percent = 0.0
                if margin > 0.01:
                    pnl_percent = (pnl / margin * 100)
                elif leverage > 0:
                    try:
                        contract = self.gate.futures_api.get_futures_contract(settle='usdt', contract=symbol)
                        quanto_multiplier = float(contract.quanto_multiplier)
                        size = abs(float(pos.size))
                        position_value = size * quanto_multiplier * entry_price
                        if position_value > 0:
                            pnl_percent = (pnl / position_value * 100) * leverage
                    except:
                        pass

                open_trades = get_open_trades_by_symbol_and_side(symbol, side)
                lifetime_text = ""
                if open_trades:
                    open_time = open_trades[0].get('open_time') or open_trades[0].get('timestamp')
                    if open_time:
                        lifetime_text = f" ({_format_duration(int(time.time()) - open_time)})"

                margin_suffix = " (офлайн)" if margin_offline else ""

                response += (
                    f"{symbol} ({side}){lifetime_text}:\n"
                    f"  💵 Маржа: {margin:.2f} USDT{margin_suffix} (плечо: {leverage:.0f}x)\n"
                    f"  🎯 Вход: {entry_price:.6f}\n"
                    f"  📊 Текущая: {current_price:.6f}\n"
                    f"  {'Прибыль' if pnl >= 0 else 'Убыток'}: {abs(pnl):.2f} USDT ({pnl_percent:+.2f}%)\n\n"
                )

        return response.strip()

    def get_sl_status(self):
        open_trades = get_open_trades()
        response = "📊 Статус позиций:\n"

        if open_trades:
            for trade in open_trades:
                response += (
                    f"{trade['symbol']} ({trade['side']}):\n"
                    f"- Стоп: {trade.get('current_stop_price', 0):.4f}\n"
                    f"- Трейлинг: {'Активен' if trade.get('trailing_active') else 'Не активен'}\n"
                    f"- Режим рынка: {trade.get('market_regime', 'N/A')}\n"
                )
        else:
            response += "- Нет открытых позиций\n"

        today = int(time.time() // 86400) * 86400
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT close_reason, COUNT(*) FROM trades
                WHERE status = 'CLOSED' AND timestamp >= ?
                GROUP BY close_reason
            ''', (today,))
            stats = {row[0]: row[1] for row in cursor.fetchall()}

        response += f"\n📈 Статистика за сегодня:\n"
        response += f"- 🛑 Стоп-лоссы: {stats.get('stop_loss', 0)}\n"
        response += f"- 🎯 Тейк-профиты: {stats.get('take_profit', 0) + stats.get('take_profit_partial', 0)}\n"
        response += f"- 🔄 Трейлинг-стопы: {stats.get('trailing_stop', 0)}\n"
        response += f"- ⌨️ Вручную: {stats.get('manual', 0) + stats.get('closeall_real', 0) + stats.get('sellall', 0)}\n"

        return response

    def get_history(self, limit=10):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM trades WHERE status = 'CLOSED'
                ORDER BY timestamp DESC LIMIT ?
            ''', (limit,))
            trades = [dict(t) for t in cursor.fetchall()]

        if not trades:
            return "📜 История сделок пуста."

        response = f"📜 История сделок (до {limit}):\n"
        for trade in trades:
            symbol = trade['symbol']
            side = trade['side']
            entry_price = trade.get('price', 0)
            close_price = trade.get('close_price', 0)
            profit = trade.get('pnl', 0)
            margin = trade.get('margin', 0) or 0
            timestamp = datetime.fromtimestamp(trade['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
            reason = trade.get('close_reason', 'N/A')

            profit_percentage = (profit / margin * 100) if margin > 0.01 else 0
            profit_label = "Прибыль" if profit >= 0 else "Убыток"

            response += (
                f"{symbol} ({side})\n"
                f"- Вход: {entry_price:.4f}\n"
                f"- Выход: {close_price:.4f}\n"
                f"- {profit_label}: {abs(profit):.2f} USDT ({profit_percentage:+.2f}%)\n"
                f"- Причина: {reason}\n"
                f"- Режим: {trade.get('market_regime', 'N/A')}\n"
                f"- Время: {timestamp}\n\n"
            )

        return response

    def get_report(self):
        balance = self.gate.get_balance_usdt() if self.gate else 0
        open_trades = get_open_trades()
        today = int(time.time() // 86400) * 86400

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT SUM(pnl), SUM(fees), COUNT(*) FROM trades
                WHERE status = 'CLOSED' AND timestamp >= ?
            ''', (today,))
            row = cursor.fetchone()
            total_pnl = row[0] or 0
            total_fees = row[1] or 0
            closed_trades = row[2] or 0

        total_result = total_pnl - total_fees
        label = "🟢 Прибыль" if total_result >= 0 else "🔴 Убыток"

        report = (
            f"📋 Отчёт за {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"📌 Сводка дня: {label} {abs(total_result):.2f} USDT\n\n"
            f"💵 Баланс: {balance:.2f} USDT\n"
            f"📈 Открытые позиции: {len(open_trades)}\n"
            f"📉 Закрытые сделки: {closed_trades}\n"
            f"💸 Комиссии: {total_fees:.2f} USDT\n"
            f"🎯 Итог: {total_result:+.2f} USDT"
        )
        return report

# ==================== TELEGRAM КОМАНДЫ ====================
# ==================== TELEGRAM КОМАНДЫ ====================
class TelegramCommands:
    def __init__(self, synergy_bot):
        self.synergy_bot = synergy_bot
        self.notifier = synergy_bot.notifier  # ✅ Используем тот же бот
        self.bot = self.notifier.bot if self.notifier else None
        if self.bot:
            try:
                self._register_handlers()
                logger.info("✅ Telegram команды зарегистрированы (используется общий бот)")
            except Exception as e:
                logger.error(f"Ошибка инициализации команд: {e}")

    def _register_handlers(self):
        @self.bot.message_handler(commands=['start'])
        def cmd_start(message):
            self.synergy_bot.start()
            self.bot.reply_to(message, "✅ Бот запущен")

        @self.bot.message_handler(commands=['stop'])
        def cmd_stop(message):
            self.synergy_bot.stop()
            self.bot.reply_to(message, "🛑 Бот остановлен")

        @self.bot.message_handler(commands=['signals_only'])
        def cmd_signals_only(message):
            self.synergy_bot.config['TRADING_MODE'] = 'signals_only'
            self.bot.reply_to(message, "📡 Режим: только сигналы (алерты)")

        @self.bot.message_handler(commands=['live'])
        def cmd_live(message):
            self.synergy_bot.config['TRADING_MODE'] = 'live'
            self.bot.reply_to(message, "💰 Режим: live торговля")

        @self.bot.message_handler(commands=['stats'])
        def cmd_stats(message):
            self.bot.reply_to(message, self.synergy_bot.get_stats_text())

        @self.bot.message_handler(commands=['status', 'positions'])
        def cmd_status(message):
            self.bot.reply_to(message, self.synergy_bot.get_open_positions_status())

        @self.bot.message_handler(commands=['balance'])
        def cmd_balance(message):
            if self.synergy_bot.gate:
                balance = self.synergy_bot.gate.get_balance_usdt()
                self.bot.reply_to(message, f"💳 Баланс: {balance:.2f} USDT" if balance else "❌ Ошибка получения баланса")
            else:
                self.bot.reply_to(message, "❌ Gate.io не инициализирован")

        @self.bot.message_handler(commands=['sl'])
        def cmd_sl(message):
            self.bot.reply_to(message, self.synergy_bot.get_sl_status())

        @self.bot.message_handler(commands=['history'])
        def cmd_history(message):
            self.bot.reply_to(message, self.synergy_bot.get_history())

        @self.bot.message_handler(commands=['report'])
        def cmd_report(message):
            self.bot.reply_to(message, self.synergy_bot.get_report())

        @self.bot.message_handler(commands=['closeall'])
        def cmd_closeall(message):
            result = self.synergy_bot.close_all_positions()
            self.bot.reply_to(message, result)

        @self.bot.message_handler(commands=['sellall'])
        def cmd_sellall(message):
            result = self.synergy_bot.close_all_positions()
            self.bot.reply_to(message, result)

        @self.bot.message_handler(commands=['close'])
        def cmd_close(message):
            args = message.text.strip().split()
            if len(args) != 2:
                self.bot.reply_to(message, "📝 Формат: /close <symbol> (например, /close BTC_USDT)")
                return
            symbol = args[1].upper()
            if not symbol.endswith('_USDT'):
                symbol += '_USDT'

            if not self.synergy_bot.gate:
                self.bot.reply_to(message, "❌ Gate.io не инициализирован")
                return

            positions = self.synergy_bot.gate._normalize_positions(
                self.synergy_bot.gate.futures_api.list_positions(settle='usdt')
            )
            closed = False
            for pos in positions:
                if pos.contract == symbol and float(pos.size) != 0:
                    side = 'buy' if float(pos.size) > 0 else 'sell'
                    contract = self.synergy_bot.gate.futures_api.get_futures_contract(
                        settle='usdt', contract=symbol
                    )
                    qty = abs(float(pos.size)) * float(contract.quanto_multiplier)
                    order_id, _ = self.synergy_bot.gate.close_position_enhanced(
                        symbol, side, qty, reason="manual",
                        notifier=self.synergy_bot.notifier
                    )
                    if order_id:
                        self.bot.reply_to(message, f"✅ Позиция {symbol} ({side}) закрыта")
                        closed = True
                    else:
                        self.bot.reply_to(message, f"❌ Ошибка закрытия {symbol}")
                    break
            if not closed:
                self.bot.reply_to(message, f"ℹ️ Нет открытой позиции для {symbol}")

        @self.bot.message_handler(commands=['help'])
        def cmd_help(message):
            text = (
                "📜 Команды skalpMat\n\n"
                "/start - Запустить бота\n"
                "/stop - Остановить бота\n"
                "/signals_only - Режим алертов\n"
                "/live - Режим live торговли\n"
                "/status - Статус позиций\n"
                "/positions - То же, что /status\n"
                "/balance - Баланс USDT\n"
                "/sl - Статус стоп-лоссов\n"
                "/history - История сделок\n"
                "/report - Отчёт за день\n"
                "/closeall - Закрыть все позиции\n"
                "/sellall - Продать все позиции\n"
                "/close <symbol> - Закрыть позицию по монете\n"
                "/stats - Статистика сигналов\n"
                "/help - Эта справка"
            )
            self.bot.reply_to(message, text)

    def start_polling(self):
        """✅ Запускаем polling ТОЛЬКО один раз"""
        if self.bot:
            # Проверяем, не запущен ли polling уже
            if hasattr(self.bot, '_polling_thread') and self.bot._polling_thread.is_alive():
                logger.info("ℹ️ Polling уже запущен, пропускаем")
                return

            def polling_with_retry():
                while True:
                    try:
                        logger.info("🔄 Запуск Telegram polling...")
                        self.bot.polling(none_stop=True, interval=1, timeout=60)
                    except Exception as e:
                        error_msg = str(e)
                        if '409' in error_msg:
                            logger.error(f"❌ Конфликт polling (409). Ждём 10 сек...")
                            time.sleep(10)
                        elif '429' in error_msg:
                            logger.error(f"⚠️ Rate limit (429). Ждём 30 сек...")
                            time.sleep(30)
                        else:
                            logger.error(f"❌ Ошибка polling: {e}")
                            time.sleep(5)

            self.bot._polling_thread = threading.Thread(
                target=polling_with_retry,
                daemon=True
            )
            self.bot._polling_thread.start()
            logger.info("✅ Telegram polling запущен в отдельном потоке")

# ==================== FLET GUI ====================
class SynergyApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.bot = None
        self.tg_commands = None
        self.msg_queue = queue.Queue()
        self._build_main_view()
        if ensure_env_exists():
            self._append_log("📄 Файл .env создан")
        try:
            init_database()
        except Exception as e:
            self._append_log(f"❌ Ошибка инициализации БД: {e}")
        self._poll_queue()

    def _poll_queue(self):
        batch = 0
        while not self.msg_queue.empty() and batch < 50:
            try:
                msg_type, text = self.msg_queue.get_nowait()
                if msg_type == 'log':
                    self._append_log(text)
                elif msg_type == 'status':
                    self._update_status_ui(text)
                batch += 1
            except Exception:
                break
        self.page.run_task(self._poll_queue_delayed)

    async def _poll_queue_delayed(self):
        import asyncio
        await asyncio.sleep(0.05)
        self._poll_queue()

    def _append_log(self, text):
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {text}"
        if hasattr(self, 'log_view') and self.log_view:
            self.log_view.controls.append(
                ft.Text(line, size=11, font_family="Consolas", color=ft.Colors.GREEN_ACCENT_200)
            )
            if len(self.log_view.controls) > 500:
                self.log_view.controls = self.log_view.controls[-500:]
            self.log_view.update()

    def _update_status_ui(self, text):
        if hasattr(self, 'status_text') and self.status_text:
            self.status_text.value = f"🔍 {text}"
            self.status_text.update()

    def _log_fn(self, text):
        self.msg_queue.put(('log', text))

    def _status_fn(self, text):
        self.msg_queue.put(('status', text))

    # ==================== КАРУСЕЛЬ ОТКРЫТЫХ ПОЗИЦИЙ ====================
    def _start_positions_carousel(self):
        """Запускаем фоновый поток для карусели открытых позиций"""
        if hasattr(self, '_carousel_running') and self._carousel_running:
            return

        self._carousel_running = True
        self._carousel_index = 0
        self._carousel_positions = []

        def carousel_loop():
            while self._carousel_running:
                try:
                    if self.bot and self.bot.gate:
                        positions = self.bot.gate._normalize_positions(
                            self.bot.gate.futures_api.list_positions(settle='usdt')
                        )
                        open_positions = []
                        for pos in positions:
                            if float(pos.size) != 0:
                                symbol = pos.contract
                                side = 'buy' if float(pos.size) > 0 else 'sell'
                                entry_price = float(pos.entry_price)
                                current_price = self.bot.gate.get_current_price(symbol) or entry_price
                                pnl = float(pos.unrealised_pnl)
                                margin = float(getattr(pos, 'margin', 0) or 0)

                                # Fallback для маржи
                                if margin == 0:
                                    try:
                                        contract = self.bot.gate.futures_api.get_futures_contract(
                                            settle='usdt', contract=symbol
                                        )
                                        quanto_multiplier = float(contract.quanto_multiplier)
                                        size = abs(float(pos.size))
                                        leverage = float(getattr(pos, 'leverage', self.bot.config['LEVERAGE']))
                                        position_value = size * quanto_multiplier * entry_price
                                        if leverage > 0:
                                            margin = position_value / leverage
                                    except:
                                        pass

                                pnl_pct = (pnl / margin * 100) if margin > 0.01 else 0
                                open_positions.append({
                                    'symbol': symbol,
                                    'side': side,
                                    'pnl': pnl,
                                    'pnl_pct': pnl_pct,
                                    'entry': entry_price,
                                    'current': current_price
                                })

                        self._carousel_positions = open_positions

                        if open_positions:
                            # Показываем по очереди
                            if self._carousel_index >= len(open_positions):
                                self._carousel_index = 0

                            pos = open_positions[self._carousel_index]
                            pnl_sign = '+' if pos['pnl'] >= 0 else ''
                            pnl_color = '🟢' if pos['pnl'] >= 0 else '🔴'

                            display_text = (
                                f"{pnl_color} {pos['symbol']} ({pos['side']}) | "
                                f"Вход: {pos['entry']:.4f} → {pos['current']:.4f} | "
                                f"{pnl_sign}{pos['pnl']:.2f} USDT ({pnl_sign}{pos['pnl_pct']:.2f}%)"
                            )

                            self._carousel_index += 1
                        else:
                            display_text = "📊 Нет открытых позиций"

                        self._update_positions_carousel(display_text)
                    else:
                        self._update_positions_carousel("⏸️ Бот не запущен")

                except Exception as e:
                    logger.error(f"Ошибка карусели позиций: {e}")

                time.sleep(4)  # Переключаем каждые 4 секунды

        thread = threading.Thread(target=carousel_loop, daemon=True)
        thread.start()
        logger.info("✅ Карусель открытых позиций запущена")

    def _update_positions_carousel(self, text):
        """Обновляем отображение карусели позиций"""
        if hasattr(self, 'positions_carousel_text') and self.positions_carousel_text:
            self.positions_carousel_text.value = text
            self.positions_carousel_text.update()

    def _stop_positions_carousel(self):
        """Останавливаем карусель"""
        self._carousel_running = False

    # ==================== БЭКТЕСТ ====================
    def run_backtest(self, e=None):
        """Запуск бэктеста на 1000 свечей с текущим балансом"""
        if not self.bot or not self.bot.gate:
            self._append_log("⚠️ Бот не запущен или Gate.io не инициализирован")
            return

        self._append_log("🧪 Запуск бэктеста на 1000 свечей...")
        self._append_log("⏳ Это может занять 30-60 секунд...")

        def backtest_thread():
            try:
                config = self.bot.config
                symbols = config['AS_SYMBOLS']
                timeframes = config['AS_TIMEFRAMES']
                leverage = config['LEVERAGE']
                trading_fee_pct = config.get('TRADING_FEE', 0.1) / 100

                # ✅ Получаем текущий баланс
                current_balance = self.bot.gate.get_balance_usdt()
                if not current_balance or current_balance < 10:
                    self._append_log("⚠️ Недостаточный баланс для бэктеста")
                    return

                # ✅ Используем реальный размер позиции как в live режиме
                if config['ORDER_TYPE'] == 'percentage':
                    position_size_usdt = current_balance * (config['QTY_PERCENTAGE'] / 100)
                else:
                    position_size_usdt = config['FIXED_VOLUME']

                total_trades = 0
                winning_trades = 0
                losing_trades = 0
                breakeven_trades = 0
                total_pnl = 0.0
                max_drawdown = 0.0
                peak_equity = current_balance
                current_equity = current_balance
                equity_curve = [current_balance]

                all_results = []

                for symbol in symbols:
                    for tf in timeframes:
                        self._append_log(f"📊 Бэктест: {symbol} ({tf})")

                        df = self.bot.gate.get_ohlcv(symbol, tf, limit=1000)
                        if df.empty or len(df) < 150:
                            self._append_log(f"  ⚠️ Недостаточно данных для {symbol} ({tf}): {len(df)} свечей")
                            continue

                        as_strategy = AdaptiveScalpingStrategy(config, f"{symbol}_{tf}")
                        df = as_strategy.calculate_indicators(df.copy())

                        position = None
                        entry_price = 0
                        entry_idx = 0
                        symbol_trades = 0
                        symbol_wins = 0
                        symbol_pnl = 0.0

                        for i in range(100, len(df)):
                            row = df.iloc[i]

                            if pd.isna(row.get('rsi')) or pd.isna(row.get('bb_pct')):
                                continue

                            signal = None
                            if row['bb_pct'] < 0.1 and row['rsi'] < config['AS_RSI_OVERSOLD']:
                                signal = 'BUY'
                            elif row['bb_pct'] > 0.9 and row['rsi'] > config['AS_RSI_OVERBOUGHT']:
                                signal = 'SELL'

                            if position:
                                tp_pct = config['AS_TAKE_PROFIT_PCT'] / 100
                                sl_pct = config['AS_STOP_LOSS_PCT'] / 100

                                if position == 'LONG':
                                    high_pct = (row['high'] - entry_price) / entry_price
                                    low_pct = (row['low'] - entry_price) / entry_price

                                    if high_pct >= tp_pct:
                                        # ✅ Рассчитываем PnL как в live режиме
                                        pnl = position_size_usdt * tp_pct * leverage
                                        fee = position_size_usdt * tp_pct * trading_fee_pct
                                        net_pnl = pnl - fee
                                        symbol_pnl += net_pnl
                                        symbol_wins += 1
                                        symbol_trades += 1
                                        position = None
                                    elif low_pct <= -sl_pct:
                                        pnl = -position_size_usdt * sl_pct * leverage
                                        fee = position_size_usdt * sl_pct * trading_fee_pct
                                        net_pnl = pnl - fee
                                        symbol_pnl += net_pnl
                                        symbol_trades += 1
                                        position = None
                                elif position == 'SHORT':
                                    low_pct = (entry_price - row['low']) / entry_price
                                    high_pct = (entry_price - row['high']) / entry_price

                                    if low_pct >= tp_pct:
                                        pnl = position_size_usdt * tp_pct * leverage
                                        fee = position_size_usdt * tp_pct * trading_fee_pct
                                        net_pnl = pnl - fee
                                        symbol_pnl += net_pnl
                                        symbol_wins += 1
                                        symbol_trades += 1
                                        position = None
                                    elif high_pct <= -sl_pct:
                                        pnl = -position_size_usdt * sl_pct * leverage
                                        fee = position_size_usdt * sl_pct * trading_fee_pct
                                        net_pnl = pnl - fee
                                        symbol_pnl += net_pnl
                                        symbol_trades += 1
                                        position = None

                            if not position and signal:
                                position = 'LONG' if signal == 'BUY' else 'SHORT'
                                entry_price = row['close']
                                entry_idx = i

                            current_equity = current_balance + symbol_pnl
                            equity_curve.append(current_equity)
                            if current_equity > peak_equity:
                                peak_equity = current_equity
                            drawdown = (peak_equity - current_equity) / peak_equity * 100
                            max_drawdown = max(max_drawdown, drawdown)

                        # Закрываем оставшуюся позицию по последней цене
                        if position and len(df) > 0:
                            last_price = df.iloc[-1]['close']
                            if position == 'LONG':
                                pnl = (last_price - entry_price) / entry_price * position_size_usdt * leverage
                            else:
                                pnl = (entry_price - last_price) / entry_price * position_size_usdt * leverage
                            symbol_pnl += pnl
                            symbol_trades += 1
                            if pnl > 0:
                                symbol_wins += 1

                        total_trades += symbol_trades
                        winning_trades += symbol_wins
                        losing_trades += (symbol_trades - symbol_wins)
                        total_pnl += symbol_pnl

                        win_rate = (symbol_wins / symbol_trades * 100) if symbol_trades > 0 else 0
                        self._append_log(f"  ✅ {symbol} ({tf}): {symbol_trades} сделок, WR={win_rate:.1f}%, PnL={symbol_pnl:+.2f}")

                        all_results.append({
                            'symbol': symbol,
                            'tf': tf,
                            'trades': symbol_trades,
                            'wins': symbol_wins,
                            'pnl': symbol_pnl,
                            'win_rate': win_rate
                        })

                win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
                avg_win = (total_pnl / winning_trades) if winning_trades > 0 else 0
                avg_loss = (total_pnl / losing_trades) if losing_trades > 0 else 0
                profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf') if total_pnl > 0 else 0

                result = f"""
{'='*60}
🧪 РЕЗУЛЬТАТЫ БЭКТЕСТА (1000 свечей)
{'='*60}
💵 Начальный баланс: {current_balance:.2f} USDT
📊 Размер позиции: {position_size_usdt:.2f} USDT
📈 Всего сделок: {total_trades}
✅ Прибыльных: {winning_trades}
❌ Убыточных: {losing_trades}
📈 Win Rate: {win_rate:.1f}%
💰 Общий PnL: {total_pnl:+.2f} USDT
📉 Max Drawdown: {max_drawdown:.2f}%
🎯 Profit Factor: {profit_factor:.2f}
{'='*60}
📋 Детализация по парам:
"""
                for r in all_results:
                    result += f"  • {r['symbol']} ({r['tf']}): {r['trades']} сделок, WR={r['win_rate']:.1f}%, PnL={r['pnl']:+.2f}\n"
                result += "=" * 60

                self._append_log(result)

            except Exception as ex:
                logger.error(f"Ошибка бэктеста: {ex}")
                self._append_log(f"❌ Ошибка бэктеста: {ex}")

        thread = threading.Thread(target=backtest_thread, daemon=True)
        thread.start()

    def start_bot(self, e=None):
        if self.bot and self.bot.is_running:
            self._append_log("⚠️ Бот уже запущен")
            return

        self._append_log("🚀 Запуск skalpMat...")
        self.bot = SynergyBot(self._log_fn, self._status_fn)
        self.tg_commands = TelegramCommands(self.bot)
        self.tg_commands.start_polling()
        self.bot.start()
        self._update_buttons(True)
        self._start_positions_carousel()

    def stop_bot(self, e=None):
        if not self.bot or not self.bot.is_running:
            self._append_log("ℹ️ Бот не запущен")
            return
        self.bot.stop()
        self._stop_positions_carousel()
        self._update_buttons(False)

    def toggle_bot(self, e=None):
        if self.bot and self.bot.is_running:
            self.stop_bot()
        else:
            self.start_bot()

    def _update_buttons(self, is_running):
        if is_running:
            self.btn_toggle.content = "Стоп"
            self.btn_toggle.icon = ft.Icons.STOP_ROUNDED
            self.btn_toggle.bgcolor = ft.Colors.RED_700
        else:
            self.btn_toggle.content = "Старт"
            self.btn_toggle.icon = ft.Icons.PLAY_ARROW_ROUNDED
            self.btn_toggle.bgcolor = ft.Colors.GREEN_700
        self.btn_toggle.update()

    def show_status(self, e=None):
        if not self.bot:
            self._append_log("⚠️ Бот не запущен")
            return
        status = self.bot.get_open_positions_status()
        self._append_log(f"\n{status}")

    def show_stats(self, e=None):
        if not self.bot:
            self._append_log("⚠️ Бот не запущен")
            return
        stats_text = self.bot.get_stats_text()
        self._append_log(f"\n{'=' * 50}\n{stats_text}\n{'=' * 50}")

    def show_report(self, e=None):
        if not self.bot:
            self._append_log("⚠️ Бот не запущен")
            return
        report = self.bot.get_report()
        self._append_log(f"\n{report}")

    def close_all(self, e=None):
        if not self.bot:
            self._append_log("⚠️ Бот не запущен")
            return
        result = self.bot.close_all_positions()
        self._append_log(f"\n{result}")

    def open_settings(self, e=None):
        config = load_config()

        dd_account = ft.Dropdown(
            label="Тип аккаунта",
            value=config['ACCOUNT_TYPE'],
            options=[
                ft.dropdown.Option("demo", text="🧪 Demo (тестовый)"),
                ft.dropdown.Option("real", text="💰 Real (реальный)"),
            ],
            width=400
        )

        dd_order_type = ft.Dropdown(
            label="Тип расчёта размера позиции",
            value=config['ORDER_TYPE'],
            options=[
                ft.dropdown.Option("percentage", text="📈 Процент от баланса"),
                ft.dropdown.Option("fixed", text="💵 Фиксированная сумма (USDT)"),
            ],
            width=400
        )

        dd_mode = ft.Dropdown(
            label="Режим работы",
            value=config['TRADING_MODE'],
            options=[
                ft.dropdown.Option("signals_only", text="📡 Только сигналы"),
                ft.dropdown.Option("live", text="💰 Live торговля"),
            ],
            width=400
        )

        tf_mr_symbols = ft.TextField(label="📈 Mean Reversion: Пары", value=", ".join(config['MR_SYMBOLS']), width=400, hint_text="Например: BTC_USDT, ETH_USDT")
        tf_mr_timeframes = ft.TextField(label="⏰ Mean Reversion: Таймфреймы", value=", ".join(config['MR_TIMEFRAMES']), width=400, hint_text="Например: 15m, 30m")
        tf_mr_entry_z = ft.TextField(label="🎯 Z-Score для входа", value=str(config['MR_ENTRY_ZSCORE']), width=200, hint_text="Например: 1.5")
        tf_mr_tp_z = ft.TextField(label="✅ Z-Score для выхода (TP)", value=str(config['MR_TAKE_PROFIT_ZSCORE']), width=200, hint_text="Например: 0.5")
        tf_mr_max_positions = ft.TextField(label="🔢 MR: Макс. позиций", value=str(config['MR_MAX_POSITIONS']), width=200, hint_text="Например: 2")
        tf_mr_cooldown = ft.TextField(label="⏳ MR: Кулдаун (сек)", value=str(config['MR_COOLDOWN_SECONDS']), width=200, hint_text="Например: 120")

        tf_as_symbols = ft.TextField(label="⚡ Scalping: Пары", value=", ".join(config['AS_SYMBOLS']), width=400, hint_text="Например: BTC_USDT, ETH_USDT, SOL_USDT")
        tf_as_timeframes = ft.TextField(label="⏰ Scalping: Таймфреймы", value=", ".join(config['AS_TIMEFRAMES']), width=400, hint_text="Например: 5m, 15m")
        tf_as_tp = ft.TextField(label="🎯 Take Profit %", value=str(config['AS_TAKE_PROFIT_PCT']), width=200, hint_text="Например: 0.6")
        tf_as_sl = ft.TextField(label="🛑 Stop Loss %", value=str(config['AS_STOP_LOSS_PCT']), width=200, hint_text="Например: 0.3")
        tf_as_rsi_os = ft.TextField(label="📉 RSI перепроданности", value=str(config['AS_RSI_OVERSOLD']), width=200, hint_text="Например: 35")
        tf_as_rsi_ob = ft.TextField(label="📈 RSI перекупленности", value=str(config['AS_RSI_OVERBOUGHT']), width=200, hint_text="Например: 65")
        tf_as_max_positions = ft.TextField(label="🔢 AS: Макс. позиций", value=str(config['AS_MAX_POSITIONS']), width=200, hint_text="Например: 3")
        tf_as_cooldown = ft.TextField(label="⏳ AS: Кулдаун (сек)", value=str(config['AS_COOLDOWN_SECONDS']), width=200, hint_text="Например: 60")

        # ✅ Checkbox для Smart Trailing Stop
        cb_smart_trailing = ft.Checkbox(
            label="✅ Smart Trailing Stop (включено)",
            value=config['AS_USE_SMART_TRAILING'],
            width=400
        )
        tf_trailing_start = ft.TextField(label="🚀 Активация трейлинга %", value=str(config['AS_TRAILING_START_PCT']), width=200, hint_text="Например: 0.3")
        tf_trailing_min = ft.TextField(label="📏 Мин. отступ трейлинга %", value=str(config['AS_TRAILING_MIN_DISTANCE']), width=200, hint_text="Например: 0.2")
        tf_trailing_atr = ft.TextField(label="📊 ATR множитель", value=str(config['AS_TRAILING_ATR_MULT']), width=200, hint_text="Например: 1.5")
        tf_trailing_step = ft.TextField(label="📈 Шаг подтяжки %", value=str(config['AS_TRAILING_STEP_PCT']), width=200, hint_text="Например: 0.1")

        # ✅ НОВОЕ: Режим закрытия при триггере трейлинга
        dd_trailing_close_mode = ft.Dropdown(
            label="🎯 Режим закрытия при триггере",
            value=config.get('TRAILING_CLOSE_MODE', 'trailing'),
            options=[
                ft.dropdown.Option("trailing", text="📈 Трейлинг-стоп (перемещать стоп)"),
                ft.dropdown.Option("tp", text="✅ Тейк-профит (закрыть позицию)"),
            ],
            width=400,
            hint_text="Что делать когда цена достигает уровня"
        )

        tf_trailing_close_percent = ft.TextField(
            label="💵 Процент закрытия позиции",
            value=str(config.get('TRAILING_CLOSE_PERCENT', '100')),
            width=200,
            hint_text="100 = полное, 50 = половина"
        )

        tf_leverage = ft.TextField(label="📊 Кредитное плечо", value=str(config['LEVERAGE']), width=200, hint_text="Например: 10")
        tf_qty_percentage = ft.TextField(label="% от баланса в сделку", value=str(config['QTY_PERCENTAGE']), width=200, hint_text="Например: 5")
        tf_fixed_volume = ft.TextField(label="💵 Фиксированная сумма (USDT)", value=str(config['FIXED_VOLUME']), width=200, hint_text="Например: 100")

        tf_daily_loss = ft.TextField(
            label="🛑 Дневной лимит убытков (сделок)",
            value=str(config['DAILY_LOSS_LIMIT']),
            width=200,
            hint_text="Например: 3"
        )
        tf_max_positions = ft.TextField(
            label="🔢 Макс. открытых позиций (общий)",
            value=str(config['MAX_OPEN_POSITIONS']),
            width=200,
            hint_text="Например: 5"
        )
        tf_scan_interval = ft.TextField(
            label="🔄 Интервал сканирования (сек)",
            value=str(config['SCAN_INTERVAL']),
            width=200,
            hint_text="Например: 15"
        )
        tf_trailing_interval = ft.TextField(
            label="⏱️ Интервал трейлинга (сек)",
            value=str(config['TRAILING_INTERVAL']),
            width=200,
            hint_text="Например: 3"
        )

        tf_initial_sl = ft.TextField(label="🛑 Начальный стоп %", value=str(config['INITIAL_STOP_PERCENTAGE']), width=200, hint_text="Например: 3.0")
        tf_trigger_profit = ft.TextField(label="🎯 Профиль прибыли для трейлинга %", value=str(config['TRIGGER_PROFIT_PERCENTAGE']), width=200, hint_text="Например: 5.0")
        tf_trailing_pct = ft.TextField(label="📈 Трейлинг %", value=str(config['TRAILING_PERCENTAGE']), width=200, hint_text="Например: 1.0")
        tf_profit_lock = ft.TextField(label="🔒 Фиксация прибыли %", value=str(config['PROFIT_LOCK_PERCENTAGE']), width=200, hint_text="Например: 2.0")

        cb_averaging = ft.Checkbox(
            label="✅ Усреднение позиций (DCA)",
            value=config.get('AVERAGING_ENABLED', False),
            width=400
        )
        tf_averaging_pause = ft.TextField(
            label="⏳ Пауза между усреднениями (сек)",
            value=str(config.get('AVERAGING_PAUSE', 300)),
            width=200,
            hint_text="Например: 300 (5 мин)"
        )

        cb_auto_adjust = ft.Checkbox(
            label="🤖 Авто-адаптация под рынок",
            value=config['AS_AUTO_ADJUST'],
            width=400
        )
        tf_adaptation_window = ft.TextField(
            label="📊 Окно адаптации (свечей)",
            value=str(config['AS_ADAPTATION_WINDOW']),
            width=200,
            hint_text="Например: 50"
        )
        tf_min_win_rate = ft.TextField(
            label="📈 Мин. Win Rate",
            value=str(config['AS_MIN_WIN_RATE']),
            width=200,
            hint_text="Например: 0.50"
        )
        tf_max_drawdown = ft.TextField(
            label="📉 Макс. Drawdown %",
            value=str(config['AS_MAX_DRAWDOWN_PCT']),
            width=200,
            hint_text="Например: 5.0"
        )

        tf_tg_token = ft.TextField(
            label="📱 Telegram Bot Token", value=config['TELEGRAM_TOKEN'],
            width=400, password=True, can_reveal_password=True,
            hint_text="Токен от @BotFather"
        )
        tf_tg_chat = ft.TextField(label="👥 Telegram Chat ID", value=config['TELEGRAM_CHAT_ID'], width=400, hint_text="ID чата для уведомлений")

        tf_demo_api_key = ft.TextField(
            label="🧪 Demo API Key", value=config['DEMO_API_KEY'],
            width=400, password=True, can_reveal_password=True
        )
        tf_demo_api_secret = ft.TextField(
            label="🧪 Demo API Secret", value=config['DEMO_API_SECRET'],
            width=400, password=True, can_reveal_password=True
        )
        tf_real_api_key = ft.TextField(
            label="💰 Real API Key", value=config['REAL_API_KEY'],
            width=400, password=True, can_reveal_password=True
        )
        tf_real_api_secret = ft.TextField(
            label="💰 Real API Secret", value=config['REAL_API_SECRET'],
            width=400, password=True, can_reveal_password=True
        )

        demo_section = ft.Column([
            ft.Text("🧪 Demo API ключи", weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN),
            ft.Text("Используются для тестирования без реальных денег", size=12, color=ft.Colors.GREY_400),
            tf_demo_api_key,
            tf_demo_api_secret,
        ], visible=(config['ACCOUNT_TYPE'] == 'demo'), spacing=8)

        real_section = ft.Column([
            ft.Text("💰 Real API ключи", weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE),
            ft.Text("⚠️ ВНИМАНИЕ: Реальные деньги! Будьте осторожны!", size=12, color=ft.Colors.RED_400),
            tf_real_api_key,
            tf_real_api_secret,
        ], visible=(config['ACCOUNT_TYPE'] == 'real'), spacing=8)

        def save_settings(ev):
            try:
                lines = [
                    "# skalpMat Settings",
                    "",
                    "# Telegram",
                    f"TELEGRAM_TOKEN={tf_tg_token.value}",
                    f"TELEGRAM_CHAT_ID={tf_tg_chat.value}",
                    "",
                    "# Gate.io DEMO",
                    f"DEMO_API_KEY={tf_demo_api_key.value}",
                    f"DEMO_API_SECRET={tf_demo_api_secret.value}",
                    "",
                    "# Gate.io REAL",
                    f"REAL_API_KEY={tf_real_api_key.value}",
                    f"REAL_API_SECRET={tf_real_api_secret.value}",
                    "",
                    f"ACCOUNT_TYPE={dd_account.value}",
                    f"TRADING_MODE={dd_mode.value}",
                    "",
                    f"STRATEGY_MEAN_REVERSION=True",
                    f"STRATEGY_ADAPTIVE_SCALPING=True",
                    "",
                    f"MR_SYMBOLS={tf_mr_symbols.value}",
                    f"MR_TIMEFRAMES={tf_mr_timeframes.value}",
                    f"MR_ENTRY_ZSCORE={tf_mr_entry_z.value}",
                    f"MR_TAKE_PROFIT_ZSCORE={tf_mr_tp_z.value}",
                    f"MR_LOOKBACK_WINDOW={config['MR_LOOKBACK_WINDOW']}",
                    f"MR_HURST_THRESHOLD={config['MR_HURST_THRESHOLD']}",
                    f"MR_POSITION_SIZE_PCT={config['MR_POSITION_SIZE_PCT']}",
                    f"MR_STOP_LOSS_PCT={config['MR_STOP_LOSS_PCT']}",
                    f"MR_MAX_POSITIONS={tf_mr_max_positions.value}",
                    f"MR_COOLDOWN_SECONDS={tf_mr_cooldown.value}",
                    "",
                    f"AS_SYMBOLS={tf_as_symbols.value}",
                    f"AS_TIMEFRAMES={tf_as_timeframes.value}",
                    f"AS_TAKE_PROFIT_PCT={tf_as_tp.value}",
                    f"AS_STOP_LOSS_PCT={tf_as_sl.value}",
                    f"AS_RSI_OVERSOLD={tf_as_rsi_os.value}",
                    f"AS_RSI_OVERBOUGHT={tf_as_rsi_ob.value}",
                    f"AS_BB_STD={config['AS_BB_STD']}",
                    f"AS_VOLUME_THRESHOLD={config['AS_VOLUME_THRESHOLD']}",
                    f"AS_MAX_POSITIONS={tf_as_max_positions.value}",
                    f"AS_COOLDOWN_SECONDS={tf_as_cooldown.value}",
                    "",
                    f"AS_USE_SMART_TRAILING={'True' if cb_smart_trailing.value else 'False'}",
                    f"AS_TRAILING_START_PCT={tf_trailing_start.value}",
                    f"AS_TRAILING_MIN_DISTANCE={tf_trailing_min.value}",
                    f"AS_TRAILING_ATR_MULT={tf_trailing_atr.value}",
                    f"AS_TRAILING_STEP_PCT={tf_trailing_step.value}",
                    "",
                    f"TRAILING_CLOSE_MODE={dd_trailing_close_mode.value}",
                    f"TRAILING_CLOSE_PERCENT={tf_trailing_close_percent.value}",
                    "",
                    f"AS_AUTO_ADJUST={'True' if cb_auto_adjust.value else 'False'}",
                    f"AS_ADAPTATION_WINDOW={tf_adaptation_window.value}",
                    f"AS_MIN_WIN_RATE={tf_min_win_rate.value}",
                    f"AS_MAX_DRAWDOWN_PCT={tf_max_drawdown.value}",
                    "",
                    f"LEVERAGE={tf_leverage.value}",
                    f"MARGIN_MODE={config['MARGIN_MODE']}",
                    f"ORDER_TYPE={dd_order_type.value}",
                    f"QTY_PERCENTAGE={tf_qty_percentage.value}",
                    f"FIXED_VOLUME={tf_fixed_volume.value}",
                    f"TRADING_FEE={config['TRADING_FEE']}",
                    "",
                    f"DAILY_LOSS_LIMIT={tf_daily_loss.value}",
                    f"MAX_OPEN_POSITIONS={tf_max_positions.value}",
                    f"SCAN_INTERVAL={tf_scan_interval.value}",
                    f"TRAILING_INTERVAL={tf_trailing_interval.value}",
                    "",
                    f"INITIAL_STOP_PERCENTAGE={tf_initial_sl.value}",
                    f"TRIGGER_PROFIT_PERCENTAGE={tf_trigger_profit.value}",
                    f"PROFIT_LOCK_PERCENTAGE={tf_profit_lock.value}",
                    f"TRAILING_PERCENTAGE={tf_trailing_pct.value}",
                    "",
                    f"AVERAGING_ENABLED={'True' if cb_averaging.value else 'False'}",
                    f"AVERAGING_PAUSE={tf_averaging_pause.value}",
                    "",
                    f"USE_TP=True",
                    f"USE_SL=True",
                    f"TP_CLOSE_PERCENT={config['TP_CLOSE_PERCENT']}",
                ]

                with open(ENV_PATH, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(lines))

                try:
                    set_tp_config(
                        '1h',
                        float(tf_initial_sl.value),
                        float(tf_trigger_profit.value),
                        float(tf_trailing_pct.value),
                        float(tf_profit_lock.value)
                    )
                except Exception as e:
                    logger.error(f"Ошибка сохранения TP/SL: {e}")

                self._append_log("✅ Настройки сохранены. Перезапустите бота.")
                self.page.pop_dialog()
            except Exception as ex:
                self._append_log(f"❌ Ошибка сохранения: {ex}")

        def close_settings(ev):
            self.page.pop_dialog()

        dialog = ft.AlertDialog(
            title=ft.Text("⚙️ Настройки SKALPMAT V7", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN),
            content=ft.Container(
                content=ft.Column([
                    ft.Text("🔑 Telegram уведомления", weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN),
                    tf_tg_token,
                    tf_tg_chat,
                    ft.Divider(),
                    ft.Text("💼 Gate.io API", weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN),
                    dd_account,
                    ft.Divider(),
                    demo_section,
                    real_section,
                    ft.Divider(),
                    ft.Text("🎮 Режим работы", weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN),
                    dd_mode,
                    ft.Divider(),
                    ft.Text("💰 Размер позиции", weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN),
                    dd_order_type,
                    ft.Row([tf_leverage, tf_qty_percentage, tf_fixed_volume], spacing=10, wrap=True),
                    ft.Divider(),
                    ft.Text("📈 Mean Reversion стратегия", weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN),
                    ft.Text("Стратегия возврата к среднему (долгосрочная)", size=11, color=ft.Colors.GREY_400),
                    tf_mr_symbols,
                    tf_mr_timeframes,
                    ft.Row([tf_mr_entry_z, tf_mr_tp_z], spacing=10),
                    ft.Row([tf_mr_max_positions, tf_mr_cooldown], spacing=10),
                    ft.Divider(),
                    ft.Text("⚡ Adaptive Scalping стратегия", weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN),
                    ft.Text("Быстрая торговля с адаптацией (краткосрочная)", size=11, color=ft.Colors.GREY_400),
                    tf_as_symbols,
                    tf_as_timeframes,
                    ft.Row([tf_as_tp, tf_as_sl], spacing=10),
                    ft.Row([tf_as_rsi_os, tf_as_rsi_ob], spacing=10),
                    ft.Row([tf_as_max_positions, tf_as_cooldown], spacing=10),
                    ft.Divider(),
                    ft.Text("🎯 Smart Trailing Stop", weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN),
                    ft.Text("Автоматическое перемещение стоп-лосса", size=11, color=ft.Colors.GREY_400),
                    cb_smart_trailing,
                    ft.Row([tf_trailing_start, tf_trailing_min], spacing=10),
                    ft.Row([tf_trailing_atr, tf_trailing_step], spacing=10),
                    ft.Divider(),
                    ft.Text("⚙️ Режим закрытия при триггере", weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE),
                    ft.Text("Что делать когда цена достигает уровня трейлинга", size=11, color=ft.Colors.GREY_400),
                    dd_trailing_close_mode,
                    ft.Row([tf_trailing_close_percent], spacing=10),
                    ft.Text("💡 Пример: 50% закроется сразу, 50% останется с трейлинг-стопом",
                            size=10, color=ft.Colors.GREEN_400, italic=True),
                    ft.Divider(),
                    ft.Text("🛡️ Защита и лимиты", weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE),
                    ft.Row([tf_daily_loss, tf_max_positions], spacing=10),
                    ft.Row([tf_scan_interval, tf_trailing_interval], spacing=10),
                    ft.Divider(),
                    ft.Text("📊 TP/SL (PnL-based)", weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN),
                    ft.Row([tf_initial_sl, tf_trigger_profit], spacing=10),
                    ft.Row([tf_trailing_pct, tf_profit_lock], spacing=10),
                    ft.Divider(),
                    ft.Text("🔄 Усреднение позиций", weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN),
                    cb_averaging,
                    tf_averaging_pause,
                    ft.Divider(),
                    ft.Text("🤖 Self-optimization", weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN),
                    ft.Text("Автоматическая подстройка параметров", size=11, color=ft.Colors.GREY_400),
                    cb_auto_adjust,
                    ft.Row([tf_adaptation_window, tf_min_win_rate], spacing=10),
                    tf_max_drawdown,
                    ft.Divider(),
                    ft.Text("⚙️ Общие", weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN),
                ], scroll=ft.ScrollMode.AUTO, spacing=10),
                width=750,
                height=750
            ),
            actions=[
                ft.Button("💾 Сохранить настройки", on_click=save_settings, bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE, icon=ft.Icons.SAVE),
                ft.TextButton("❌ Отмена", on_click=close_settings),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        def on_account_change(ev):
            if dd_account.value == 'demo':
                demo_section.visible = True
                real_section.visible = False
            else:
                demo_section.visible = False
                real_section.visible = True
            dialog.update()

        dd_account.on_change = on_account_change
        self.page.show_dialog(dialog)

    def _build_main_view(self):
        self.page.title = "skalpMat V7"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.bgcolor = ft.Colors.BLACK
        self.page.padding = 0
        self.page.window.width = 850
        self.page.window.height = 680

        if ICON_PATH.exists():
            self.page.window.icon = str(ICON_PATH)

        self.log_view = ft.ListView(
            expand=True,
            spacing=1,
            auto_scroll=True,
            controls=[
                ft.Text("=" * 60, size=11, font_family="Consolas", color=ft.Colors.CYAN),
                ft.Text("  🚀 SKALPMAT V7 — Adaptive Trading System 🚀",
                        size=12, font_family="Consolas", color=ft.Colors.CYAN,
                        weight=ft.FontWeight.BOLD),
                ft.Text("  📈 Mean Reversion + ⚡ Adaptive Scalping",
                        size=11, font_family="Consolas", color=ft.Colors.YELLOW),
                ft.Text("  🎯 Smart Trailing + Self-optimization + Market Regime",
                        size=11, font_family="Consolas", color=ft.Colors.YELLOW),
                ft.Text("  ✅ AUTO-RESTART + ANTI-SPAM + TRAILING STOP",
                        size=11, font_family="Consolas", color=ft.Colors.GREEN),
                ft.Text("=" * 60, size=11, font_family="Consolas", color=ft.Colors.CYAN),
            ]
        )

        self.status_text = ft.Text("  ⏸️ Готов к работе.", size=12, font_family="Consolas", color=ft.Colors.YELLOW)
        status_bar = ft.Container(
            content=ft.Row([self.status_text], spacing=8, alignment=ft.MainAxisAlignment.START),
            bgcolor=ft.Colors.BLACK,
            padding=ft.Padding(10, 6, 10, 6),
            border=ft.Border(top=ft.BorderSide(1, ft.Colors.CYAN)),
        )

        # ✅ КАРУСЕЛЬ ОТКРЫТЫХ ПОЗИЦИЙ С ТЕКУЩЕЙ ЦЕНОЙ
        self.positions_carousel_text = ft.Text(
            "📊 Нет открытых позиций",
            size=11,
            font_family="Consolas",
            color=ft.Colors.YELLOW,
            weight=ft.FontWeight.NORMAL
        )

        positions_carousel_bar = ft.Container(
            content=ft.Row([self.positions_carousel_text], spacing=8, alignment=ft.MainAxisAlignment.CENTER),
            bgcolor=ft.Colors.GREY_900,
            padding=ft.Padding(10, 6, 10, 6),
            border=ft.Border(
                top=ft.BorderSide(1, ft.Colors.GREY_700),
                bottom=ft.BorderSide(1, ft.Colors.GREY_700)
            ),
        )

        self.btn_toggle = ft.Button(
            "Старт",
            icon=ft.Icons.PLAY_ARROW_ROUNDED,
            on_click=self.toggle_bot,
            bgcolor=ft.Colors.GREEN_700,
            color=ft.Colors.WHITE,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=12),
                padding=ft.Padding(24, 14, 24, 14)
            )
        )

        btn_status = ft.Button(
            "Позиции",
            icon=ft.Icons.INFO_OUTLINE,
            on_click=self.show_status,
            bgcolor=ft.Colors.CYAN_700,
            color=ft.Colors.WHITE,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=12),
                padding=ft.Padding(24, 14, 24, 14)
            )
        )

        btn_stats = ft.Button(
            "Статистика",
            icon=ft.Icons.ANALYTICS,
            on_click=self.show_stats,
            bgcolor=ft.Colors.PURPLE_700,
            color=ft.Colors.WHITE,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=12),
                padding=ft.Padding(24, 14, 24, 14)
            )
        )

        btn_report = ft.Button(
            "Отчёт",
            icon=ft.Icons.ASSIGNMENT,
            on_click=self.show_report,
            bgcolor=ft.Colors.BLUE_700,
            color=ft.Colors.WHITE,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=12),
                padding=ft.Padding(24, 14, 24, 14)
            )
        )

        btn_close_all = ft.Button(
            "Закрыть всё",
            icon=ft.Icons.CANCEL,
            on_click=self.close_all,
            bgcolor=ft.Colors.RED_900,
            color=ft.Colors.WHITE,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=12),
                padding=ft.Padding(24, 14, 24, 14)
            )
        )

        # ✅ КНОПКА БЭКТЕСТА
        btn_backtest = ft.Button(
            "Бэктест",
            icon=ft.Icons.SCIENCE,
            on_click=self.run_backtest,
            bgcolor=ft.Colors.ORANGE_700,
            color=ft.Colors.WHITE,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=12),
                padding=ft.Padding(24, 14, 24, 14)
            )
        )

        btn_settings = ft.Button(
            "Настройки",
            icon=ft.Icons.SETTINGS_ROUNDED,
            on_click=self.open_settings,
            bgcolor=ft.Colors.BLUE_800,
            color=ft.Colors.WHITE,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=12),
                padding=ft.Padding(24, 14, 24, 14)
            )
        )

        btn_exit = ft.Button(
            "Выход",
            icon=ft.Icons.CLOSE_ROUNDED,
            on_click=lambda e: sys.exit(0),
            bgcolor=ft.Colors.GREY_800,
            color=ft.Colors.WHITE,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=12),
                padding=ft.Padding(24, 14, 24, 14)
            )
        )

        self.page.add(ft.Column([
            ft.Container(
                content=self.log_view,
                bgcolor=ft.Colors.BLACK,
                expand=True,
                padding=ft.Padding(10, 8, 10, 4)
            ),
            status_bar,
            positions_carousel_bar,  # ✅ КАРУСЕЛЬ ПОЗИЦИЙ
            ft.Container(
                content=ft.Row(
                    [self.btn_toggle, btn_status, btn_stats, btn_report, btn_close_all, btn_backtest, btn_settings, btn_exit],
                    alignment=ft.MainAxisAlignment.SPACE_EVENLY,
                    wrap=True
                ),
                padding=ft.Padding(16, 12, 16, 12)
            ),
        ], expand=True, spacing=0))

def main(page: ft.Page):
    app = SynergyApp(page)

if __name__ == "__main__":
    ft.run(main)
