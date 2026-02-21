import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
import logging
from threading import Thread
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

# =========================================================
# LOGGING
# =========================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("btc_improved_bot.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger()

# =========================================================
# MT5 LOGIN
# =========================================================
MT5_PATH = r"C:\Users\Naveen Kumar Reddy\AppData\Roaming\XM Global MT5\terminal64.exe"
MT5_LOGIN    = 167958826
MT5_PASSWORD = "Panvith@143"
MT5_SERVER   = "XMGlobal-MT5 2"

# =========================================================
# STRATEGY CONFIG - IMPROVED
# =========================================================
SYMBOL = "BTCUSD#"
TIMEFRAME = mt5.TIMEFRAME_M1
MAGIC = 777

# Risk Management
BASE_LOT = 0.01
MARTINGALE_MULTIPLIER = 1.5  # Consistent progression
MAX_LEVELS = 6  # Reduced from 9 to prevent deep drawdowns
MAX_RISK_PCT = 2.0  # Max risk per trade as % of equity
MAX_DAILY_LOSS_PCT = 3.0  # Max daily loss as % of equity
EQUITY_STOP_PCT = 5.0  # Close all if equity drops 5%

# Grid Configuration (CALIBRATED FOR BTC AT $70K - 50 points = $1)
MIN_GRID_GAP = 250   # $5 minimum spacing
MAX_GRID_GAP = 1000  # $20 maximum spacing
ATR_GRID_MULTIPLIER = 1.0  # Conservative for BTC volatility

# Frequency Control
GLOBAL_COOLDOWN_SEC = 90  # 90 seconds between entries
MAX_TRADES_PER_DAY = 30  # Conservative for BTC
CANDLE_BLOCK = True  # Prevent multiple entries per candle

# Filters (STRICTER FOR BTC)
ADX_THRESHOLD = 25  # Minimum ADX for trending market
RSI_MIN = 35
RSI_MAX = 65
AVOID_HIGH_VOLATILITY = True
AVOID_SQUEEZE = True

# State Variables
lot_index = 0
last_entry_time = 0
last_buy_candle_time = 0
basket_active = False
daily_trades = 0
last_trade_date = None
INITIAL_EQUITY = 0

# Performance Tracking
trade_log = {
    'timestamp': [],
    'type': [],
    'level': [],
    'lot': [],
    'price': [],
    'pnl': [],
    'equity': []
}

# =========================================================
# INIT MT5
# =========================================================
def init_mt5():
    global INITIAL_EQUITY
    
    if not mt5.initialize(
        path=MT5_PATH,
        login=MT5_LOGIN,
        password=MT5_PASSWORD,
        server=MT5_SERVER
    ):
        raise RuntimeError(mt5.last_error())

    if not mt5.symbol_select(SYMBOL, True):
        raise RuntimeError("Symbol select failed")

    info = mt5.symbol_info(SYMBOL)
    if info.trade_mode != mt5.SYMBOL_TRADE_MODE_FULL:
        raise RuntimeError("Trading disabled for symbol")

    account = mt5.account_info()
    INITIAL_EQUITY = account.equity

    log.info(
        f"CONNECTED | {SYMBOL} | "
        f"min_lot={info.volume_min} step={info.volume_step} | "
        f"Initial Equity=${INITIAL_EQUITY:.2f}"
    )

# =========================================================
# INDICATORS
# =========================================================
def EMA(series, period):
    return series.ewm(span=period, adjust=False).mean()

def ATR(df, period):
    tr = np.maximum(
        df['high'] - df['low'],
        np.maximum(
            abs(df['high'] - df['close'].shift()),
            abs(df['low'] - df['close'].shift())
        )
    )
    return tr.rolling(period).mean()

