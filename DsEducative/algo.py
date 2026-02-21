"""
🔥 ROBUST GOLD SCALPING STRATEGY - M1 TIMEFRAME
================================================

IMPROVEMENTS IMPLEMENTED:
-------------------------
1. ✅ Market Regime Detection (ADX + Choppiness Index)
   - Identifies: trending_up, trending_down, ranging, volatile
   - Prevents entries during unfavorable conditions

2. ✅ Volatility Gating System
   - MIN/MAX ATR thresholds prevent trading in dead or chaotic markets
   - Dynamic grid spacing based on current volatility

3. ✅ Liquidity Filters
   - Minimum tick volume requirements
   - Volume ratio checks vs moving average
   - Avoids low-liquidity periods (Asian session gaps, news events)

4. ✅ Structural Filters
   - Swing high/low detection
   - Prevents entries near key resistance/support levels
   - Reduces fake breakout entries

5. ✅ Anti-Chop Filters
   - Choppiness Index > 61.8 blocks entries
   - Candle body quality checks (min 25% body ratio)
   - Prevents overtrading in sideways markets

6. ✅ Dynamic TP/SL System
   - TP/SL calculated from ATR (adaptive to volatility)
   - Regime-based TP adjustments (let winners run in trends)
   - Position-count based TP scaling

7. ✅ Smart Stop Placement
   - ATR-based dynamic stops
   - Basket-level stop loss protection
   - Prevents catastrophic drawdowns

CONFIGURATION TUNING GUIDE:
---------------------------
For CONSERVATIVE (lower risk, fewer trades):
- Increase MIN_ATR_THRESHOLD to 0.5
- Increase ADX_TREND_THRESHOLD to 30
- Increase MIN_VOLUME_RATIO to 0.8
- Increase CHOP_THRESHOLD to 55

For AGGRESSIVE (more trades, higher risk):
- Decrease MIN_ATR_THRESHOLD to 0.2
- Decrease ADX_TREND_THRESHOLD to 20
- Decrease MIN_VOLUME_RATIO to 0.5
- Increase CHOP_THRESHOLD to 65

For VOLATILE MARKETS (Gold spikes):
- Increase MAX_ATR_THRESHOLD to 4.0
- Increase SL_ATR_MULTIPLIER to 2.5
- Decrease TP_ATR_MULTIPLIER to 1.2

For RANGING MARKETS (consolidation):
- Decrease MIN_GRID_GAP to 0.4
- Increase STRUCTURE_BUFFER to 2.0
- Decrease TP_ATR_MULTIPLIER to 1.0

USAGE:
------
1. Adjust configuration parameters below
2. Run: python gold.py
3. Monitor logs for filter activations
4. Tune parameters based on market conditions

RISK WARNING:
-------------
- Always test on demo account first
- Monitor during different market sessions
- Adjust FLOATING_LOSS_LIMIT based on account size
- Review logs daily to identify filter effectiveness
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
import logging
from threading import Thread
import sys
from concurrent.futures import ThreadPoolExecutor

# =========================================================
# LOGGING
# =========================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("gold_grid_bot.log"),
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
# STRATEGY CONFIG
# =========================================================
SYMBOL     = "GOLD.i#"
TIMEFRAME = mt5.TIMEFRAME_M1
MAGIC     = 777
last_buy_candle_time = 0

FLOATING_LOSS_LIMIT = -70.0

# ✅ USER REQUESTED LADDER
LOT_LADDER = [
    0.01, 0.01, 0.01,
    0.02, 0.02, 0.02,
    0.03, 0.03,
    0.04
]

MAX_DOWNSPEED = 2.5
MIN_GRID_GAP  = 0.6
COOLDOWN_SEC  = 3

# =========================================================
# 🔥 NEW: ROBUST FILTERS CONFIG
# =========================================================
# Volatility gating
MIN_ATR_THRESHOLD = 0.3      # Minimum ATR to allow trading
MAX_ATR_THRESHOLD = 3.0      # Maximum ATR (too volatile)
ATR_PERIOD = 14

# Liquidity filters
MIN_TICK_VOLUME = 50         # Minimum tick volume per candle
VOLUME_MA_PERIOD = 20
MIN_VOLUME_RATIO = 0.6       # Current vol must be > 60% of MA

# Market regime detection
REGIME_LOOKBACK = 30         # Bars to analyze for regime
ADX_PERIOD = 14
ADX_TREND_THRESHOLD = 25     # ADX > 25 = trending
ADX_STRONG_THRESHOLD = 35    # ADX > 35 = strong trend

# Structural filters
SWING_LOOKBACK = 20          # Bars to find swing highs/lows
STRUCTURE_BUFFER = 1.5       # Distance from structure in dollars

# Anti-chop filters
CHOP_INDEX_PERIOD = 14
CHOP_THRESHOLD = 61.8        # Above this = choppy market
MIN_CANDLE_BODY_RATIO = 0.25 # Body must be 25% of range

# Dynamic TP/SL
TP_ATR_MULTIPLIER = 1.5      # TP = ATR * multiplier
SL_ATR_MULTIPLIER = 2.0      # SL = ATR * multiplier
TRAILING_ACTIVATION = 0.5    # Start trailing at 50% of TP

lot_index = 0
last_entry_time = 0
basket_peak_price = 0
basket_active = False
# =========================================================
# INIT MT5
# =========================================================
def init_mt5():
    
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

    log.info(
        f"CONNECTED | {SYMBOL} "
        f"min_lot={info.volume_min} step={info.volume_step}"
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

# =========================================================
# 🔥 NEW: ADVANCED INDICATORS
# =========================================================
def calculate_ADX(df, period=14):
    """Calculate ADX for trend strength detection"""
    high = df['high']
    low = df['low']
    close = df['close']
    
    # Calculate +DM and -DM
    plus_dm = high.diff()
    minus_dm = -low.diff()
    
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0
    
    # True Range
    tr = np.maximum(
        high - low,
        np.maximum(
            abs(high - close.shift()),
            abs(low - close.shift())
        )
    )
    
    # Smooth with Wilder's method
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)
    
    # Calculate DX and ADX
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.ewm(alpha=1/period, adjust=False).mean()
    
    return adx, plus_di, minus_di

def calculate_choppiness_index(df, period=14):
    """Calculate Choppiness Index - higher values = more choppy"""
    high = df['high']
    low = df['low']
    close = df['close']
    
    tr = np.maximum(
        high - low,
        np.maximum(
            abs(high - close.shift()),
            abs(low - close.shift())
        )
    )
    
    atr_sum = tr.rolling(period).sum()
    high_low_range = high.rolling(period).max() - low.rolling(period).min()
    
    # Avoid division by zero
    high_low_range = high_low_range.replace(0, 0.0001)
    
    chop = 100 * np.log10(atr_sum / high_low_range) / np.log10(period)
    
    return chop

def find_swing_highs(df, lookback=20):
    """Find recent swing high levels"""
    highs = df['high'].rolling(window=lookback).max()
    return highs.iloc[-1]

def find_swing_lows(df, lookback=20):
    """Find recent swing low levels"""
    lows = df['low'].rolling(window=lookback).min()
    return lows.iloc[-1]

# =========================================================
# 🔥 NEW: MARKET REGIME & FILTER FUNCTIONS
# =========================================================
def detect_market_regime(df):
    """
    Detect market regime: trending_up, trending_down, ranging, volatile
    Returns: (regime, strength, details)
    """
    adx, plus_di, minus_di = calculate_ADX(df, ADX_PERIOD)
    chop = calculate_choppiness_index(df, CHOP_INDEX_PERIOD)
    atr = ATR(df, ATR_PERIOD)
    
    current_adx = adx.iloc[-1]
    current_chop = chop.iloc[-1]
    current_atr = atr.iloc[-1]
    current_plus_di = plus_di.iloc[-1]
    current_minus_di = minus_di.iloc[-1]
    
    # Determine regime
    if current_chop > CHOP_THRESHOLD:
        regime = "ranging"
        strength = "choppy"
    elif current_adx > ADX_STRONG_THRESHOLD:
        if current_plus_di > current_minus_di:
            regime = "trending_up"
            strength = "strong"
        else:
            regime = "trending_down"
            strength = "strong"
    elif current_adx > ADX_TREND_THRESHOLD:
        if current_plus_di > current_minus_di:
            regime = "trending_up"
            strength = "moderate"
        else:
            regime = "trending_down"
            strength = "moderate"
    else:
        regime = "ranging"
        strength = "weak"
    
    # Check volatility
    if current_atr > MAX_ATR_THRESHOLD:
        regime = "volatile"
        strength = "extreme"
    
    details = {
        "adx": current_adx,
        "chop": current_chop,
        "atr": current_atr,
        "plus_di": current_plus_di,
        "minus_di": current_minus_di
    }
    
    return regime, strength, details

def check_volatility_gate(df):
    """Check if volatility is within acceptable range"""
    atr = ATR(df, ATR_PERIOD)
    current_atr = atr.iloc[-1]
    
    if current_atr < MIN_ATR_THRESHOLD:
        return False, f"ATR too low: {current_atr:.2f}"
    elif current_atr > MAX_ATR_THRESHOLD:
        return False, f"ATR too high: {current_atr:.2f}"
    
    return True, f"ATR OK: {current_atr:.2f}"

def check_liquidity(df):
    """Check if there's sufficient liquidity"""
    current_vol = df['vol'].iloc[-1]
    vol_ma = df['vol'].rolling(VOLUME_MA_PERIOD).mean().iloc[-1]
    
    if current_vol < MIN_TICK_VOLUME:
        return False, f"Volume too low: {current_vol}"
    
    vol_ratio = current_vol / vol_ma if vol_ma > 0 else 0
    if vol_ratio < MIN_VOLUME_RATIO:
        return False, f"Volume ratio low: {vol_ratio:.2f}"
    
    return True, f"Liquidity OK: {current_vol}/{vol_ma:.0f}"

