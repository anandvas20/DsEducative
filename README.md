Hello:

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
import logging
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple
from enum import Enum


# =========================================================
# LOGGING CONFIGURATION
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
# ENUMS
# =========================================================
class LadderLevel(Enum):
    """Trading ladder levels with associated risk"""
    PROBE = "probe"
    MID = "mid"
    HIGH = "high"
    EXTREME = "extreme"


class TrendState(Enum):
    """Market trend states"""
    STRONG_UP = "strong_up"
    STRONG_DOWN = "strong_down"
    RANGE = "range"


class VolatilityRegime(Enum):
    """Volatility regime classification"""
    ULTRA_LOW = "ultra_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"


# =========================================================
# CONFIGURATION
# =========================================================
@dataclass
class TradingConfig:
    """Centralized trading configuration"""
    # MT5 Connection
    mt5_path: str = r"C:\Users\Naveen Kumar Reddy\AppData\Roaming\XM Global MT5\terminal64.exe"
    mt5_login: int = 167958826
    mt5_password: str = "Panvith@143"
    mt5_server: str = "XMGlobal-MT5 2"
    
    # Trading Parameters
    symbol: str = "GOLD.i#"
    timeframe: int = mt5.TIMEFRAME_M1
    magic: int = 777
    
    # Risk Management
    floating_loss_limit: float = -50.0  # Tightened from -70
    daily_loss_limit: float = -200.0  # Daily loss limit
    max_baskets_per_day: int = 5  # Max basket attempts per day
    max_consecutive_losses: int = 3  # Circuit breaker
    max_downspeed: float = 2.5
    cooldown_sec: int = 3
    
    # Anti-Martingale: Position sizes DECREASE as we go deeper
    use_anti_martingale: bool = True
    max_positions: int = 5  # Reduced from 9
    
    # Kelly Criterion
    use_kelly_sizing: bool = True
    kelly_fraction: float = 0.25  # Quarter Kelly for safety
    
    # Trailing Stop
    use_trailing_stop: bool = True
    trailing_stop_percent: float = 0.5  # Trail at 50% of peak
    
    # Dynamic TP/SL
    use_dynamic_targets: bool = True
    
    # Cooldown per lot size (in minutes)
    cooldown_minutes: Dict[float, int] = None
    
    def __post_init__(self):
        if self.cooldown_minutes is None:
            self.cooldown_minutes = {
                0.01: 1,
                0.02: 2,
                0.03: 3
            }


