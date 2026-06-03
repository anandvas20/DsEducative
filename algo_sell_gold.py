
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

print("=" * 60)
print("GOLD ALGO BOT (SELL SIDE) - LOADING...")
print("=" * 60)

import os
import sys
import time
import json
import math
import logging
import threading
import traceback
from queue import Queue
from collections import deque
from functools import wraps
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from logging.handlers import RotatingFileHandler

print("[IMPORT] Standard libraries loaded successfully")

# Try importing required packages with error handling
try:
    import MetaTrader5 as mt5
    print("[IMPORT] MetaTrader5 loaded successfully")
except ImportError as e:
    print(f"\n[ERROR] Failed to import MetaTrader5: {e}")
    print("[FIX] Install with: pip install MetaTrader5")
    sys.exit(1)

try:
    import numpy as np
    print("[IMPORT] NumPy loaded successfully")
except ImportError as e:
    print(f"\n[ERROR] Failed to import numpy: {e}")
    print("[FIX] Install with: pip install numpy")
    sys.exit(1)

try:
    import pandas as pd
    print("[IMPORT] Pandas loaded successfully")
except ImportError as e:
    print(f"\n[ERROR] Failed to import pandas: {e}")
    print("[FIX] Install with: pip install pandas")
    sys.exit(1)

try:
    from google import genai
    print("[IMPORT] Google Gemini AI loaded successfully")
    GEMINI_AVAILABLE = True
except ImportError as e:
    print(f"\n[WARNING] Google Gemini AI not available: {e}")
    print("[INFO] Install with: pip install google-genai")
    print("[INFO] Bot will run without AI assistance")
    GEMINI_AVAILABLE = False

print("[IMPORT] All required packages loaded successfully\n")

# =========================================================
# ADVANCED LOGGING CONFIGURATION
# =========================================================

class ThrottledLogger:
    """
    Advanced logging system with throttling,
    rotation, and structured logging.
    """

    def __init__(self, name="GoldAlgoBot"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)  # Changed from DEBUG to INFO
        self.logger.propagate = False

        # Clear existing handlers
        self.logger.handlers.clear()

        # Throttle tracking
        self._throttle_cache = {}
        self._throttle_lock = threading.Lock()

        # Performance metrics
        self._perf_metrics = {}
        self._perf_lock = threading.Lock()

        self._setup_handlers()

    def _setup_handlers(self):
        """Optimized logging setup - reduced file handlers and backup counts"""
        simple_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%H:%M:%S'
        )

        # Console handler only - minimal logging
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.WARNING)  # Only warnings and errors to console
        console_handler.setFormatter(simple_formatter)
        self.logger.addHandler(console_handler)

        # Single main log file - larger size, fewer backups
        main_file_handler = RotatingFileHandler(
            'gold_grid_bot_sell.log',  # Different log file for SELL bot
            maxBytes=50 * 1024 * 1024,  # 50MB before rotation
            backupCount=2,  # Keep only 2 backups
            encoding='utf-8'
        )
        main_file_handler.setLevel(logging.INFO)
        main_file_handler.setFormatter(simple_formatter)
        self.logger.addHandler(main_file_handler)

    def throttle(self, key, interval=5.0):
        with self._throttle_lock:
            now = time.time()
            last_time = self._throttle_cache.get(key, 0)

            if now - last_time >= interval:
                self._throttle_cache[key] = now
                return True

            return False

    def debug(self, msg, throttle_key=None, throttle_interval=5.0):
        if throttle_key:
            if not self.throttle(throttle_key, throttle_interval):
                return

        self.logger.debug(msg)

    def info(self, msg, throttle_key=None, throttle_interval=5.0):
        if throttle_key:
            if not self.throttle(throttle_key, throttle_interval):
                return

        self.logger.info(msg)

    def warning(self, msg, throttle_key=None, throttle_interval=5.0):
        if throttle_key:
            if not self.throttle(throttle_key, throttle_interval):
                return

        self.logger.warning(msg)

    def error(self, msg, exc_info=False, throttle_key=None, throttle_interval=5.0):
        if throttle_key:
            if not self.throttle(throttle_key, throttle_interval):
                return

        self.logger.error(msg, exc_info=exc_info)

    def critical(self, msg, exc_info=False):
        self.logger.critical(msg, exc_info=exc_info)

    def trade(self, action, **kwargs):
        details = " | ".join([f"{k}={v}" for k, v in kwargs.items()])
        self.logger.info(f"TRADE | {action} | {details}")


# =========================================================
# LOGGER INIT
# =========================================================

log = ThrottledLogger("GoldAlgoBot")


# =========================================================
# PERFORMANCE DECORATOR
# =========================================================