def calculate_rsi(series, period=14):
    """Calculate RSI indicator"""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_adx(df, period=14):
    """Calculate ADX to measure trend strength"""
    high = df['high']
    low = df['low']
    close = df['close']
    
    plus_dm = high.diff()
    minus_dm = -low.diff()
    
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0
    
    tr = pd.DataFrame({
        'hl': high - low,
        'hc': abs(high - close.shift()),
        'lc': abs(low - close.shift())
    }).max(axis=1)
    
    atr = tr.rolling(period).mean()
    plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
    
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.rolling(period).mean()
    
    return adx, plus_di, minus_di

# =========================================================
# POSITIONS
# =========================================================
def get_buy_positions():
    return [p for p in mt5.positions_get(symbol=SYMBOL) or [] if p.type == mt5.ORDER_TYPE_BUY]

def total_buy_volume():
    return sum(p.volume for p in get_buy_positions())

def avg_buy_price():
    pos = get_buy_positions()
    return sum(p.volume * p.price_open for p in pos) / sum(p.volume for p in pos) if pos else 0.0

def last_buy_price():
    pos = get_buy_positions()
    return max(pos, key=lambda p: p.time).price_open if pos else 0.0

def floating_buy_pnl():
    return sum(p.profit for p in get_buy_positions())

# =========================================================
# LOT NORMALIZATION
# =========================================================
def normalize_lot(symbol, lot):
    info = mt5.symbol_info(symbol)
    step = info.volume_step
    min_lot = info.volume_min
    max_lot = info.volume_max
    normalized = max(min_lot, round(lot / step) * step)
    return min(normalized, max_lot)

def reset_after_tp():
    global lot_index, last_buy_candle_time, last_entry_time
    lot_index = 0
    last_buy_candle_time = 0
    last_entry_time = 0
    log.info("BOT RESET | lot_index and trackers cleared")

# =========================================================
# DYNAMIC LOT CALCULATION
# =========================================================
def calculate_dynamic_lot(level, atr_current, atr_avg):
    """
    Calculate lot size based on:
    - Level (Martingale progression)
    - ATR (volatility adjustment)
    - Account equity (risk management)
    """
    account = mt5.account_info()
    equity = account.equity
    
    # Martingale multiplier with diminishing returns
    if level == 0:
        multiplier = 1.0
    elif level <= 2:
        multiplier = MARTINGALE_MULTIPLIER ** level
    else:
        # Slower growth after level 2
        multiplier = (MARTINGALE_MULTIPLIER ** 2) * (1.2 ** (level - 2))
    
    # ATR-based adjustment (reduce size in high volatility)
    vol_factor = min(1.0, atr_avg / atr_current) if atr_current > 0 else 1.0
    
    # Calculate lot
    lot = BASE_LOT * multiplier * vol_factor
    
    # Cap based on max risk
    max_risk_dollars = equity * (MAX_RISK_PCT / 100)
    max_lot = max_risk_dollars / (atr_current * 10) if atr_current > 0 else lot
    lot = min(lot, max_lot)
    
    return normalize_lot(SYMBOL, lot)

# =========================================================
# GRID SPACING
# =========================================================
def calculate_grid_spacing(atr_current, level):
    """
    Dynamic grid spacing based on:
    - ATR (volatility)
    - Level (wider spacing for deeper levels)
    """
    base_spacing = atr_current * ATR_GRID_MULTIPLIER
    
    # Increase spacing for deeper levels
    level_multiplier = 1.0 + (level * 0.15)  # +15% per level
    
    spacing = base_spacing * level_multiplier
    
    # Clamp to min/max
    return max(MIN_GRID_GAP, min(spacing, MAX_GRID_GAP))