# =========================================================
# TECHNICAL INDICATORS
# =========================================================
class TechnicalIndicators:
    """Technical analysis indicators"""
    
    @staticmethod
    def ema(series: pd.Series, period: int) -> pd.Series:
        """Calculate Exponential Moving Average"""
        return series.ewm(span=period, adjust=False).mean()
    
    @staticmethod
    def atr(df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate Average True Range"""
        tr = np.maximum(
            df['high'] - df['low'],
            np.maximum(
                abs(df['high'] - df['close'].shift()),
                abs(df['low'] - df['close'].shift())
            )
        )
        return tr.rolling(period).mean()
    
    @staticmethod
    def volume_ema(df: pd.DataFrame, period: int = 20) -> pd.Series:
        """Calculate volume EMA"""
        return TechnicalIndicators.ema(df['vol'], period)


# =========================================================
# POSITION MANAGER
# =========================================================
class PositionManager:
    """Manages position queries and calculations"""
    
    def __init__(self, symbol: str):
        self.symbol = symbol
    
    def get_buy_positions(self) -> List:
        """Get all open buy positions"""
        positions = mt5.positions_get(symbol=self.symbol)
        return [p for p in (positions or []) if p.type == mt5.ORDER_TYPE_BUY]
    
    def total_buy_volume(self) -> float:
        """Calculate total volume of buy positions"""
        return sum(p.volume for p in self.get_buy_positions())
    
    def avg_buy_price(self) -> float:
        """Calculate volume-weighted average buy price"""
        positions = self.get_buy_positions()
        if not positions:
            return 0.0
        total_volume = sum(p.volume for p in positions)
        weighted_sum = sum(p.volume * p.price_open for p in positions)
        return weighted_sum / total_volume
    
    def last_buy_price(self) -> float:
        """Get the price of the most recent buy position"""
        positions = self.get_buy_positions()
        if not positions:
            return 0.0
        return max(positions, key=lambda p: p.time).price_open
    
    def floating_buy_pnl(self) -> float:
        """Calculate total floating P&L for buy positions"""
        return sum(p.profit for p in self.get_buy_positions())
    
    def position_count(self) -> int:
        """Get count of open buy positions"""
        return len(self.get_buy_positions())


# =========================================================
# ORDER EXECUTOR
# =========================================================
class OrderExecutor:
    """Handles order execution and management"""
    
    def __init__(self, config: TradingConfig, position_manager: PositionManager):
        self.config = config
        self.position_manager = position_manager
        self.last_entry_time = 0
        self.last_buy_candle_time = 0
        self.last_buy_time_per_lot: Dict[float, float] = {}
    
    def normalize_lot(self, lot: float) -> float:
        """Normalize lot size to broker requirements"""
        info = mt5.symbol_info(self.config.symbol)
        step = info.volume_step
        min_lot = info.volume_min
        return max(min_lot, round(lot / step) * step)
    
    def check_cooldown(self, lot: float, pos_count: int) -> Tuple[bool, str]:
        """Check if cooldown period has passed for given lot size"""
        if pos_count == 0:
            return True, ""
        
        cooldown_sec = self.config.cooldown_minutes.get(lot, 1) * 60
        last_time = self.last_buy_time_per_lot.get(lot, 0)
        time_elapsed = time.time() - last_time
        
        if time_elapsed < cooldown_sec:
            minutes_left = int((cooldown_sec - time_elapsed) / 60)
            return False, f"cooldown not met ({minutes_left} min left)"
        
        return True, ""
    
    def check_candle_restriction(self) -> Tuple[bool, int]:
        """Check if we can buy in current candle"""
        rates = mt5.copy_rates_from_pos(self.config.symbol, self.config.timeframe, 0, 1)
        if rates is None or len(rates) == 0:
            log.warning("No candle data available")
            return False, 0
        
        current_candle_time = int(rates[-1]['time'])
        if current_candle_time == self.last_buy_candle_time:
            return False, current_candle_time
        
        return True, current_candle_time
    
    def execute_buy(self, lot: float) -> bool:
        """Execute a buy order with all safety checks"""
        lot = self.normalize_lot(lot)
        pos_count = self.position_manager.position_count()
        
        # Check cooldown
        cooldown_ok, cooldown_msg = self.check_cooldown(lot, pos_count)
        if not cooldown_ok:
            log.info(f"BUY BLOCKED | lot={lot} {cooldown_msg}")
            return False
        
        # Check candle restriction
        candle_ok, current_candle_time = self.check_candle_restriction()
        if not candle_ok:
            if current_candle_time > 0:
                log.info("BUY BLOCKED | already bought in this candle")
            return False
        
        # Execute order
        tick = mt5.symbol_info_tick(self.config.symbol)
        result = mt5.order_send({
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.config.symbol,
            "volume": lot,
            "type": mt5.ORDER_TYPE_BUY,
            "price": tick.ask,
            "magic": self.config.magic,
            "deviation": 50,
            "comment": "Grid Buy",
            "type_filling": mt5.ORDER_FILLING_IOC,
            "type_time": mt5.ORDER_TIME_GTC
        })
        
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            self.last_entry_time = time.time()
            self.last_buy_candle_time = current_candle_time
            self.last_buy_time_per_lot[lot] = time.time()
            log.info(f"BUY EXECUTED | lot={lot} | candle={current_candle_time}")
            return True
        else:
            log.error(f"BUY FAILED | retcode={result.retcode} lot={lot}")
            return False
    
    def close_position(self, position) -> None:
        """Close a single position"""
        tick = mt5.symbol_info_tick(self.config.symbol)
        mt5.order_send({
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.config.symbol,
            "volume": position.volume,
            "type": mt5.ORDER_TYPE_SELL,
            "position": position.ticket,
            "price": tick.bid,
            "magic": self.config.magic,
            "deviation": 50,
            "comment": "Close",
            "type_filling": mt5.ORDER_FILLING_IOC,
            "type_time": mt5.ORDER_TIME_GTC
        })
    
    def close_all_buys(self) -> None:
        """Close all buy positions concurrently"""
        positions = self.position_manager.get_buy_positions()
        if not positions:
            return
        
        log.warning(f"CLOSING ALL BUYS | count={len(positions)}")
        with ThreadPoolExecutor(max_workers=min(5, len(positions))) as exe:
            exe.map(self.close_position, positions)
    
    def reset_after_tp(self) -> None:
        """Reset state after take profit"""
        self.last_buy_candle_time = 0
        log.info("BOT RESET | candle tracker cleared")


# =========================================================
# MARKET ANALYZER
# =========================================================
class MarketAnalyzer:
    """Analyzes market conditions and validates trading signals"""
    
    def __init__(self, config: TradingConfig):
        self.config = config
        self.current_regime = VolatilityRegime.LOW
    
    def detect_volatility_regime(self, df: pd.DataFrame) -> VolatilityRegime:
        """
        Classify market into volatility regimes using ATR z-score
        """
        if len(df) < 25:
            return VolatilityRegime.LOW
        
        atr_20 = TechnicalIndicators.atr(df, 20)
        atr_current = atr_20.iloc[-1]
        atr_mean = atr_20.mean()
        atr_std = atr_20.std()
        
        if atr_std == 0:
            return VolatilityRegime.LOW
        
        z_score = (atr_current - atr_mean) / atr_std
        
        if z_score < -1.0:
            regime = VolatilityRegime.ULTRA_LOW
        elif z_score < 0:
            regime = VolatilityRegime.LOW
        elif z_score < 1.0:
            regime = VolatilityRegime.MEDIUM
        elif z_score < 2.0:
            regime = VolatilityRegime.HIGH
        else:
            regime = VolatilityRegime.EXTREME
        
        self.current_regime = regime
        return regime
    
    def calculate_adaptive_grid(self, regime: VolatilityRegime, atr: float, price: float) -> float:
        """
        Calculate grid spacing with inverse volatility relationship
        Tighter grids in high volatility for faster mean reversion capture
        """
        regime_multipliers = {
            VolatilityRegime.ULTRA_LOW: 0.25,
            VolatilityRegime.LOW: 0.20,
            VolatilityRegime.MEDIUM: 0.15,
            VolatilityRegime.HIGH: 0.10,
            VolatilityRegime.EXTREME: 0.05
        }
        
        base_grid = atr * regime_multipliers[regime]
        
        # Scale with price level (Gold at 2650 vs 1800)
        scaled_grid = base_grid * (price / 2000)
        
        return max(scaled_grid, 0.3)
    
    def get_anti_martingale_size(self, index: int, regime: VolatilityRegime) -> float:
        """
        ANTI-MARTINGALE: Position sizes DECREASE as we go deeper
        Opposite of traditional martingale - reduces risk in drawdown
        """
        base_sizes = {
            VolatilityRegime.ULTRA_LOW: [0.03, 0.03, 0.02, 0.02, 0.01],
            VolatilityRegime.LOW: [0.02, 0.02, 0.02, 0.01, 0.01],
            VolatilityRegime.MEDIUM: [0.02, 0.01, 0.01, 0.01, 0.01],
            VolatilityRegime.HIGH: [0.01, 0.01, 0.01, 0.01, 0.01],
            VolatilityRegime.EXTREME: [0.01, 0.01, 0.01, 0.00, 0.00]
        }
        
        sizes = base_sizes[regime]
        return sizes[min(index, len(sizes)-1)]
    
    def calculate_kelly_size(self, win_rate: float, avg_win: float, avg_loss: float, base_size: float) -> float:
        """
        Kelly Criterion for optimal position sizing
        Uses quarter-Kelly for safety
        """
        if avg_loss == 0 or win_rate <= 0:
            return 0.0
        
        b = avg_win / abs(avg_loss)  # Payoff ratio
        p = win_rate
        q = 1 - p
        
        kelly_fraction = (p * b - q) / b
        
        # Use quarter Kelly and apply to base size
        if kelly_fraction > 0:
            return base_size * kelly_fraction * 0.25
        return 0.0
    
    def check_spread(self) -> bool:
        """Check if spread is acceptable"""
        tick = mt5.symbol_info_tick(self.config.symbol)
        return abs(tick.ask - tick.bid) <= 0.8
    
    def check_price_drop_speed(self) -> bool:
        """Check if price is dropping too fast"""
        ticks = mt5.copy_ticks_from(self.config.symbol, time.time() - 3, 200, mt5.COPY_TICKS_ALL)
        if ticks is None or len(ticks) < 5:
            return False
        bids = ticks['bid']
        return (bids.max() - bids.min()) >= self.config.max_downspeed
    
    def check_heavy_sell_volume(self, df: pd.DataFrame) -> bool:
        """Detect heavy selling volume"""
        last = df.iloc[-1]
        return (
            last['close'] < last['open']
            and last['vol'] > 1.8 * df['vol_ema'].iloc[-1]
        )
    
    def check_volume_exhaustion(self, df: pd.DataFrame) -> bool:
        """Check if selling volume is exhausting (improved logic)"""
        if len(df) < 5:
            return False
        
        # Check last 4 candles for declining volume trend
        v = df['vol'].iloc[-4:]
        vol_ema = df['vol_ema'].iloc[-1]
        
        # Volume should be declining AND below average
        declining = v.iloc[-1] < v.iloc[-2] < v.iloc[-3]
        below_avg = v.iloc[-1] < vol_ema * 0.8
        
        return declining and below_avg
    
    def get_ladder_level(self, index: int) -> LadderLevel:
        """Determine ladder level based on position index"""
        if index <= 2:
            return LadderLevel.PROBE
        elif index <= 5:
            return LadderLevel.MID
        elif index <= 7:
            return LadderLevel.HIGH
        else:
            return LadderLevel.EXTREME
    
    def get_trend_state(self, df: pd.DataFrame) -> TrendState:
        """Determine current market trend"""
        ema20 = TechnicalIndicators.ema(df['close'], 20)
        ema50 = TechnicalIndicators.ema(df['close'], 50)
        slope = ema20.iloc[-1] - ema20.iloc[-5]
        
        if ema20.iloc[-1] > ema50.iloc[-1] and slope > 0.5:
            return TrendState.STRONG_UP
        elif ema20.iloc[-1] < ema50.iloc[-1] and slope < -0.5:
            return TrendState.STRONG_DOWN
        else:
            return TrendState.RANGE
    
    def get_immediate_resistance(self, df: pd.DataFrame) -> float:
        """Calculate immediate resistance using proper swing high detection"""
        lookback = 20
        highs = df['high'].iloc[-lookback:]
        
        # Find swing highs (peaks where price is higher than neighbors)
        swing_highs = []
        for i in range(2, len(highs) - 2):
            if (highs.iloc[i] > highs.iloc[i-1] and
                highs.iloc[i] > highs.iloc[i-2] and
                highs.iloc[i] > highs.iloc[i+1] and
                highs.iloc[i] > highs.iloc[i+2]):
                swing_highs.append(highs.iloc[i])
        
        # Return highest swing high, or simple max if no swings found
        return max(swing_highs) if swing_highs else highs.max()
    
    def is_trading_session_allowed(self) -> Tuple[bool, str]:
        """Check if current time is in allowed trading session"""
        from datetime import datetime, time as dt_time
        
        # Get current UTC time
        now_utc = datetime.utcnow()
        current_time = now_utc.time()
        
        # Define restricted periods (UTC)
        # Avoid: 22:00-02:00 UTC (low liquidity Asian session)
        # Avoid: First 15 min of major sessions
        # Avoid: Last 15 min before major news (simplified: avoid 12:15-12:45 UTC for US news)
        
        # Low liquidity period
        if dt_time(22, 0) <= current_time or current_time < dt_time(2, 0):
            return False, "low_liquidity_session"
        
        # London open buffer (07:45-08:15 UTC)
        if dt_time(7, 45) <= current_time < dt_time(8, 15):
            return False, "london_open_buffer"
        
        # NY open buffer (12:45-13:15 UTC)
        if dt_time(12, 45) <= current_time < dt_time(13, 15):
            return False, "ny_open_buffer"
        
        # Major news time buffer (12:15-12:45 UTC - typical US news time)
        if dt_time(12, 15) <= current_time < dt_time(12, 45):
            return False, "news_time_buffer"
        
        return True, ""
    
    def is_trend_up(
        self,
        df: pd.DataFrame,
        fast_period: int = 3,
        slow_period: int = 5,
        body_threshold: float = 0.3,
        has_position: bool = False
    ) -> bool:
        """
        Check if market is in uptrend with bullish confirmation
        
        Args:
            df: DataFrame with OHLC data
            fast_period: Fast EMA period
            slow_period: Slow EMA period
            body_threshold: Minimum candle body size threshold
            has_position: Whether a position is already open
            
        Returns:
            True if conditions for uptrend are met
        """
        if df is None or df.empty or len(df) < slow_period + 21:
            return False
        
        # Calculate EMAs
        ema_fast = TechnicalIndicators.ema(df['close'], fast_period)
        ema_slow = TechnicalIndicators.ema(df['close'], slow_period)
        
        # Trend check
        trend_up = ema_fast.iloc[-1] > ema_slow.iloc[-1]
        
        # Bullish candle check
        bullish_open = df['open'].iloc[-1] > df['close'].iloc[-2]
        
        # Candle body filter
        body = abs(df['close'] - df['open'])
        avg_body = body.rolling(window=20).mean()
        ignore_small_candle = body.iloc[-1] < avg_body.iloc[-1] * body_threshold
        
        return trend_up and bullish_open and not ignore_small_candle and not has_position


# =========================================================
# BASKET MANAGER
# =========================================================
class BasketManager:
    """Manages basket of positions and take profit logic"""
    
    def __init__(
        self,
        config: TradingConfig,
        position_manager: PositionManager,
        order_executor: OrderExecutor
    ):
        self.config = config
        self.position_manager = position_manager
        self.order_executor = order_executor
        self.basket_active = False
        self.peak_pnl = 0.0
        self.trailing_stop_level = 0.0
    
    def calculate_tp_target(self, pos_count: int) -> float:
        """Calculate take profit target based on position count"""
        if pos_count == 1:
            return 1.0
        elif 2 <= pos_count <= 3:
            return 0.9
        elif 4 <= pos_count <= 5:
            return 0.8
        else:
            return 0.7
    
    def calculate_dynamic_tp(self, regime: VolatilityRegime, pos_count: int, atr: float, total_volume: float) -> float:
        """
        Dynamic TP that scales with volatility and position count
        Higher volatility = higher TP target
        """
        base_tp_pips = {
            VolatilityRegime.ULTRA_LOW: 0.8,
            VolatilityRegime.LOW: 1.0,
            VolatilityRegime.MEDIUM: 1.5,
            VolatilityRegime.HIGH: 2.0,
            VolatilityRegime.EXTREME: 3.0
        }
        
        tp_pips = base_tp_pips[regime]
        
        # Adjust for position count (more positions = lower TP)
        tp_pips *= (1 - 0.1 * (pos_count - 1))
        tp_pips = max(tp_pips, 0.5)
        
        # Convert to dollar value
        tp_dollars = tp_pips * total_volume * 10  # $10 per pip per lot
        
        return max(tp_dollars, 0.5)
    
    def update_trailing_stop(self, floating_pnl: float) -> float:
        """
        Update trailing stop level
        Locks in profits as they grow
        """
        if not self.config.use_trailing_stop:
            return 0.0
        
        # Update peak
        if floating_pnl > self.peak_pnl:
            self.peak_pnl = floating_pnl
        
        # Trail at configured percentage of peak
        self.trailing_stop_level = self.peak_pnl * self.config.trailing_stop_percent
        
        # Minimum trail: breakeven
        return max(self.trailing_stop_level, 0.0)
    
    def check_trailing_stop_hit(self, floating_pnl: float) -> bool:
        """Check if trailing stop has been hit"""
        if not self.config.use_trailing_stop or self.peak_pnl <= 0:
            return False
        
        return floating_pnl <= self.trailing_stop_level
    
    def watch_basket(self, risk_manager) -> None:
        """Monitor basket and close on take profit or trailing stop"""
        log.info("BASKET WATCHER STARTED")
        
        while True:
            positions = self.position_manager.get_buy_positions()
            pos_count = len(positions)
            
            # No positions - reset basket
            if pos_count == 0:
                if self.basket_active:
                    log.info("No positions - Resetting basket state")
                self.basket_active = False
                self.peak_pnl = 0.0
                self.trailing_stop_level = 0.0
                time.sleep(0.5)
                continue
            
            # Calculate floating PnL
            floating_pnl = sum(p.profit for p in positions)
            avg_price = self.position_manager.avg_buy_price()
            tp_target = self.calculate_tp_target(pos_count)
            
            # Update trailing stop
            trailing_stop = self.update_trailing_stop(floating_pnl)
            
            log.info(
                f"[BASKET STATUS] FloatingPnL={floating_pnl:.2f} | "
                f"Avg={avg_price:.2f} | TP_Target={tp_target:.2f} | "
                f"Peak={self.peak_pnl:.2f} | Trail={trailing_stop:.2f} | "
                f"Positions={pos_count}"
            )
            
            # Check trailing stop hit
            if self.check_trailing_stop_hit(floating_pnl):
                log.info(
                    f"TRAILING STOP HIT - Closing All Buys | "
                    f"FloatingPnL={floating_pnl:.2f} | Peak={self.peak_pnl:.2f}"
                )
                self.order_executor.close_all_buys()
                self.order_executor.reset_after_tp()
                risk_manager.record_basket_result(floating_pnl)
                self.basket_active = False
                self.peak_pnl = 0.0
                self.trailing_stop_level = 0.0
                time.sleep(0.5)
                continue
            
            # Close on take profit
            if floating_pnl >= tp_target:
                log.info(
                    f"BASKET TP HIT - Closing All Buys | "
                    f"FloatingPnL={floating_pnl:.2f} | TP Target={tp_target:.2f}"
                )
                self.order_executor.close_all_buys()
                self.order_executor.reset_after_tp()
                risk_manager.record_basket_result(floating_pnl)
                self.basket_active = False
                self.peak_pnl = 0.0
                self.trailing_stop_level = 0.0
                time.sleep(0.5)
                continue
            
            time.sleep(0.2)


# =========================================================
# RISK MANAGER
# =========================================================
class RiskManager:
    """Manages risk and implements kill switches"""
    
    def __init__(
        self,
        config: TradingConfig,
        position_manager: PositionManager,
        order_executor: OrderExecutor
    ):
        self.config = config
        self.position_manager = position_manager
        self.order_executor = order_executor
        self.daily_pnl = 0.0
        self.baskets_today = 0
        self.consecutive_losses = 0
        self.last_reset_date = time.strftime("%Y-%m-%d")
    
    def reset_daily_stats(self) -> None:
        """Reset daily statistics at start of new day"""
        current_date = time.strftime("%Y-%m-%d")
        if current_date != self.last_reset_date:
            log.info(f"NEW DAY | Resetting daily stats | Previous P&L: {self.daily_pnl:.2f}")
            self.daily_pnl = 0.0
            self.baskets_today = 0
            self.consecutive_losses = 0
            self.last_reset_date = current_date
    
    def check_daily_limits(self) -> bool:
        """Check if daily trading limits are exceeded"""
        self.reset_daily_stats()
        
        if self.daily_pnl <= self.config.daily_loss_limit:
            log.critical(f"DAILY LOSS LIMIT HIT | P&L: {self.daily_pnl:.2f}")
            return False
        
        if self.baskets_today >= self.config.max_baskets_per_day:
            log.warning(f"MAX BASKETS PER DAY REACHED | Count: {self.baskets_today}")
            return False
        
        if self.consecutive_losses >= self.config.max_consecutive_losses:
            log.critical(f"MAX CONSECUTIVE LOSSES HIT | Count: {self.consecutive_losses}")
            return False
        
        return True
    
    def record_basket_result(self, pnl: float) -> None:
        """Record basket closure result"""
        self.daily_pnl += pnl
        self.baskets_today += 1
        
        if pnl < 0:
            self.consecutive_losses += 1
            log.warning(f"BASKET LOSS | P&L: {pnl:.2f} | Consecutive: {self.consecutive_losses}")
        else:
            self.consecutive_losses = 0
            log.info(f"BASKET WIN | P&L: {pnl:.2f} | Daily Total: {self.daily_pnl:.2f}")
    
    def check_floating_loss_limit(self) -> None:
        """Check and act on floating loss limit"""
        pnl = self.position_manager.floating_buy_pnl()
        log.info(f"FLOATING BUY PNL={pnl:.2f}")
        
        if pnl <= self.config.floating_loss_limit:
            log.critical("FLOATING BUY LOSS LIMIT HIT")
            self.order_executor.close_all_buys()
            self.record_basket_result(pnl)


# =========================================================
# TRADING STRATEGY
# =========================================================
class GoldGridStrategy:
    """Main trading strategy implementation"""
    
    def __init__(self, config: TradingConfig):
        self.config = config
        self.position_manager = PositionManager(config.symbol)
        self.order_executor = OrderExecutor(config, self.position_manager)
        self.market_analyzer = MarketAnalyzer(config)
        self.risk_manager = RiskManager(config, self.position_manager, self.order_executor)
        self.basket_manager = BasketManager(config, self.position_manager, self.order_executor)
        self.lot_index = 0
    
    def validate_entry_conditions(
        self,
        df: pd.DataFrame,
        price: float,
        regime: VolatilityRegime,
        ema_fast: pd.Series,
        ema_slow: pd.Series
    ) -> Tuple[bool, List[str]]:
        """Validate all entry conditions with regime awareness"""
        allow_entry = True
        blocks = []
        
        # Check resistance (improved detection)
        resistance = self.market_analyzer.get_immediate_resistance(df)
        if abs(price - resistance) <= 2:
            allow_entry = False
            blocks.append(f"near_resistance_{resistance:.2f}")
        
        # Check trading session
        session_ok, session_msg = self.market_analyzer.is_trading_session_allowed()
        if not session_ok:
            allow_entry = False
            blocks.append(session_msg)
        
        # Check max positions (regime-dependent)
        pos_count = self.position_manager.position_count()
        if regime == VolatilityRegime.EXTREME and pos_count >= 3:
            allow_entry = False
            blocks.append("extreme_vol_limit")
        elif pos_count >= self.config.max_positions:
            allow_entry = False
            blocks.append("max_positions")
        
        # Check spread
        if not self.market_analyzer.check_spread():
            allow_entry = False
            blocks.append("spread")
        
        # Check cooldown
        if time.time() - self.order_executor.last_entry_time < self.config.cooldown_sec:
            allow_entry = False
            blocks.append("cooldown")
        
        # Regime-specific checks
        if regime in (VolatilityRegime.MEDIUM, VolatilityRegime.HIGH, VolatilityRegime.EXTREME):
            if ema_fast.iloc[-1] < ema_slow.iloc[-1]:
                allow_entry = False
                blocks.append("trend")
        
        if regime in (VolatilityRegime.HIGH, VolatilityRegime.EXTREME):
            if self.market_analyzer.check_heavy_sell_volume(df):
                allow_entry = False
                blocks.append("heavy_vol")
            if not self.market_analyzer.check_volume_exhaustion(df):
                allow_entry = False
                blocks.append("vol_not_exhausted")
        
        if regime == VolatilityRegime.EXTREME:
            if self.market_analyzer.check_price_drop_speed():
                allow_entry = False
                blocks.append("downspeed")
        
        return allow_entry, blocks
    
    def handle_grid_entry(
        self,
        df: pd.DataFrame,
        price: float,
        grid_step: float,
        pos_count: int,
        allow_entry: bool,
        regime: VolatilityRegime
    ) -> None:
        """Handle grid entry with ANTI-MARTINGALE sizing"""
        # First position - with trend filter
        if pos_count == 0 and allow_entry:
            if self.market_analyzer.is_trend_up(df, has_position=False):
                log.info("FIRST ENTRY BLOCKED | Waiting for uptrend confirmation")
                return
            
            # Get anti-martingale size
            lot_size = self.market_analyzer.get_anti_martingale_size(self.lot_index, regime)
            
            if lot_size > 0 and self.order_executor.execute_buy(lot_size):
                self.lot_index += 1
                self.basket_manager.basket_active = True
                log.info(f"FIRST ENTRY | Regime={regime.value} | Size={lot_size}")
            return
        
        # Additional positions
        if pos_count > 0 and allow_entry and self.lot_index < self.config.max_positions:
            last_price = self.position_manager.last_buy_price()
            
            if last_price > 0 and price <= last_price - grid_step:
                bullish_candle = df['close'].iloc[-1] > df['open'].iloc[-1]
                
                # Extra protection for high volatility
                if regime in (VolatilityRegime.HIGH, VolatilityRegime.EXTREME):
                    if not bullish_candle:
                        log.info("STACK BLOCKED | waiting bullish confirmation in high vol")
                        return
                
                # Get anti-martingale size (DECREASES with depth)
                lot_size = self.market_analyzer.get_anti_martingale_size(self.lot_index, regime)
                
                if lot_size > 0 and self.order_executor.execute_buy(lot_size):
                    self.lot_index += 1
                    log.info(f"ADDED POSITION {self.lot_index} | Regime={regime.value} | Size={lot_size}")
    
    def run(self) -> None:
        """Main trading loop with regime-adaptive logic"""
        log.info("GOLD GRID BOT STARTED - QUANTITATIVE EDITION")
        
        while True:
            # Check daily limits FIRST
            if not self.risk_manager.check_daily_limits():
                log.critical("DAILY LIMITS EXCEEDED - Bot paused for today")
                time.sleep(300)
                continue
            
            # Risk check
            self.risk_manager.check_floating_loss_limit()
            
            # Get market data
            rates = mt5.copy_rates_from_pos(self.config.symbol, self.config.timeframe, 0, 120)
            if rates is None or len(rates) < 50:
                time.sleep(1)
                continue
            
            # Prepare dataframe
            df = pd.DataFrame(rates)
            df['vol'] = df['tick_volume']
            df['vol_ema'] = TechnicalIndicators.volume_ema(df)
            
            # Calculate indicators
            close = df['close']
            ema_fast = TechnicalIndicators.ema(close, 3)
            ema_slow = TechnicalIndicators.ema(close, 5)
            atr = TechnicalIndicators.atr(df, 5)
            
            # DETECT VOLATILITY REGIME
            regime = self.market_analyzer.detect_volatility_regime(df)
            
            # Reset lot index if no positions
            pos_count = self.position_manager.position_count()
            if pos_count == 0:
                self.lot_index = 0
            
            # Current state
            price = close.iloc[-1]
            
            # Validate entry conditions (regime-aware)
            allow_entry, blocks = self.validate_entry_conditions(
                df, price, regime, ema_fast, ema_slow
            )
            
            # Calculate ADAPTIVE grid step (inverse volatility)
            grid_step = self.market_analyzer.calculate_adaptive_grid(regime, atr.iloc[-1], price)
            
            # Log status with regime
            log.info(
                f"PRICE={price:.2f} IDX={self.lot_index} REGIME={regime.value} "
                f"GRID={grid_step:.2f} ALLOW={allow_entry} BLOCKS={blocks}"
            )
            
            # Handle entry with anti-martingale
            self.handle_grid_entry(df, price, grid_step, pos_count, allow_entry, regime)
            
            time.sleep(1)


# =========================================================
# MT5 INITIALIZATION
# =========================================================
def init_mt5(config: TradingConfig) -> None:
    """Initialize MT5 connection"""
    if not mt5.initialize(
        path=config.mt5_path,
        login=config.mt5_login,
        password=config.mt5_password,
        server=config.mt5_server
    ):
        raise RuntimeError(mt5.last_error())
    
    if not mt5.symbol_select(config.symbol, True):
        raise RuntimeError("Symbol select failed")
    
    info = mt5.symbol_info(config.symbol)
    if info.trade_mode != mt5.SYMBOL_TRADE_MODE_FULL:
        raise RuntimeError("Trading disabled for symbol")
    
    log.info(
        f"CONNECTED | {config.symbol} "
        f"min_lot={info.volume_min} step={info.volume_step}"
    )


# =========================================================
# MAIN ENTRY POINT
# =========================================================
if __name__ == "__main__":
    # Initialize configuration
    config = TradingConfig()
    
    # Initialize MT5
    init_mt5(config)
    
    # Create strategy
    strategy = GoldGridStrategy(config)
    
    # Start basket watcher in background with risk manager reference
    Thread(target=strategy.basket_manager.watch_basket, args=(strategy.risk_manager,), daemon=True).start()
    
    # Run main strategy
    strategy.run()

# Made with Bob
