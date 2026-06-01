
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
    0.01,
    0.01,
    0.02,
    0.02,
    0.02,
    0.03,
    0.03,
    0.04
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


# =========================================================
# GRID ENTRY ENGINE
# =========================================================

def grid_engine(df):
    """✅ FIXED: Proper lot index management with position limits and restart safety"""
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

    # First entry with strong filters
    if len(sell_positions) == 0:
        # Entry cooldown check
        if entry_times:
            last_entry = entry_times[-1]
            if time.time() - last_entry < MIN_ENTRY_DELAY:
                return
        
        # RSI filter - avoid oversold
        rsi_ok = df['rsi'].iloc[-1] > 35
        
        # ATR filter - ensure volatility
        atr_ok = atr_now > latest_atr_mean * 0.8 if latest_atr_mean else True
        
        # Bearish candle confirmation
        bearish_candle = df['close'].iloc[-1] < df['open'].iloc[-1]
        
        # Combined entry signal
        bearish = (
            ema_fast.iloc[-1] < ema_slow.iloc[-1]
            and higher_tf_bearish()
            and rsi_ok
            and atr_ok
            and bearish_candle
        )

        if bearish and spread_ok(max_spread=35):
            # lot_index already reset to 0 at start of function
            if sell(LOT_LADDER[0]):
                entry_times.append(time.time())
            return

    # Grid recovery entries with trend protection
    last_price = last_sell_price()
    
    # Prevent selling into strong uptrends
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

    print("\n[BOT] GoldAlgoBot main loop started")
    log.info("GoldAlgoBot started")

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

            # Fetch market data
            df = get_market_data(200)

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

            # Execute grid engine
            grid_engine(df)

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