# =========================================================
# HIGHER TIMEFRAME BIAS
# =========================================================
def get_htf_bias(symbol, timeframe_higher):
    """
    Check higher timeframe trend using EMA alignment
    Returns: 'bullish', 'bearish', 'neutral'
    """
    rates = mt5.copy_rates_from_pos(symbol, timeframe_higher, 0, 100)
    if rates is None or len(rates) < 100:
        return 'neutral'
    
    df = pd.DataFrame(rates)
    
    ema20 = df['close'].ewm(span=20).mean()
    ema50 = df['close'].ewm(span=50).mean()
    ema100 = df['close'].ewm(span=100).mean()
    
    price = df['close'].iloc[-1]
    
    # Strong bullish: price > EMA20 > EMA50 > EMA100
    if price > ema20.iloc[-1] > ema50.iloc[-1] > ema100.iloc[-1]:
        return 'bullish'
    # Strong bearish: price < EMA20 < EMA50 < EMA100
    elif price < ema20.iloc[-1] < ema50.iloc[-1] < ema100.iloc[-1]:
        return 'bearish'
    else:
        return 'neutral'

# =========================================================
# MOMENTUM FILTER
# =========================================================
def momentum_filter(df):
    """
    Returns True if momentum supports entry
    - ADX > 20 (trending, not ranging)
    - RSI between 30-70 (not overbought/oversold)
    - +DI > -DI (bullish momentum)
    """
    if len(df) < 50:
        return False
    
    rsi = calculate_rsi(df['close'], 14)
    adx, plus_di, minus_di = calculate_adx(df, 14)
    
    trending = adx.iloc[-1] > ADX_THRESHOLD
    not_extreme = RSI_MIN < rsi.iloc[-1] < RSI_MAX
    bullish_momentum = plus_di.iloc[-1] > minus_di.iloc[-1]
    
    return trending and not_extreme and bullish_momentum

# =========================================================
# VOLATILITY REGIME
# =========================================================
def get_volatility_regime(df, atr_period=14, lookback=50):
    """
    Classify current volatility as 'low', 'normal', 'high'
    Based on ATR percentile over lookback period
    """
    atr = ATR(df, atr_period)
    if len(atr) < lookback:
        return 'normal'
    
    current_atr = atr.iloc[-1]
    atr_history = atr.iloc[-lookback:]
    percentile = (atr_history < current_atr).sum() / len(atr_history) * 100
    
    if percentile < 30:
        return 'low'
    elif percentile > 70:
        return 'high'
    else:
        return 'normal'

def bollinger_squeeze(df, period=20, std_dev=2):
    """
    Detect Bollinger Band squeeze (low volatility)
    Returns True if bands are contracting
    """
    if len(df) < period + 10:
        return False
    
    sma = df['close'].rolling(period).mean()
    std = df['close'].rolling(period).std()
    
    bb_width = (std * std_dev * 2) / sma
    bb_width_ma = bb_width.rolling(10).mean()
    
    # Squeeze: current width < 80% of average width
    return bb_width.iloc[-1] < bb_width_ma.iloc[-1] * 0.8

# =========================================================
# SESSION FILTER
# =========================================================
def get_trading_session():
    """
    Identify current trading session
    Returns: 'asian', 'london', 'newyork', 'overlap', 'dead'
    """
    utc_hour = datetime.now(timezone.utc).hour
    
    # Asian: 00:00-08:00 UTC
    if 0 <= utc_hour < 8:
        return 'asian'
    # London: 08:00-16:00 UTC
    elif 8 <= utc_hour < 16:
        return 'london'
    # NY: 13:00-21:00 UTC (overlap with London 13:00-16:00)
    elif 13 <= utc_hour < 21:
        if utc_hour < 16:
            return 'overlap'
        return 'newyork'
    # Dead zone: 21:00-00:00 UTC
    else:
        return 'dead'

def session_filter():
    """
    Allow trading only during high-liquidity sessions
    Crypto trades 24/7, but avoid dead zones for better execution
    """
    session = get_trading_session()
    
    # For crypto, we're more lenient, but still avoid dead zone
    if session == 'dead':
        return False
    
    return True

# =========================================================
# FREQUENCY CONTROL
# =========================================================
def check_daily_limit():
    """
    Prevent overtrading by limiting daily trades
    """
    global daily_trades, last_trade_date
    
    today = datetime.now().date()
    
    # Reset counter at midnight
    if last_trade_date != today:
        daily_trades = 0
        last_trade_date = today
    
    if daily_trades >= MAX_TRADES_PER_DAY:
        return False
    
    return True