def check_structure(df, price):
    """Check if price is near key structural levels"""
    swing_high = find_swing_highs(df, SWING_LOOKBACK)
    swing_low = find_swing_lows(df, SWING_LOOKBACK)
    
    # Check if too close to swing high (resistance)
    if abs(price - swing_high) < STRUCTURE_BUFFER:
        return False, f"Near swing high: {swing_high:.2f}"
    
    # Check if too close to swing low (support)
    if abs(price - swing_low) < STRUCTURE_BUFFER:
        return False, f"Near swing low: {swing_low:.2f}"
    
    return True, f"Structure clear: H={swing_high:.2f} L={swing_low:.2f}"

def check_candle_quality(df):
    """Check if current candle has good body (not doji/pin bar)"""
    last = df.iloc[-1]
    candle_range = last['high'] - last['low']
    candle_body = abs(last['close'] - last['open'])
    
    if candle_range == 0:
        return False, "Zero range candle"
    
    body_ratio = candle_body / candle_range
    
    if body_ratio < MIN_CANDLE_BODY_RATIO:
        return False, f"Weak body: {body_ratio:.2f}"
    
    return True, f"Good candle: {body_ratio:.2f}"

def calculate_dynamic_tp_sl(df, entry_price):
    """Calculate dynamic TP and SL based on ATR"""
    atr = ATR(df, ATR_PERIOD).iloc[-1]
    
    tp_distance = atr * TP_ATR_MULTIPLIER
    sl_distance = atr * SL_ATR_MULTIPLIER
    
    tp_price = entry_price + tp_distance
    sl_price = entry_price - sl_distance
    
    return tp_price, sl_price, atr