def monitor_performance(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()

        try:
            result = func(*args, **kwargs)
            duration = time.time() - start_time

            log.debug(
                f"PERF | {func.__name__} | {duration:.4f}s",
                throttle_key=f"perf_{func.__name__}",
                throttle_interval=10
            )

            return result

        except Exception as e:
            log.error(
                f"Exception in {func.__name__}: {str(e)}",
                exc_info=True
            )
            raise

    return wrapper


# =========================================================
# GLOBAL CONFIG
# =========================================================

SYMBOL = "XAUUSDm"
MAGIC = 20241202  # Different magic for SELL bot
TIMEFRAME = mt5.TIMEFRAME_M5
HTF_TIMEFRAME = mt5.TIMEFRAME_M15  # Higher timeframe for trend filter

# Indicators - Optimized for SELL side
EMA_FAST = 9
EMA_SLOW = 21
RSI_PERIOD = 14
ATR_PERIOD = 14

# Safer lot ladder - no dangerous jumps
LOT_LADDER = [
    0.01,
    0.02,
    0.04,
    0.06,
    0.08,
    0.12,
    0.14,
    0.15,
    0.16
]
STATE_FILE = "gold_grid_state_sell.json"

# Grid configuration - More conservative for SELL
MIN_GRID_GAP = 3.0  # Wider base gap
LOT_MULTIPLIER = 1.0
MIN_ENTRY_DELAY = 120  # 2 minutes between entries

# Position limits - Safer for SELL side
MAX_SELL_POSITIONS = 9  # Reduced from 8
MAX_TOTAL_POSITIONS = 12 # Reduced from 12
MAX_DAILY_LOSS = 200.0

# =========================================================
# GEMINI AI CONFIGURATION (SELL SIDE)
# =========================================================

GEMINI_API_KEY = "" # Set via environment variable
GEMINI_MODEL = "gemini-2.5-flash" # Full model path for google-genai package
GEMINI_ENABLED = GEMINI_AVAILABLE and len(GEMINI_API_KEY) > 0
GEMINI_CACHE_DURATION = 180  # Cache AI decisions for 180 seconds (3 minutes)

# AI decision cache
ai_decision_cache = {
    'signal': None,
    'timestamp': 0,
    'confidence': 0
}


# =========================================================
# GLOBAL STATE
# =========================================================

lot_index = 0
latest_atr = None
latest_atr_mean = None

positions_cache = []
positions_cache_time = 0
positions_lock = threading.Lock()

trade_queue = Queue()
entry_lock = threading.Lock()
trade_lock = threading.Lock()

speed_cache = deque()
entry_times = []


# =========================================================
# MT5 LOGIN
# =========================================================

# MT5 Credentials
MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"
MT5_LOGIN = 433567390
MT5_PASSWORD = "Trading@123"
MT5_SERVER = "Exness-MT5Trial7"


def load_mt5_credentials():
    """Load MT5 credentials from constants"""
    return MT5_LOGIN, MT5_PASSWORD, MT5_SERVER


@monitor_performance
def init_mt5():
    print(f"\n[INIT] Attempting MT5 connection...")
    print(f"[INIT] Path: {MT5_PATH}")
    print(f"[INIT] Login: {MT5_LOGIN}")
    print(f"[INIT] Server: {MT5_SERVER}")
    
    login, password, server = load_mt5_credentials()

    if not mt5.initialize(
        path=MT5_PATH,
        login=login,
        password=password,
        server=server
    ):
        code, msg = mt5.last_error()
        error_msg = f"MT5 INIT FAILED | Code: {code} | Message: {msg}"
        print(f"\n[ERROR] {error_msg}")
        log.error(error_msg)
        raise RuntimeError(error_msg)

    print(f"[SUCCESS] MT5 initialized successfully")
    log.info("MT5 initialized successfully")
    
    # Print account info
    account_info = mt5.account_info()
    if account_info:
        print(f"[INFO] Account: {account_info.login}")
        print(f"[INFO] Balance: ${account_info.balance:.2f}")
        print(f"[INFO] Equity: ${account_info.equity:.2f}")
        log.info(f"Account {account_info.login} | Balance: ${account_info.balance:.2f}")
    
    # Verify symbol exists
    print(f"\n[VERIFY] Checking symbol: {SYMBOL}")
    symbol_info = mt5.symbol_info(SYMBOL)
    if symbol_info is None:
        print(f"[ERROR] Symbol '{SYMBOL}' not found!")
        print("[INFO] Available GOLD symbols:")
        symbols = mt5.symbols_get()
        gold_symbols = [s.name for s in symbols if 'GOLD' in s.name.upper() or 'XAU' in s.name.upper()]
        for sym in gold_symbols[:10]:  # Show first 10
            print(f"  - {sym}")
        raise RuntimeError(f"Symbol '{SYMBOL}' not available on this broker")
    
    # Enable symbol for trading
    if not symbol_info.visible:
        print(f"[INFO] Enabling symbol {SYMBOL} for trading...")
        if not mt5.symbol_select(SYMBOL, True):
            print(f"[WARNING] Could not enable symbol {SYMBOL}")
    
    print(f"[SUCCESS] Symbol {SYMBOL} verified and ready")
    print(f"[INFO] Bid: {symbol_info.bid:.2f} | Ask: {symbol_info.ask:.2f}")
    print(f"[INFO] Spread: {symbol_info.spread} points\n")


# =========================================================
# POSITION HELPERS
# =========================================================

@monitor_performance
def get_positions(force=False):
    global positions_cache
    global positions_cache_time

    now = time.time()

    with positions_lock:
        if force or (now - positions_cache_time) > 0.15:
            data = mt5.positions_get(symbol=SYMBOL)
            positions_cache = data if data else []
            positions_cache_time = now

        return list(positions_cache)


def floating_pnl():
    """Calculate floating PnL for SELL positions only"""
    return sum(
        position.profit
        for position in get_positions()
        if position.type == mt5.POSITION_TYPE_SELL
    )


def total_sell_volume():
    return sum(
        p.volume
        for p in get_positions(force=True)
        if p.type == mt5.POSITION_TYPE_SELL
    )


# =========================================================
# INDICATORS
# =========================================================

def ATR(df, period=14):
    tr = np.maximum(
        df['high'] - df['low'],
        np.maximum(
            abs(df['high'] - df['close'].shift()),
            abs(df['low'] - df['close'].shift())
        )
    )
    return tr.rolling(period).mean()


def RSI(series, period=14):
    """Calculate RSI indicator"""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def MACD(series, fast=12, slow=26, signal=9):
    """Calculate MACD indicator"""
    ema_fast = series.ewm(span=fast).mean()
    ema_slow = series.ewm(span=slow).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal).mean()
    return macd_line, signal_line


# =========================================================
# GEMINI AI INTEGRATION (SELL SIDE)
# =========================================================