# =========================================================
# EQUITY PROTECTION
# =========================================================
def check_equity_stop():
    """
    Close all positions if equity drops below threshold
    """
    account = mt5.account_info()
    current_equity = account.equity
    
    dd_pct = ((INITIAL_EQUITY - current_equity) / INITIAL_EQUITY) * 100
    
    if dd_pct >= EQUITY_STOP_PCT:
        log.critical(f"EQUITY STOP HIT | DD={dd_pct:.2f}%")
        close_all_buys()
        return True
    return False

def check_daily_loss():
    """
    Check if daily loss limit exceeded
    """
    account = mt5.account_info()
    current_equity = account.equity
    
    # Get equity at start of day (approximate using initial equity)
    # In production, track this properly
    daily_dd_pct = ((INITIAL_EQUITY - current_equity) / INITIAL_EQUITY) * 100
    
    if daily_dd_pct >= MAX_DAILY_LOSS_PCT:
        log.critical(f"DAILY LOSS LIMIT HIT | Loss={daily_dd_pct:.2f}%")
        return True
    return False

# =========================================================
# ORDERS (EXECUTION SAFE)
# =========================================================
def buy(lot):
    global last_entry_time, last_buy_candle_time, lot_index, daily_trades
    
    lot = normalize_lot(SYMBOL, lot)
    tick = mt5.symbol_info_tick(SYMBOL)

    # Get current candle time
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 1)
    if rates is None or len(rates) == 0:
        log.warning("No candle data, skipping buy")
        return
    current_candle_time = int(rates[-1]['time'])

    # Prevent multiple buys in the same candle
    if CANDLE_BLOCK and current_candle_time == last_buy_candle_time:
        log.info("BUY BLOCKED | already bought in this candle")
        return

    # Send Buy order
    result = mt5.order_send({
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": lot,
        "type": mt5.ORDER_TYPE_BUY,
        "price": tick.ask,
        "magic": MAGIC,
        "deviation": 50,
        "comment": f"Grid L{lot_index}",
        "type_filling": mt5.ORDER_FILLING_IOC,
        "type_time": mt5.ORDER_TIME_GTC
    })

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        last_entry_time = time.time()
        last_buy_candle_time = current_candle_time
        daily_trades += 1
        
        # Log trade
        account = mt5.account_info()
        trade_log['timestamp'].append(datetime.now())
        trade_log['type'].append('entry')
        trade_log['level'].append(lot_index)
        trade_log['lot'].append(lot)
        trade_log['price'].append(tick.ask)
        trade_log['pnl'].append(0)
        trade_log['equity'].append(account.equity)
        
        log.info(f"BUY EXECUTED | lot={lot} level={lot_index} price={tick.ask:.2f}")
    else:
        log.error(f"BUY FAILED | retcode={result.retcode} lot={lot}")

def close_position(p):
    tick = mt5.symbol_info_tick(SYMBOL)
    result = mt5.order_send({
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": p.volume,
        "type": mt5.ORDER_TYPE_SELL,
        "position": p.ticket,
        "price": tick.bid,
        "magic": MAGIC,
        "deviation": 50,
        "comment": "Close",
        "type_filling": mt5.ORDER_FILLING_IOC,
        "type_time": mt5.ORDER_TIME_GTC
    })
    return result

def close_all_buys():
    pos = get_buy_positions()
    if not pos:
        return
    
    total_pnl = sum(p.profit for p in pos)
    log.warning(f"CLOSING ALL BUYS | count={len(pos)} | PnL=${total_pnl:.2f}")
    
    # Log exit
    account = mt5.account_info()
    trade_log['timestamp'].append(datetime.now())
    trade_log['type'].append('exit')
    trade_log['level'].append(len(pos))
    trade_log['lot'].append(sum(p.volume for p in pos))
    trade_log['price'].append(avg_buy_price())
    trade_log['pnl'].append(total_pnl)
    trade_log['equity'].append(account.equity)
    
    with ThreadPoolExecutor(max_workers=min(5, len(pos))) as exe:
        exe.map(close_position, pos)