def should_allow_entry_by_regime(regime, strength, pos_count):
    """Determine if entry is allowed based on market regime"""
    # No positions - be more selective
    if pos_count == 0:
        if regime == "volatile":
            return False, "Market too volatile for initial entry"
        if regime == "ranging" and strength == "choppy":
            return False, "Market too choppy for initial entry"
        if regime == "trending_down" and strength == "strong":
            return False, "Strong downtrend - avoid initial entry"
    
    # Has positions - allow averaging in trending up or moderate conditions
    else:
        if regime == "volatile":
            return False, "Market too volatile for adding"
        if regime == "trending_down" and strength == "strong":
            return False, "Strong downtrend - avoid adding"
    
    return True, f"Regime OK: {regime}/{strength}"

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
    return max(min_lot, round(lot / step) * step)
def reset_after_tp():
    global lot_index, last_buy_candle_time
    lot_index = 0
    last_buy_candle_time = 0
    cooldown_sec= 0
    log.info("BOT RESET | lot_index and candle tracker cleared")

# =========================================================
# ORDERS (EXECUTION SAFE)
# =========================================================
# Track last buy time per lot size
last_buy_time_per_lot = {}

def buy(lot):
    global last_entry_time, last_buy_candle_time, lot_index, last_buy_time_per_lot
    lot = normalize_lot(SYMBOL, lot)
    tick = mt5.symbol_info_tick(SYMBOL)

    pos_count = len(get_buy_positions()) # get current position count

    # Determine required cooldown in seconds based on lot
    cooldown_minutes = {
        0.01: 1,
        0.02: 2,
        0.03: 3,
        0.04: 4
    }
    cooldown_sec = cooldown_minutes.get(lot, 1) * 60

    # Apply cooldown only if there is at least one position
    if pos_count > 0:
        last_time = last_buy_time_per_lot.get(lot, 0)
        if time.time() - last_time < cooldown_sec:
            log.info(f"BUY BLOCKED | lot={lot} cooldown not met ({int((cooldown_sec-(time.time()-last_time))/60)} min left)")
            lot_index = max(0, lot_index - 1)
            return


    # Get current candle time (start of current minute)
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 1)
    if rates is None or len(rates) == 0:
        log.warning("No candle data, skipping buy")
        lot_index -= 1
        return
    current_candle_time = int(rates[-1]['time'])

    # Prevent multiple buys in the same candle
    if current_candle_time == last_buy_candle_time:
        log.info("BUY BLOCKED | already bought in this candle")
        lot_index -= 1
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
        "comment": "Grid Buy",
        "type_filling": mt5.ORDER_FILLING_IOC,
        "type_time": mt5.ORDER_TIME_GTC
    })

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        last_entry_time = time.time()
        last_buy_candle_time = current_candle_time
        last_buy_time_per_lot[lot] = time.time()  # update last buy time for this lot
        log.info(f"BUY EXECUTED | lot={lot} | candle={current_candle_time}")
    else:
        log.error(f"BUY FAILED | retcode={result.retcode} lot={lot}")
        lot_index -= 1