def prepare_market_data_for_ai_sell(df, mtf_data=None, sr_analysis=None):
    """
    Prepare market data in JSON format for Gemini AI (SELL side)
    Sends precomputed indicators instead of raw OHLC
    """
    if df is None or len(df) < 20:
        return None
    
    tick = safe_tick()
    if not tick:
        return None
    
    # Calculate indicators
    current_price = df['close'].iloc[-1]
    rsi = df['rsi'].iloc[-1] if 'rsi' in df.columns else RSI(df['close'], 14).iloc[-1]
    macd_line, macd_signal = MACD(df['close'])
    macd = macd_line.iloc[-1]
    macd_sig = macd_signal.iloc[-1]
    
    ema20 = df['close'].ewm(span=20).mean().iloc[-1]
    ema50 = df['close'].ewm(span=50).mean().iloc[-1]
    ema200 = df['close'].ewm(span=200).mean().iloc[-1] if len(df) >= 200 else ema50
    
    atr = df['atr'].iloc[-1] if 'atr' in df.columns else ATR(df, 14).iloc[-1]
    
    # Trend direction (SELL side - bearish is good)
    trend = "BEARISH" if df['ema_fast'].iloc[-1] < df['ema_slow'].iloc[-1] else "BULLISH"
    
    # Support/Resistance from analysis
    support = sr_analysis['nearest_support'] if sr_analysis and sr_analysis['nearest_support'] else current_price - (atr * 2)
    resistance = sr_analysis['nearest_resistance'] if sr_analysis and sr_analysis['nearest_resistance'] else current_price + (atr * 2)
    
    # Multi-timeframe trend
    mtf_trend = "NEUTRAL"
    if mtf_data:
        m5_bearish = mtf_data.get('M5', {}).get('ema_fast', pd.Series([0])).iloc[-1] < mtf_data.get('M5', {}).get('ema_slow', pd.Series([0])).iloc[-1] if 'M5' in mtf_data else False
        m15_bearish = mtf_data.get('M15', {}).get('ema_fast', pd.Series([0])).iloc[-1] < mtf_data.get('M15', {}).get('ema_slow', pd.Series([0])).iloc[-1] if 'M15' in mtf_data else False
        
        if m5_bearish and m15_bearish:
            mtf_trend = "STRONG_BEARISH"
        elif not m5_bearish and not m15_bearish:
            mtf_trend = "STRONG_BULLISH"
        else:
            mtf_trend = "MIXED"
    
    # Volume (approximate from tick volume)
    volume = int(df['tick_volume'].iloc[-1]) if 'tick_volume' in df.columns else 1000
    
    market_data = {
        "symbol": SYMBOL,
        "timeframe": "M5",
        "price": round(float(current_price), 2),
        "rsi": round(float(rsi), 2),
        "macd": round(float(macd), 4),
        "macd_signal": round(float(macd_sig), 4),
        "ema20": round(float(ema20), 2),
        "ema50": round(float(ema50), 2),
        "ema200": round(float(ema200), 2),
        "atr": round(float(atr), 2),
        "support": round(float(support), 2),
        "resistance": round(float(resistance), 2),
        "volume": volume,
        "trend": trend,
        "mtf_trend": mtf_trend,
        "spread": round(tick.ask - tick.bid, 2),
        "side": "SELL"  # Indicate this is for SELL bot
    }
    
    return market_data


def get_gemini_trading_signal_sell(market_data):
    """
    Get trading signal from Gemini AI for SELL side
    Returns: dict with signal, confidence, entry, stop_loss, take_profit, reason
    """
    global ai_decision_cache
    
    if not GEMINI_ENABLED:
        return None
    
    # Check cache
    now = time.time()
    if ai_decision_cache['signal'] and (now - ai_decision_cache['timestamp']) < GEMINI_CACHE_DURATION:
        log.info(
            f"Using cached AI decision: {ai_decision_cache['signal']} (confidence: {ai_decision_cache['confidence']}%)",
            throttle_key="ai_cache",
            throttle_interval=30
        )
        return ai_decision_cache
    
    try:
        # Prepare prompt for SELL side
        market_data_json = json.dumps(market_data, indent=2)
        
        prompt = f"""
You are a professional gold (XAU/USD) SELL-side trading AI. Analyze the market data and return ONLY valid JSON.

Market Data:
{market_data_json}

Trading Rules for SELL:
1. SELL when:
   - Trend is BEARISH or STRONG_BEARISH
   - RSI between 30-70 (not oversold)
   - MACD < MACD_Signal (bearish crossover)
   - Price near resistance or breaking support (breakdown)
   - Multi-timeframe trend confirms bearish

2. BUY when:
   - Trend is BULLISH or STRONG_BULLISH
   - RSI between 30-70 (not overbought)
   - MACD > MACD_Signal (bullish crossover)
   - Price near support or breaking resistance
   - Multi-timeframe trend confirms bullish

3. HOLD when:
   - Conflicting signals
   - RSI overbought (>70) or oversold (<30)
   - Low confidence
   - Mixed multi-timeframe trend

Return ONLY this JSON format (no markdown, no explanation):
{{
  "signal": "SELL|BUY|HOLD",
  "confidence": 0-100,
  "entry": price_level,
  "stop_loss": price_level,
  "take_profit_1": price_level,
  "take_profit_2": price_level,
  "reason": "brief_explanation"
}}
"""
        
        # Call Gemini API
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )
        
        # Parse response
        response_text = response.text.strip()
        
        # Remove markdown code blocks if present
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()
        
        result = json.loads(response_text)
        
        # Validate result
        required_keys = ["signal", "confidence", "entry", "stop_loss", "take_profit_1", "take_profit_2", "reason"]
        if not all(key in result for key in required_keys):
            log.error(f"Invalid AI response format: {result}")
            return None
        
        # Cache the decision
        ai_decision_cache = {
            'signal': result['signal'],
            'confidence': result['confidence'],
            'entry': result['entry'],
            'stop_loss': result['stop_loss'],
            'take_profit_1': result['take_profit_1'],
            'take_profit_2': result['take_profit_2'],
            'reason': result['reason'],
            'timestamp': now
        }
        
        log.info(
            f"AI Decision (SELL): {result['signal']} | Confidence: {result['confidence']}% | Reason: {result['reason']}",
            throttle_key="ai_decision",
            throttle_interval=10
        )
        
        return result
        
    except json.JSONDecodeError as e:
        log.error(f"Failed to parse AI response as JSON: {e}")
        return None
    except Exception as e:
        error_msg = str(e)
        if "UNAVAILABLE" in error_msg or "503" in error_msg:
            log.warning(f"Gemini API temporarily unavailable (high demand) - will retry later", throttle_key="api_unavailable", throttle_interval=60)
        elif "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg:
            log.warning(f"Gemini API rate limit reached - will use cache", throttle_key="rate_limit", throttle_interval=60)
        else:
            log.error(f"Gemini API error: {e}", exc_info=True)
        return None