# =========================================================
# DYNAMIC TAKE PROFIT
# =========================================================
def calculate_dynamic_tp(pos_count, avg_entry, current_price, atr_current, atr_avg):
    """
    Dynamic TP based on:
    - Position count (deeper = higher TP)
    - ATR (volatility-adjusted)
    - Minimum % gain requirement
    
    CALIBRATED FOR BTC AT $70K: 50 points = $1
    """
    # Base TP in POINTS (then convert to dollars)
    if pos_count == 1:
        base_tp_points = 150   # $3
    elif pos_count <= 3:
        base_tp_points = 250   # $5
    elif pos_count <= 5:
        base_tp_points = 400   # $8
    else:
        base_tp_points = 600   # $12
    
    # ATR-based adjustment (higher TP in volatile markets)
    vol_multiplier = atr_current / atr_avg if atr_avg > 0 else 1.0
    tp_points = base_tp_points * vol_multiplier
    
    # Convert points to dollars (50 points = $1 for BTC at $70k)
    tp_target = tp_points / 50.0
    
    # Minimum % gain requirement
    distance_pct = ((current_price - avg_entry) / avg_entry) * 100 if avg_entry > 0 else 0
    min_gain_pct = 0.15 * pos_count  # 0.15% per position (increased from 0.1%)
    
    if distance_pct < min_gain_pct:
        return None  # Don't close yet
    
    return tp_target

# =========================================================
# BASKET WATCHER
# =========================================================
def basket_watcher():
    global lot_index, basket_active
    
    log.info("BASKET WATCHER STARTED")
    
    while True:
        try:
            pos = get_buy_positions()
            pos_count = len(pos)
            
            # No positions → reset basket
            if pos_count == 0:
                if basket_active:
                    log.info("No positions - Resetting basket state")
                basket_active = False
                time.sleep(0.5)
                continue
            
            # Get current data
            rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 50)
            if rates is None or len(rates) < 50:
                time.sleep(0.5)
                continue
            
            df = pd.DataFrame(rates)
            atr = ATR(df, 14)
            atr_current = atr.iloc[-1]
            atr_avg = atr.rolling(50).mean().iloc[-1]
            
            floating_pnl = sum([p.profit for p in pos])
            avg_price = avg_buy_price()
            current_price = df['close'].iloc[-1]
            
            # Calculate dynamic TP
            tp_target = calculate_dynamic_tp(pos_count, avg_price, current_price, atr_current, atr_avg)
            
            log.info(
                f"[BASKET] PnL=${floating_pnl:.2f} | "
                f"Avg={avg_price:.2f} | TP={tp_target:.2f if tp_target else 'N/A'} | "
                f"Pos={pos_count}"
            )
            
            # Close if TP hit
            if tp_target and floating_pnl >= tp_target:
                log.info(
                    f"BASKET TP HIT | "
                    f"PnL=${floating_pnl:.2f} | TP=${tp_target:.2f}"
                )
                close_all_buys()
                reset_after_tp()
                basket_active = False
                time.sleep(1)
                continue
            
            time.sleep(0.2)
            
        except Exception as e:
            log.error(f"BASKET WATCHER ERROR: {e}")
            time.sleep(1)