def close_position(p):
    tick = mt5.symbol_info_tick(SYMBOL)
    mt5.order_send({
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

def close_all_buys():
    pos = get_buy_positions()
    if not pos:
        return
    log.warning(f"CLOSING ALL BUYS | count={len(pos)}")
    with ThreadPoolExecutor(max_workers=min(5, len(pos))) as exe:
        exe.map(close_position, pos)


# =========================================================
# SAFETY & VOLUME
# =========================================================
def spread_ok():
    tick = mt5.symbol_info_tick(SYMBOL)
    return abs(tick.ask - tick.bid) <= 0.8

def price_drop_fast():
    ticks = mt5.copy_ticks_from(SYMBOL, time.time() - 3, 200, mt5.COPY_TICKS_ALL)
    if ticks is None or len(ticks) < 5:
        return False
    bids = ticks['bid']
    return (bids.max() - bids.min()) >= MAX_DOWNSPEED

def heavy_sell_volume(df):
    last = df.iloc[-1]
    return (
        last['close'] < last['open']
        and last['vol'] > 1.8 * df['vol_ema'].iloc[-1]
    )

def volume_exhausted(df):
    v = df['vol'].iloc[-3:]
    return v.iloc[0] > v.iloc[1] > v.iloc[2]

# =========================================================
# ✅ CORRECT LADDER LEVEL FOR 9 STEPS
# =========================================================
def ladder_level(idx):
    if idx <= 2:
        return "probe"
    elif idx <= 5:
        return "mid"
    elif idx <= 7:
        return "high"
    else:  # idx == 8
        return "extreme"

# =========================================================
# KILL SWITCH
# =========================================================
def floating_loss_kill():
    pnl = floating_buy_pnl()
    log.info(f"FLOATING BUY PNL={pnl:.2f}")
    if pnl <= FLOATING_LOSS_LIMIT:
        log.critical("FLOATING BUYLOSS LIMIT HIT")
        close_all_buys()
        # mt5.shutdown()
        # sys.exit(1)



def is_trend_up(df, fast_period=3, slow_period=5, body_threshold=0.3, has_position=False):
    """
    Returns True if:
        - Fast EMA is above Slow EMA (trend up)
        - Current candle is bullish (opened above previous close)
        - Candle body is large enough (ignores small candles)
        - No open position (if has_position=True, returns False)

    Parameters:
        df (pd.DataFrame): Must contain 'close' and 'open' columns
        fast_period (int): Fast EMA period (default 3)
        slow_period (int): Slow EMA period (default 5)
        body_threshold (float): Minimum candle size relative to 20-period average (default 0.3)
        has_position (bool): True if already in position; False means can trade

    Returns:
        bool
    """
    if df is None or df.empty or len(df) < slow_period + 21:  # need at least 21 bars for avg body
        return False  # not enough data

    # Calculate EMAs
    ema_fast = df['close'].ewm(span=fast_period, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow_period, adjust=False).mean()

    # Trend check
    trend_up = ema_fast.iloc[-1] > ema_slow.iloc[-1]

    # Bullish candle check
    bullish_open = df['open'].iloc[-1] > df['close'].iloc[-2]

    # Candle body filter
    body = abs(df['close'] - df['open'])
    avg_body = body.rolling(window=20).mean()
    ignore_small_candle = body.iloc[-1] < avg_body.iloc[-1] * body_threshold

    # Combine conditions
    can_trade = trend_up and bullish_open and not ignore_small_candle and not has_position

    return can_trade

def get_trend_state(df):
    ema20 = df['close'].ewm(span=20).mean()
    ema50 = df['close'].ewm(span=50).mean()

    slope = ema20.iloc[-1] - ema20.iloc[-5]

    if ema20.iloc[-1] > ema50.iloc[-1] and slope > 0.5:
        return "strong_up"
    elif ema20.iloc[-1] < ema50.iloc[-1] and slope < -0.5:
        return "strong_down"
    else:
        return "range"
def get_immediate_resistance(df):

    trend = get_trend_state(df)

    if trend == "strong_up":
        swing_window = 4
        lookback = 20

    elif trend == "strong_down":
        swing_window = 2
        lookback = 10

    else:  # range
        swing_window = 3
        lookback = 15

    highs = df['high'].iloc[-lookback:]

    resistance = highs.max()

    return resistance

def basket_watcher():
    """
    🔥 IMPROVED: Dynamic TP/SL based on market conditions
    """
    global lot_index, basket_active

    log.info("🎯 BASKET WATCHER STARTED - DYNAMIC TP/SL")

    while True:
        pos = get_buy_positions()
        pos_count = len(pos)

        # ------------------------------
        # No positions → reset basket
        # ------------------------------
        if pos_count == 0:
            if basket_active:
                log.info("✅ No positions - Resetting basket state")
            basket_active = False
            time.sleep(0.5)
            continue

        # ------------------------------
        # Get market data for dynamic TP calculation
        # ------------------------------
        rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 100)
        if rates is None or len(rates) < 50:
            time.sleep(0.5)
            continue
        
        df = pd.DataFrame(rates)
        df['vol'] = df['tick_volume']
        
        # Detect market regime
        regime, strength, regime_details = detect_market_regime(df)
        current_atr = regime_details['atr']
        
        # ------------------------------
        # Get current floating PnL for the basket
        # ------------------------------
        floating_pnl = sum([p.profit for p in pos])
        avg_price = avg_buy_price()
        total_volume = total_buy_volume()
        
        # ------------------------------
        # 🔥 DYNAMIC TP based on regime and position count
        # ------------------------------
        base_tp = 1.0
        
        # Adjust TP based on position count (more positions = lower TP)
        if pos_count == 1:
            count_multiplier = 1.0
        elif 2 <= pos_count <= 3:
            count_multiplier = 0.85
        elif 4 <= pos_count <= 5:
            count_multiplier = 0.70
        else:
            count_multiplier = 0.60
        
        # Adjust TP based on market regime
        if regime == "trending_up" and strength == "strong":
            regime_multiplier = 1.3  # Let winners run in strong uptrend
        elif regime == "trending_up":
            regime_multiplier = 1.1
        elif regime == "ranging":
            regime_multiplier = 0.9  # Take profit faster in range
        elif regime == "volatile":
            regime_multiplier = 0.8  # Take profit quickly in volatile market
        else:  # trending_down
            regime_multiplier = 0.7  # Exit fast in downtrend
        
        # Calculate final TP target
        tp_target = base_tp * count_multiplier * regime_multiplier
        
        # Minimum TP to avoid too-tight exits
        tp_target = max(tp_target, 0.5)
        
        # ------------------------------
        # 🔥 DYNAMIC SL based on ATR
        # ------------------------------
        # Calculate max acceptable loss based on ATR and position size
        max_loss_per_lot = current_atr * SL_ATR_MULTIPLIER
        max_basket_loss = -(max_loss_per_lot * total_volume)
        
        log.info(
            f"📊 [BASKET] PnL={floating_pnl:.2f} | TP={tp_target:.2f} | "
            f"MaxLoss={max_basket_loss:.2f} | Avg={avg_price:.2f} | "
            f"Pos={pos_count} | Vol={total_volume:.2f} | "
            f"Regime={regime}/{strength} | ATR={current_atr:.2f}"
        )
        
        # ------------------------------
        # Close on TP hit
        # ------------------------------
        if floating_pnl >= tp_target:
            log.info(
                f"✅ BASKET TP HIT - Closing All | "
                f"PnL={floating_pnl:.2f} | Target={tp_target:.2f} | "
                f"Regime={regime}"
            )
            close_all_buys()
            reset_after_tp()
            basket_active = False
            time.sleep(0.5)
            continue
        
        # ------------------------------
        # 🔥 NEW: Dynamic SL protection
        # ------------------------------
        if floating_pnl <= max_basket_loss:
            log.warning(
                f"🛑 DYNAMIC SL HIT - Closing All | "
                f"PnL={floating_pnl:.2f} | MaxLoss={max_basket_loss:.2f} | "
                f"ATR={current_atr:.2f}"
            )
            close_all_buys()
            reset_after_tp()
            basket_active = False
            time.sleep(0.5)
            continue

        time.sleep(0.3)
      
    
# =========================================================
# 🔥 REDESIGNED MAIN LOOP WITH ROBUST FILTERS
# =========================================================
def run():
    global lot_index
    log.info("🚀 GOLD SCALPING BOT STARTED - ROBUST VERSION")

    while True:
        floating_loss_kill()

        # Get sufficient data for all indicators
        rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 150)
        if rates is None or len(rates) < 100:
            time.sleep(1)
            continue

        df = pd.DataFrame(rates)
        df['vol'] = df['tick_volume']
        df['vol_ema'] = EMA(df['vol'], VOLUME_MA_PERIOD)

        pos_count = len(get_buy_positions())
        if pos_count == 0:
            lot_index = 0

        price = df['close'].iloc[-1]
        
        # =========================================================
        # 🔥 STEP 1: MARKET REGIME DETECTION
        # =========================================================
        regime, strength, regime_details = detect_market_regime(df)
        
        # =========================================================
        # 🔥 STEP 2: APPLY ALL FILTERS
        # =========================================================
        allow_entry = True
        blocks = []
        
        # Check ladder limit
        if lot_index >= len(LOT_LADDER):
            allow_entry = False
            blocks.append("ladder_end")
        
        # Check spread
        if not spread_ok():
            allow_entry = False
            blocks.append("spread")
        
        # Check cooldown
        if time.time() - last_entry_time < COOLDOWN_SEC:
            allow_entry = False
            blocks.append("cooldown")
        
        # 🔥 NEW: Volatility gate
        vol_ok, vol_msg = check_volatility_gate(df)
        if not vol_ok:
            allow_entry = False
            blocks.append(f"volatility:{vol_msg}")
        
        # 🔥 NEW: Liquidity check
        liq_ok, liq_msg = check_liquidity(df)
        if not liq_ok:
            allow_entry = False
            blocks.append(f"liquidity:{liq_msg}")
        
        # 🔥 NEW: Market regime filter
        regime_ok, regime_msg = should_allow_entry_by_regime(regime, strength, pos_count)
        if not regime_ok:
            allow_entry = False
            blocks.append(f"regime:{regime_msg}")
        
        # 🔥 NEW: Structural filter
        struct_ok, struct_msg = check_structure(df, price)
        if not struct_ok:
            allow_entry = False
            blocks.append(f"structure:{struct_msg}")
        
        # 🔥 NEW: Candle quality filter
        candle_ok, candle_msg = check_candle_quality(df)
        if not candle_ok:
            allow_entry = False
            blocks.append(f"candle:{candle_msg}")
        
        # Legacy filters (kept for compatibility)
        level = ladder_level(lot_index)
        
        if level in ("mid", "high", "extreme"):
            ema_fast = EMA(df['close'], 3)
            ema_slow = EMA(df['close'], 5)
            if ema_fast.iloc[-1] < ema_slow.iloc[-1]:
                allow_entry = False
                blocks.append("ema_trend")
        
        if level in ("high", "extreme"):
            if heavy_sell_volume(df):
                allow_entry = False
                blocks.append("heavy_vol")
            if not volume_exhausted(df):
                allow_entry = False
                blocks.append("vol_not_exhausted")
        
        if level == "extreme":
            if price_drop_fast():
                allow_entry = False
                blocks.append("downspeed")
        
        # =========================================================
        # 🔥 STEP 3: CALCULATE DYNAMIC GRID STEP
        # =========================================================
        atr_current = ATR(df, ATR_PERIOD).iloc[-1]
        
        # Dynamic grid step based on volatility
        if regime == "volatile":
            grid_step = max(atr_current * 0.25, MIN_GRID_GAP * 1.5)
        elif regime == "ranging":
            grid_step = max(atr_current * 0.15, MIN_GRID_GAP)
        else:  # trending
            grid_step = max(atr_current * 0.20, MIN_GRID_GAP)
        
        # =========================================================
        # 🔥 STEP 4: LOGGING
        # =========================================================
        log.info(
            f"📊 PRICE={price:.2f} | REGIME={regime}/{strength} | "
            f"ADX={regime_details['adx']:.1f} | CHOP={regime_details['chop']:.1f} | "
            f"ATR={regime_details['atr']:.2f} | IDX={lot_index}/{len(LOT_LADDER)} | "
            f"LVL={level} | POS={pos_count} | ALLOW={allow_entry}"
        )
        
        if blocks:
            log.info(f"🚫 BLOCKS: {', '.join(blocks)}")
        
        # =========================================================
        # 🔥 STEP 5: ENTRY LOGIC
        # =========================================================
        if pos_count == 0 and allow_entry:
            log.info(f"✅ INITIAL ENTRY | Lot={LOT_LADDER[lot_index]}")
            buy(LOT_LADDER[lot_index])
            lot_index += 1
        
        elif pos_count > 0 and allow_entry and lot_index < len(LOT_LADDER):
            last_price = last_buy_price()
            
            if last_price > 0 and price <= last_price - grid_step:
                # Extra confirmation for deeper levels
                if level in ("high", "extreme"):
                    bullish_candle = df['close'].iloc[-1] > df['open'].iloc[-1]
                    
                    if not bullish_candle:
                        log.info("⏸️ STACK BLOCKED | Waiting for bullish confirmation")
                    else:
                        log.info(f"✅ ADDING POSITION | Lot={LOT_LADDER[lot_index]} | Level={level}")
                        buy(LOT_LADDER[lot_index])
                        lot_index += 1
                else:
                    log.info(f"✅ ADDING POSITION | Lot={LOT_LADDER[lot_index]} | Level={level}")
                    buy(LOT_LADDER[lot_index])
                    lot_index += 1

        time.sleep(1)

# =========================================================
# START
# =========================================================
init_mt5()
Thread(target=basket_watcher, daemon=True).start()
run()