def higher_tf_bearish():
    """Check if higher timeframe is bearish"""
    rates = mt5.copy_rates_from_pos(
        SYMBOL,
        HTF_TIMEFRAME,
        0,
        100
    )
    
    if rates is None:
        return False
    
    df = pd.DataFrame(rates)
    df['ema_50'] = df['close'].ewm(span=50).mean()
    
    return df['close'].iloc[-1] < df['ema_50'].iloc[-1]


# =========================================================
# ORDER HELPERS
# =========================================================

def normalize_lot(symbol, lot):
    info = mt5.symbol_info(symbol)

    if not info:
        return lot

    return max(
        info.volume_min,
        round(lot / info.volume_step) * info.volume_step
    )


def send_order_with_retry(request, attempts=3, delay=0.2):
    """Send order with retry logic - FIXED: Better error handling"""
    for i in range(attempts):
        result = mt5.order_send(request)

        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            return result

        if result:
            # ✅ FIXED: Don't retry on certain errors
            if result.retcode == 10019:  # TRADE_RETCODE_NO_MONEY
                log.error(f"Insufficient funds (retcode 10019) - stopping retries")
                return None
            
            if result.retcode == 10018:  # TRADE_RETCODE_MARKET_CLOSED
                log.error(f"Market closed (retcode 10018) - stopping retries")
                return None
            
            log.warning(
                f"ORDER RETRY {i + 1}/{attempts} | retcode={result.retcode}"
            )

        time.sleep(delay)

    log.error("ORDER FAILED AFTER RETRIES")
    return None


def can_afford_trade(lot, order_type):
    """✅ NEW: Check if account has sufficient margin for trade"""
    account_info = mt5.account_info()
    if not account_info:
        return False
    
    # Get required margin
    symbol_info = mt5.symbol_info(SYMBOL)
    if not symbol_info:
        return False
    
    tick = mt5.symbol_info_tick(SYMBOL)
    if not tick:
        return False
    
    price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid
    contract_size = symbol_info.trade_contract_size
    leverage = account_info.leverage if account_info.leverage > 0 else 100
    
    required_margin = (lot * contract_size * price) / leverage
    
    # Add 20% buffer for safety
    required_margin *= 1.2
    
    available = account_info.margin_free
    
    if available < required_margin:
        log.warning(
            f"Insufficient margin: need ${required_margin:.2f}, "
            f"have ${available:.2f}"
        )
        return False
    
    return True


# =========================================================
# SELL FUNCTION
# =========================================================

@monitor_performance
def sell(lot):
    """Execute sell order - FIXED: Added balance check"""
    tick = mt5.symbol_info_tick(SYMBOL)

    if not tick:
        log.warning("SELL SKIPPED — No tick data")
        return False

    normalized_lot = normalize_lot(SYMBOL, lot)

    # ✅ FIXED: Check if we can afford this trade
    if not can_afford_trade(normalized_lot, mt5.ORDER_TYPE_SELL):
        log.warning(f"SELL SKIPPED — Insufficient margin for {normalized_lot} lots")
        return False

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": normalized_lot,
        "type": mt5.ORDER_TYPE_SELL,
        "price": tick.bid,
        "magic": MAGIC,
        "deviation": 50,
        "comment": "Grid Sell",
        "type_filling": mt5.ORDER_FILLING_IOC,
        "type_time": mt5.ORDER_TIME_GTC,
    }

    result = send_order_with_retry(request)

    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        log.trade(
            "SELL_EXECUTED",
            lot=normalized_lot,
            price=tick.bid,
            ticket=result.order
        )
        return True

    return False


# =========================================================
# STATE MANAGEMENT
# =========================================================

def save_state():
    state = {
        "lot_index": lot_index,
    }

    try:
        with open(STATE_FILE, "w") as file:
            json.dump(state, file)

    except Exception as e:
        log.error(f"STATE SAVE FAILED: {e}")


# =========================================================
# MAIN LOOP
# =========================================================

@monitor_performance
def main_loop():
    log.info("Starting GoldAlgoBot...")

    while True:
        try:
            positions = get_positions(force=True)
            pnl = floating_pnl()

            log.info(
                f"Positions={len(positions)} | PnL={pnl:.2f}",
                throttle_key="status",
                throttle_interval=5
            )

            time.sleep(1)

        except KeyboardInterrupt:
            log.warning("Bot stopped by user")
            break

        except Exception as e:
            log.error(f"MAIN LOOP ERROR: {e}", exc_info=True)
            time.sleep(5)


# =========================================================
# ADDITIONAL RECOVERED FUNCTIONS (LATEST VERSION)
# =========================================================

# =========================================================
# SAFE TICK
# =========================================================

def safe_tick():
    try:
        tick = mt5.symbol_info_tick(SYMBOL)

        if tick is None:
            log.warning(
                "Tick data unavailable",
                throttle_key="tick_missing",
                throttle_interval=5
            )
            return None

        return tick

    except Exception as e:
        log.error(f"safe_tick failed: {e}", exc_info=True)
        return None


# =========================================================
# VERIFY POSITION EXISTS
# =========================================================

def verify_position_exists(ticket, retries=10, delay=0.2):
    for _ in range(retries):
        positions = mt5.positions_get(ticket=ticket)

        if positions:
            return True

        time.sleep(delay)

    log.critical(f"POSITION VERIFY FAILED | ticket={ticket}")
    return False


# =========================================================
# SPREAD CHECK
# =========================================================