# =========================================================
# MAIN LOOP
# =========================================================
def run():
    global lot_index
    log.info("BTC IMPROVED GRID BOT STARTED")
    
    while True:
        try:
            # Safety checks
            if check_equity_stop():
                log.critical("EQUITY STOP - Pausing for 5 minutes")
                time.sleep(300)
                continue
            
            if check_daily_loss():
                log.critical("DAILY LOSS LIMIT - Pausing for 5 minutes")
                time.sleep(300)
                continue
            
            # Load data
            rates_1m = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 120)
            if rates_1m is None or len(rates_1m) < 100:
                time.sleep(1)
                continue
            
            df = pd.DataFrame(rates_1m)
            
            # Calculate indicators
            atr = ATR(df, 14)
            atr_current = atr.iloc[-1]
            atr_avg = atr.rolling(50).mean().iloc[-1]
            
            pos_count = len(get_buy_positions())
            if pos_count == 0:
                lot_index = 0
            
            price = df['close'].iloc[-1]
            allow_entry = True
            blocks = []
            
            # Check max levels
            if lot_index >= MAX_LEVELS:
                allow_entry = False
                blocks.append("max_levels")
            
            # Check daily limit
            if not check_daily_limit():
                allow_entry = False
                blocks.append("daily_limit")
            
            # Check global cooldown
            if time.time() - last_entry_time < GLOBAL_COOLDOWN_SEC:
                allow_entry = False
                blocks.append("cooldown")
            
            # Check session
            if not session_filter():
                allow_entry = False
                blocks.append("session")
            
            # Check HTF bias (5m and 15m)
            htf_5m = get_htf_bias(SYMBOL, mt5.TIMEFRAME_M5)
            htf_15m = get_htf_bias(SYMBOL, mt5.TIMEFRAME_M15)
            
            if htf_5m == 'bearish' and htf_15m == 'bearish':
                allow_entry = False
                blocks.append("htf_bearish")
            
            # Check momentum
            if not momentum_filter(df):
                allow_entry = False
                blocks.append("momentum")
            
            # Check volatility
            vol_regime = get_volatility_regime(df)
            if AVOID_HIGH_VOLATILITY and vol_regime == 'high':
                allow_entry = False
                blocks.append("high_vol")
            
            if AVOID_SQUEEZE and bollinger_squeeze(df):
                allow_entry = False
                blocks.append("squeeze")
            
            log.info(
                f"PRICE={price:.2f} | IDX={lot_index}/{MAX_LEVELS} | "
                f"HTF=5m:{htf_5m}/15m:{htf_15m} | VOL={vol_regime} | "
                f"ALLOW={allow_entry} | BLOCKS={blocks}"
            )
            
            # Entry logic
            if pos_count == 0 and allow_entry:
                lot = calculate_dynamic_lot(lot_index, atr_current, atr_avg)
                buy(lot)
                lot_index += 1
            
            elif pos_count > 0 and allow_entry and lot_index < MAX_LEVELS:
                last_price = last_buy_price()
                grid_step = calculate_grid_spacing(atr_current, lot_index)
                
                if last_price > 0 and price <= last_price - grid_step:
                    # Extra confirmation for deeper levels
                    if lot_index >= 3:
                        bullish_candle = df['close'].iloc[-1] > df['open'].iloc[-1]
                        if not bullish_candle:
                            log.info("STACK BLOCKED | waiting bullish confirmation")
                        else:
                            lot = calculate_dynamic_lot(lot_index, atr_current, atr_avg)
                            buy(lot)
                            lot_index += 1
                    else:
                        lot = calculate_dynamic_lot(lot_index, atr_current, atr_avg)
                        buy(lot)
                        lot_index += 1
            
            time.sleep(1)
            
        except Exception as e:
            log.error(f"MAIN LOOP ERROR: {e}")
            time.sleep(5)

# =========================================================
# SAVE TRADE LOG
# =========================================================
def save_trade_log():
    """Save trade log to CSV periodically"""
    while True:
        try:
            time.sleep(3600)  # Save every hour
            if trade_log['timestamp']:
                df = pd.DataFrame(trade_log)
                filename = f"trades_{datetime.now().date()}.csv"
                df.to_csv(filename, index=False)
                log.info(f"Trade log saved to {filename}")
        except Exception as e:
            log.error(f"Error saving trade log: {e}")

# =========================================================
# START
# =========================================================
if __name__ == "__main__":
    init_mt5()
    Thread(target=basket_watcher, daemon=True).start()
    Thread(target=save_trade_log, daemon=True).start()
    run()

# Made with Bob