def spread_ok(max_spread=35):  # Reduced from 60 for safer SELL entries
    tick = safe_tick()

    if not tick:
        return False

    spread = abs(tick.ask - tick.bid)

    if spread > max_spread:
        log.warning(
            f"Spread too high | spread={spread:.2f}",
            throttle_key="spread_high",
            throttle_interval=5
        )
        return False

    return True


# =========================================================
# MISSING FUNCTION STUBS
# =========================================================

def htf_trend_strength(position_count):
    """Calculate higher timeframe trend strength"""
    # Stub implementation - returns neutral trend
    return 0




def last_sell_price():
    """Get the price of the last sell position"""
    positions = get_positions(force=True)
    sell_positions = [
        p for p in positions
        if p.type == mt5.POSITION_TYPE_SELL
    ]
    
    if not sell_positions:
        return 0.0
    
    # Return the most recent sell position price
    return sell_positions[-1].price_open


def dynamic_tp_target(total_lot, position_count):
    """Calculate dynamic take profit target - simplified for quick exits"""
    # Quick exit for single position
    if position_count <= 1:
        return 1.0
    
    # Scale primarily with lot size for deeper positions
    return max(1.0, total_lot * 5)


def mt5_alive():
    """Check if MT5 connection is alive"""
    try:
        return mt5.terminal_info() is not None
    except:
        return False


def equity_circuit_breaker():
    """Check if equity circuit breaker should trigger"""
    # Stub implementation - always returns False
    return False


def equity_trailing_lock():
    """Check if equity trailing lock should trigger"""
    # Stub implementation - always returns False
    return False


def daily_drawdown_guard():
    """Check if daily drawdown limit is reached"""
    # Stub implementation - always returns False
    return False


def adaptive_engine():
    """Adaptive engine for dynamic parameter adjustment"""
    # Stub implementation - does nothing
    pass


def update_market_regime_mode(df, atr, atr_mean):
    """Update market regime mode based on volatility"""
    # Stub implementation - does nothing
    pass


def flat_trap_detector(df):
    """Detect flat/ranging market conditions"""
    # Stub implementation - does nothing
    pass


# =========================================================
# CLOSE ALL POSITIONS
# =========================================================

def close_all():
    """Close all SELL positions only"""
    positions = get_positions(force=True)

    for position in positions:
        try:
            # Only close SELL positions
            if position.type != mt5.POSITION_TYPE_SELL:
                continue

            tick = safe_tick()

            if not tick:
                continue

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": SYMBOL,
                "volume": position.volume,
                "type": mt5.ORDER_TYPE_BUY,  # Close SELL with BUY
                "position": position.ticket,
                "price": tick.ask,
                "deviation": 50,
                "magic": MAGIC,
                "comment": "Close Sell",
                "type_filling": mt5.ORDER_FILLING_IOC,
                "type_time": mt5.ORDER_TIME_GTC,
            }

            result = mt5.order_send(request)

            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                log.trade(
                    "SELL_POSITION_CLOSED",
                    ticket=position.ticket,
                    profit=position.profit
                )

        except Exception as e:
            log.error(f"close_all failed: {e}", exc_info=True)


# =========================================================
# HEDGE POSITION FINDER
# =========================================================



# =========================================================
# MARKET DATA FETCH
# =========================================================

def get_market_data(bars=200):
    """Get M5 market data with indicators"""
    rates = mt5.copy_rates_from_pos(
        SYMBOL,
        TIMEFRAME,
        0,
        bars
    )

    if rates is None or len(rates) == 0:
        return None

    df = pd.DataFrame(rates)

    df['ema_fast'] = df['close'].ewm(span=EMA_FAST).mean()
    df['ema_slow'] = df['close'].ewm(span=EMA_SLOW).mean()
    df['atr'] = ATR(df, ATR_PERIOD)
    df['rsi'] = RSI(df['close'], RSI_PERIOD)

    return df


def get_multi_timeframe_data():
    """
    Get market data from multiple timeframes for better trend analysis (SELL side)
    Returns: dict with M1, M5, M15 dataframes
    """
    mtf_data = {}
    
    # M1 - 200 candles (3.3 hours) - for precise entry timing
    rates_m1 = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M1, 0, 200)
    if rates_m1 is not None and len(rates_m1) > 0:
        df_m1 = pd.DataFrame(rates_m1)
        df_m1['ema_fast'] = df_m1['close'].ewm(span=5).mean()
        df_m1['ema_slow'] = df_m1['close'].ewm(span=9).mean()
        df_m1['atr'] = ATR(df_m1, 14)
        mtf_data['M1'] = df_m1
    
    # M5 - 100 candles (8.3 hours) - for short-term trend
    rates_m5 = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M5, 0, 100)
    if rates_m5 is not None and len(rates_m5) > 0:
        df_m5 = pd.DataFrame(rates_m5)
        df_m5['ema_fast'] = df_m5['close'].ewm(span=9).mean()
        df_m5['ema_slow'] = df_m5['close'].ewm(span=21).mean()
        df_m5['atr'] = ATR(df_m5, 14)
        df_m5['rsi'] = RSI(df_m5['close'], 14)
        mtf_data['M5'] = df_m5
    
    # M15 - 50 candles (12.5 hours) - for medium-term trend
    rates_m15 = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, 50)
    if rates_m15 is not None and len(rates_m15) > 0:
        df_m15 = pd.DataFrame(rates_m15)
        df_m15['ema_fast'] = df_m15['close'].ewm(span=9).mean()
        df_m15['ema_slow'] = df_m15['close'].ewm(span=21).mean()
        df_m15['atr'] = ATR(df_m15, 14)
        mtf_data['M15'] = df_m15
    
    return mtf_data if len(mtf_data) == 3 else None


def detect_support_resistance_sell(df, lookback=50):
    """
    Detect key support and resistance levels for SELL side
    Returns: dict with support/resistance levels and current price position
    """
    if df is None or len(df) < lookback:
        return None
    
    closes = df['close'].iloc[-lookback:].values
    highs = df['high'].iloc[-lookback:].values
    lows = df['low'].iloc[-lookback:].values
    current_price = closes[-1]
    
    # Find swing highs (resistance) - local maxima
    resistance_levels = []
    for i in range(2, len(highs) - 2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and \
           highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            resistance_levels.append(highs[i])
    
    # Find swing lows (support) - local minima
    support_levels = []
    for i in range(2, len(lows) - 2):
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and \
           lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            support_levels.append(lows[i])
    
    # Find nearest resistance above current price
    resistance_above = [r for r in resistance_levels if r > current_price]
    nearest_resistance = min(resistance_above) if resistance_above else None
    
    # Find nearest support below current price
    support_below = [s for s in support_levels if s < current_price]
    nearest_support = max(support_below) if support_below else None
    
    # Calculate distance to nearest levels
    distance_to_resistance = None
    distance_to_support = None
    
    if nearest_resistance:
        distance_to_resistance = nearest_resistance - current_price
    
    if nearest_support:
        distance_to_support = current_price - nearest_support
    
    # ✅ SELL SIDE: Determine if price is near support (within 3 points) - AVOID SELLING HERE
    near_support = distance_to_support is not None and distance_to_support < 3.0
    
    # ✅ SELL SIDE: Determine if price is near resistance (within 3 points) - GOOD FOR SELLING
    near_resistance = distance_to_resistance is not None and distance_to_resistance < 3.0
    
    # ✅ SELL SIDE: Check for breakdown - price recently broke below support
    breakdown_detected = False
    if support_levels:
        recent_support = min([s for s in support_levels if s > current_price], default=None)
        if recent_support and (recent_support - current_price) < 5.0:
            # Price is within 5 points below a recent support = potential breakdown
            breakdown_detected = True
    
    return {
        'current_price': current_price,
        'nearest_resistance': nearest_resistance,
        'nearest_support': nearest_support,
        'distance_to_resistance': distance_to_resistance,
        'distance_to_support': distance_to_support,
        'near_support': near_support,
        'near_resistance': near_resistance,
        'breakdown_detected': breakdown_detected,
        'resistance_levels': resistance_levels,
        'support_levels': support_levels
    }


def analyze_multi_timeframe_trend_sell(mtf_data):
    """
    Analyze trend across multiple timeframes for SELL side with support/resistance
    Returns: dict with trend analysis
    """
    if not mtf_data or len(mtf_data) != 3:
        return None
    
    analysis = {
        'M1_bearish': False,
        'M5_bearish': False,
        'M15_bearish': False,
        'trend_strength': 0,  # 0-3 (number of bearish timeframes)
        'trend_aligned': False,  # All timeframes agree
        'entry_allowed': False,
        'sr_analysis': None,  # Support/Resistance analysis
        'block_reason': None,
        'favorable_entry': False
    }
    
    # Check each timeframe for BEARISH trend
    if 'M1' in mtf_data:
        df_m1 = mtf_data['M1']
        analysis['M1_bearish'] = df_m1['ema_fast'].iloc[-1] < df_m1['ema_slow'].iloc[-1]
    
    if 'M5' in mtf_data:
        df_m5 = mtf_data['M5']
        analysis['M5_bearish'] = df_m5['ema_fast'].iloc[-1] < df_m5['ema_slow'].iloc[-1]
        
        # Detect support/resistance on M5 (more reliable than M1)
        analysis['sr_analysis'] = detect_support_resistance_sell(df_m5, lookback=50)
    
    if 'M15' in mtf_data:
        df_m15 = mtf_data['M15']
        analysis['M15_bearish'] = df_m15['ema_fast'].iloc[-1] < df_m15['ema_slow'].iloc[-1]
    
    # Calculate trend strength (bearish)
    analysis['trend_strength'] = sum([
        analysis['M1_bearish'],
        analysis['M5_bearish'],
        analysis['M15_bearish']
    ])
    
    # All timeframes aligned (bearish)
    analysis['trend_aligned'] = analysis['trend_strength'] == 3
    
    # Entry allowed if at least M5 and M15 are bearish (stronger confirmation)
    analysis['entry_allowed'] = analysis['M5_bearish'] and analysis['M15_bearish']
    
    # ✅ CRITICAL FOR SELL: Block entry if near support (unless breakdown confirmed)
    if analysis['sr_analysis']:
        sr = analysis['sr_analysis']
        
        # Don't sell near support unless it's a confirmed breakdown
        if sr['near_support'] and not sr['breakdown_detected']:
            analysis['entry_allowed'] = False
            analysis['block_reason'] = 'near_support'
        
        # Prefer entries near resistance or after breakdown
        if sr['near_resistance'] or sr['breakdown_detected']:
            analysis['favorable_entry'] = True
        else:
            analysis['favorable_entry'] = False
    
    return analysis


# =========================================================
# GRID ENTRY ENGINE
# =========================================================

def grid_engine(df, mtf_data=None):
    """✅ ENHANCED: Multi-timeframe trend analysis with S/R for SELL side"""
    global lot_index

    if df is None or len(df) < 50:
        return

    positions = get_positions(force=True)

    sell_positions = [
        p for p in positions
        if p.type == mt5.POSITION_TYPE_SELL
    ]

    # ✅ FIX: Always calculate lot_index from actual position count
    # This handles bot restarts when positions already exist
    if len(sell_positions) == 0:
        lot_index = 0
    else:
        # Use position count to determine lot_index (restart-safe)
        lot_index = min(len(sell_positions) - 1, len(LOT_LADDER) - 1)

    # ✅ FIXED: Add position limit checks
    if len(sell_positions) >= MAX_SELL_POSITIONS:
        log.warning(
            f"Max sell positions reached: {len(sell_positions)}",
            throttle_key="max_sell_positions",
            throttle_interval=30
        )
        return
    
    if len(positions) >= MAX_TOTAL_POSITIONS:
        log.warning(
            f"Max total positions reached: {len(positions)}",
            throttle_key="max_total_positions",
            throttle_interval=30
        )
        return

    tick = safe_tick()

    if not tick:
        return

    ema_fast = df['ema_fast']
    ema_slow = df['ema_slow']

    atr_now = df['atr'].iloc[-1]

    # ✅ ENHANCED: Multi-timeframe trend analysis with S/R detection for SELL
    trend_analysis = None
    if mtf_data:
        trend_analysis = analyze_multi_timeframe_trend_sell(mtf_data)
        
        if trend_analysis:
            # Enhanced logging with S/R info
            sr_info = ""
            if trend_analysis['sr_analysis']:
                sr = trend_analysis['sr_analysis']
                res_dist = f"{sr['distance_to_resistance']:.1f}" if sr['distance_to_resistance'] is not None else 'N/A'
                sup_dist = f"{sr['distance_to_support']:.1f}" if sr['distance_to_support'] is not None else 'N/A'
                sr_info = f" | SR: Res={res_dist} Sup={sup_dist} Breakdown={sr['breakdown_detected']}"
            
            log.info(
                f"MTF Trend (SELL) | M1:{trend_analysis['M1_bearish']} | "
                f"M5:{trend_analysis['M5_bearish']} | "
                f"M15:{trend_analysis['M15_bearish']} | "
                f"Strength:{trend_analysis['trend_strength']}/3 | "
                f"Entry:{trend_analysis['entry_allowed']}{sr_info}",
                throttle_key="mtf_trend",
                throttle_interval=10
            )

    # First entry with strong filters
    if len(sell_positions) == 0:
        # Entry cooldown check
        if entry_times:
            last_entry = entry_times[-1]
            if time.time() - last_entry < MIN_ENTRY_DELAY:
                return
        
        # ✅ NEW: Get AI trading signal if enabled (SELL side)
        ai_signal = None
        if GEMINI_ENABLED:
            sr_analysis = trend_analysis['sr_analysis'] if trend_analysis else None
            market_data = prepare_market_data_for_ai_sell(df, mtf_data, sr_analysis)
            
            if market_data:
                ai_signal = get_gemini_trading_signal_sell(market_data)
                
                if ai_signal:
                    # AI overrides if confidence is high
                    if ai_signal['confidence'] >= 70:
                        if ai_signal['signal'] == 'HOLD':
                            log.warning(
                                f"AI BLOCKS SELL entry - Signal: {ai_signal['signal']} | Confidence: {ai_signal['confidence']}% | Reason: {ai_signal['reason']}",
                                throttle_key="ai_block",
                                throttle_interval=30
                            )
                            return
                        elif ai_signal['signal'] == 'BUY':
                            log.warning(
                                f"AI suggests BUY (not SELL) - Confidence: {ai_signal['confidence']}% | Reason: {ai_signal['reason']}",
                                throttle_key="ai_buy_signal",
                                throttle_interval=30
                            )
                            return
                        elif ai_signal['signal'] == 'SELL':
                            log.info(
                                f"✅ AI CONFIRMS SELL - Confidence: {ai_signal['confidence']}% | Reason: {ai_signal['reason']}",
                                throttle_key="ai_confirm",
                                throttle_interval=60
                            )
        
        # ✅ ENHANCED: Use multi-timeframe confirmation with S/R for first entry
        if trend_analysis:
            # Check if entry is blocked by support
            if trend_analysis['block_reason'] == 'near_support':
                log.warning(
                    f"First SELL entry BLOCKED - Price near support (avoid selling at floor)",
                    throttle_key="support_block",
                    throttle_interval=30
                )
                return
            
            # Require M5 and M15 to be bearish for first entry
            if not trend_analysis['entry_allowed']:
                log.warning(
                    f"First SELL entry BLOCKED - MTF not aligned (M5:{trend_analysis['M5_bearish']}, M15:{trend_analysis['M15_bearish']})",
                    throttle_key="mtf_block",
                    throttle_interval=30
                )
                return
            
            # Log favorable entry conditions
            if trend_analysis['favorable_entry']:
                log.info(
                    "✅ FAVORABLE SELL ENTRY - Near resistance or breakdown detected",
                    throttle_key="favorable_entry",
                    throttle_interval=60
                )
        else:
            # Fallback to existing logic if MTF unavailable
            bearish = (
                ema_fast.iloc[-1] < ema_slow.iloc[-1]
                and higher_tf_bearish()
            )
            if not bearish:
                return
        
        # RSI filter - avoid oversold
        rsi_ok = df['rsi'].iloc[-1] > 35
        
        # ATR filter - ensure volatility
        atr_ok = atr_now > latest_atr_mean * 0.8 if latest_atr_mean else True
        
        # Bearish candle confirmation
        bearish_candle = df['close'].iloc[-1] < df['open'].iloc[-1]
        
        if rsi_ok and atr_ok and bearish_candle and spread_ok(max_spread=35):
            # lot_index already reset to 0 at start of function
            if sell(LOT_LADDER[0]):
                entry_times.append(time.time())
            return

    # Grid recovery entries with trend protection
    last_price = last_sell_price()
    
    # Entry cooldown for recovery
    if entry_times:
        last_entry = entry_times[-1]
        if time.time() - last_entry < MIN_ENTRY_DELAY:
            return

    gap = abs(tick.ask - last_price)

    # Improved adaptive grid spacing - wider for SELL safety
    base_gap = 3.0  # Increased from 2.5
    
    # Stronger exponential growth for deeper positions
    position_gap = math.pow(len(sell_positions), 1.4)  # Increased from 1.3
    
    # Higher ATR multiplier for more conservative spacing
    atr_gap = atr_now * 0.7  # Increased from 0.5
    
    dynamic_gap = max(
        base_gap + position_gap,
        atr_gap
    )
    
    log.info(
        f"Grid Gap={dynamic_gap:.2f} | "
        f"Current Gap={gap:.2f} | "
        f"Positions={len(sell_positions)}",
        throttle_key="grid_gap",
        throttle_interval=5
    )

    if gap >= dynamic_gap:
        # ✅ ENHANCED: Multi-timeframe trend protection with S/R for grid entries
        bearish = ema_fast.iloc[-1] < ema_slow.iloc[-1]
        
        # Use MTF analysis if available
        if trend_analysis:
            # ✅ CRITICAL: Also check S/R for grid entries
            if trend_analysis['block_reason'] == 'near_support':
                log.warning(
                    f"Grid SELL entry SKIPPED - Price near support (avoid adding at floor)",
                    throttle_key="grid_support_block",
                    throttle_interval=30
                )
                return
            
            # For grid entries, require at least 2 out of 3 timeframes bearish
            if trend_analysis['trend_strength'] < 2:
                log.warning(
                    f"Grid SELL entry SKIPPED - Weak MTF trend (strength:{trend_analysis['trend_strength']}/3)",
                    throttle_key="weak_mtf_trend",
                    throttle_interval=30
                )
                return
        else:
            # Fallback: Prevent selling into strong uptrends
            strong_uptrend = (
                ema_fast.iloc[-1] > ema_slow.iloc[-1]
                and ema_fast.iloc[-2] > ema_slow.iloc[-2]
            )
            
            if strong_uptrend:
                log.warning(
                    "Strong uptrend detected - skipping recovery entry",
                    throttle_key="uptrend_skip",
                    throttle_interval=30
                )
                return
        
        # ✅ FIX: Use position count for lot index with bounds check
        # This ensures lot_index matches actual positions and prevents IndexError
        lot_index = min(len(sell_positions), len(LOT_LADDER) - 1)
        
        # ✅ FIX: Use lot without multiplier (0.8 makes lots smaller, not larger)
        # If you want larger recovery lots, use LOT_MULTIPLIER > 1.0
        lot = LOT_LADDER[lot_index]

        if sell(lot):
            entry_times.append(time.time())


# =========================================================
# TAKE PROFIT ENGINE
# =========================================================

def tp_engine():
    global lot_index

    positions = get_positions(force=True)

    if not positions:
        return

    pnl = floating_pnl()
    total_lot = total_sell_volume()
    
    # Count SELL positions for grid depth
    sell_positions = [p for p in positions if p.type == mt5.POSITION_TYPE_SELL]
    position_count = len(sell_positions)

    target = dynamic_tp_target(total_lot, position_count)

    if pnl >= target:
        log.warning(
            f"TP HIT | pnl={pnl:.2f} | target={target:.2f}"
        )

        close_all()

        lot_index = 0


# =========================================================
# MAIN BOT LOOP (LATEST)
# =========================================================

def bot_loop():
    global latest_atr
    global latest_atr_mean

    print("\n[BOT] GoldAlgoBot SELL side main loop started with Multi-Timeframe Analysis")
    log.info("GoldAlgoBot SELL side started with MTF (M1, M5, M15)")

    loop_count = 0
    while True:
        try:
            loop_count += 1
            
            # MT5 connection health
            if not mt5_alive():
                print("[WARNING] MT5 connection lost, reconnecting...")
                log.warning("MT5 connection lost")
                time.sleep(2)
                continue

            # Account safety
            if equity_circuit_breaker():
                print("[WARNING] Equity circuit breaker triggered")
                continue

            if equity_trailing_lock():
                print("[WARNING] Equity trailing lock active")
                continue

            if daily_drawdown_guard():
                print("[WARNING] Daily drawdown guard active")
                log.warning("Daily drawdown guard active")
                time.sleep(30)
                continue

            # ✅ ENHANCED: Fetch multi-timeframe market data
            mtf_data = get_multi_timeframe_data()
            
            # Fallback to M5 only if MTF fails
            if mtf_data is None:
                log.warning("MTF data unavailable, using M5 only", throttle_key="mtf_fail", throttle_interval=60)
                df = get_market_data(200)
            else:
                df = mtf_data.get('M5')

            if df is None:
                if loop_count % 10 == 0:  # Print every 10 loops
                    print("[WARNING] Market data unavailable")
                time.sleep(1)
                continue

            latest_atr = df['atr'].iloc[-1]
            latest_atr_mean = df['atr'].rolling(50).mean().iloc[-1]

            # Update adaptive engine
            adaptive_engine()

            # Update regime mode
            update_market_regime_mode(
                df,
                latest_atr,
                latest_atr_mean
            )

            # Flat trap detection
            flat_trap_detector(df)

            # ✅ ENHANCED: Execute grid engine with multi-timeframe data
            grid_engine(df, mtf_data)

            # TP manager
            tp_engine()

            # Status logging
            log.info(
                f"PnL={floating_pnl():.2f} | "
                f"Lot={total_sell_volume():.2f} | "
                f"Positions={len(get_positions())}",
                throttle_key="status_log",
                throttle_interval=5
            )

            time.sleep(1)

        except KeyboardInterrupt:
            print("\n[INFO] Bot stopped manually")
            log.warning("Bot stopped manually")
            break

        except Exception as e:
            print(f"\n[ERROR] BOT LOOP ERROR: {e}")
            log.error(
                f"BOT LOOP ERROR: {e}",
                exc_info=True
            )
            traceback.print_exc()
            time.sleep(5)


# =========================================================
# FINAL ENTRY POINT
# =========================================================

if __name__ == "__main__":
    print("=" * 60)
    print("GOLD ALGO BOT - STARTING")
    print("=" * 60)
    
    try:
        init_mt5()
        bot_loop()

    except KeyboardInterrupt:
        print("\n" + "=" * 60)
        print("BOT STOPPED BY USER")
        print("=" * 60)
        log.warning("Bot stopped by user")
        
    except Exception as e:
        print("\n" + "=" * 60)
        print(f"FATAL ERROR: {e}")
        print("=" * 60)
        log.critical(
            f"FATAL ERROR: {e}",
            exc_info=True
        )
        import traceback
        traceback.print_exc()
        
    finally:
        print("\nShutting down MT5...")
        mt5.shutdown()
        print("MT5 shutdown complete")
        print("=" * 60)

