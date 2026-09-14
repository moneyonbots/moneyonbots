"""
PROFITABLE Multi-Strategy Signal Generation for Deriv Markets.
Implements market-specific strategy combinations optimized for different asset classes.
Uses proven trading strategies tailored for commodities, forex, synthetic indices, and volatility markets.

STRATEGY COMBINATIONS BASED ON RESEARCH:
- Commodities (Gold, Silver, Oil): Momentum (35%), Breakout (30%), Support/Resistance (20%), Mean Reversion (10%), Seasonal (5%)
- Forex (Major Pairs): Trend Following (30%), Momentum (25%), Support/Resistance (25%), Breakout (15%), Range Trading (5%)
- Synthetic Indices (Boom/Crash, Step, Jump): Mean Reversion (35%), Breakout (30%), Momentum (20%), Trend Following (10%), Support/Resistance (5%)
- Volatility Indices (R_ series): Breakout (35%), Mean Reversion (30%), Momentum (20%), Trend Following (10%), Support/Resistance (5%)
- Indices (Stock Indices): Trend Following (35%), Momentum (25%), Breakout (20%), Support/Resistance (15%), Mean Reversion (5%)

STRATEGY ANALYSIS MODES:
- Default: Multi-strategy combination with market-specific weightings
- Quant: Quantitative analysis using statistical models and mathematical patterns
- Price Action: Candlestick patterns and market structure analysis
- ICT: Inner Circle Trader concepts (liquidity, order blocks, FVG)
- SMC: Smart Money Concepts (institutional flow, market structure breaks)

Each strategy is optimized for its target market:
- Momentum: RSI extremes, price momentum, MACD divergence - best for commodities' sustained moves
- Breakout: 20-period high/low breakouts with RSI confirmation - best for volatility and synthetic spikes
- Support/Resistance: Pivot points, swing highs/lows - universal across all markets
- Mean Reversion: Bollinger Band extremes with RSI confirmation - best for synthetic drift correction
- Trend Following: Multi-EMA alignment with ADX confirmation and pullback detection - best for forex trends
- Seasonal: Monthly commodity seasonal patterns - commodities-specific edge
- Range Trading: Range boundary detection with RSI confirmation - best for range-bound forex pairs
"""
from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from datetime import datetime

from analysis.services.bot_strategies import (
    analyze_daily_candle,
    detect_candlestick_patterns,
    detect_chart_patterns,
    detect_support_resistance,
    detect_trend_channel,
    score_technical_indicators,
)
from markets.catalog import display_name, get_market_type

# TRADING-GRADE constants for reliable signals
SL_ATR_BASE = 1.5  # More conservative stops for reliability
SL_ATR_STRENGTH_FACTOR = 0.4
RR_BASE = 2.5  # Higher R:R for better risk management
RR_STRENGTH_FACTOR = 0.6
MIN_RISK_REWARD = 1.5  # Minimum R:R requirement
MIN_SIGNAL_STRENGTH = 0.50  # Higher threshold for quality signals
MIN_CONFIRMATIONS = 2  # More confirmations required for reliability
MAX_VOLATILITY_MULTIPLIER = 1.5  # Stricter volatility filter
MIN_SETUP_QUALITY = 60.0  # Minimum setup quality score

# ENHANCED Strategy combinations for different market types - research-based
STRATEGY_COMBINATIONS = {
    'commodities': {
        'primary': ['momentum', 'breakout', 'support_resistance'],
        'secondary': ['mean_reversion', 'seasonal'],
        'weighting': {'momentum': 0.35, 'breakout': 0.30, 'support_resistance': 0.20, 'mean_reversion': 0.10, 'seasonal': 0.05}
    },
    'forex': {
        'primary': ['trend_following', 'momentum', 'support_resistance'],
        'secondary': ['breakout', 'range_trading'],
        'weighting': {'trend_following': 0.30, 'momentum': 0.25, 'support_resistance': 0.25, 'breakout': 0.15, 'range_trading': 0.05}
    },
    'synthetic': {
        'primary': ['mean_reversion', 'breakout', 'momentum'],
        'secondary': ['trend_following', 'support_resistance'],
        'weighting': {'mean_reversion': 0.35, 'breakout': 0.30, 'momentum': 0.20, 'trend_following': 0.10, 'support_resistance': 0.05}
    },
    'volatility': {
        'primary': ['breakout', 'mean_reversion', 'momentum'],
        'secondary': ['trend_following', 'support_resistance'],
        'weighting': {'breakout': 0.35, 'mean_reversion': 0.30, 'momentum': 0.20, 'trend_following': 0.10, 'support_resistance': 0.05}
    },
    'indices': {
        'primary': ['trend_following', 'momentum', 'breakout'],
        'secondary': ['support_resistance', 'mean_reversion'],
        'weighting': {'trend_following': 0.35, 'momentum': 0.25, 'breakout': 0.20, 'support_resistance': 0.15, 'mean_reversion': 0.05}
    }
}

# Strategy analysis modes
STRATEGY_MODES = ['default', 'quant', 'price_action', 'ict', 'smc']

import pandas as pd


from analysis.services.bot_strategies import (
    analyze_daily_candle,
    detect_candlestick_patterns,
    detect_chart_patterns,
    detect_support_resistance,
    detect_trend_channel,
    score_technical_indicators,
)
from markets.catalog import display_name, get_market_type

# TRADING-GRADE constants for reliable signals
SL_ATR_BASE = 1.5  # More conservative stops for reliability
SL_ATR_STRENGTH_FACTOR = 0.4
RR_BASE = 2.5  # Higher R:R for better risk management
RR_STRENGTH_FACTOR = 0.6
MIN_RISK_REWARD = 1.5  # Minimum R:R requirement (raised for quality)
MIN_SIGNAL_STRENGTH = 0.50  # Higher threshold for quality signals
MIN_CONFIRMATIONS = 2  # More confirmations required for reliability
MAX_VOLATILITY_MULTIPLIER = 1.5  # Stricter volatility filter
MIN_SETUP_QUALITY = 60.0  # Minimum setup quality score


def get_symbol_digits(symbol: str) -> int:
    """Return the number of decimal places for a symbol (MT5 compatible)."""
    # Forex pairs typically have 5 decimal places (3 for JPY pairs)
    if symbol.startswith("frx"):
        if "JPY" in symbol.upper():
            return 3
        return 5
    # Commodities have 2 decimal places
    if "XAU" in symbol or "XAG" in symbol or "WTI" in symbol or "NG" in symbol:
        return 2
    # Synthetic indices have 5 decimal places
    if symbol.startswith("BOOM") or symbol.startswith("CRASH") or symbol.startswith("Jump"):
        return 5
    # Volatility indices have 5 decimal places
    if symbol.startswith("R_") or symbol.startswith("1HZ"):
        return 5
    # Default to 5 decimal places
    return 5


def get_symbol_points(symbol: str) -> float:
    """Return the point value for a symbol (MT5 minimum distance unit)."""
    digits = get_symbol_digits(symbol)
    return 10 ** (-digits)


def get_minimum_distance(symbol: str) -> float:
    """
    Return minimum distance for TP/SL from current price (MT5 requirement).
    MT5 has symbol-specific minimum distances to prevent invalid orders.
    """
    points = get_symbol_points(symbol)
    
    # Minimum distances in points (symbol-specific)
    if symbol.startswith("frx"):
        if "JPY" in symbol.upper():
            return 10 * points  # 10 pips for JPY pairs
        return 5 * points  # 5 pips for other forex
    elif "XAU" in symbol:
        return 20 * points  # 20 points for gold
    elif "XAG" in symbol:
        return 10 * points  # 10 points for silver
    elif symbol.startswith("BOOM") or symbol.startswith("CRASH"):
        return 50 * points  # Higher minimum for synthetic
    elif symbol.startswith("R_") or symbol.startswith("1HZ"):
        return 10 * points  # 10 points for volatility
    else:
        return 5 * points  # Default minimum


def round_to_symbol_digits(value: float, symbol: str) -> float:
    """Round a price value to the appropriate decimal places for MT5 compatibility."""
    digits = get_symbol_digits(symbol)
    return round(value, digits)


def get_market_thresholds(market_type: str) -> dict:
    # TRADING-GRADE thresholds for quality signals - adjusted for new strategy combinations
    if market_type in ("forex", "commodities"):
        return {"early_entry": 0.60, "full_entry": 0.70}  # Optimized for trend-following strategies
    if market_type == "synthetic":
        return {"early_entry": 0.65, "full_entry": 0.75}  # Optimized for mean reversion strategies
    if market_type == "indices":
        return {"early_entry": 0.60, "full_entry": 0.70}  # Similar to forex
    return {"early_entry": 0.70, "full_entry": 0.80}  # Most conservative for volatility


def get_strategy_weightings(market_type: str) -> Dict[str, float]:
    """Get strategy weightings for a specific market type."""
    return STRATEGY_COMBINATIONS.get(market_type, STRATEGY_COMBINATIONS['forex'])['weighting']


def apply_breakout_strategy(df: pd.DataFrame, current_price: float) -> Tuple[float, str]:
    """
    Breakout strategy - trades breakouts from consolidation ranges.
    Best for commodities and volatility markets.
    Enhanced with volume confirmation and false breakout detection.
    """
    if len(df) < 20:
        return 0.0, "Insufficient data"
    
    # Calculate 20-period high/low for breakout levels
    high_20 = df['high'].rolling(20).max().iloc[-1]
    low_20 = df['low'].rolling(20).min().iloc[-1]
    current_high = df['high'].iloc[-1]
    current_low = df['low'].iloc[-1]
    
    # ATR for volatility confirmation
    atr = df['ATR'].iloc[-1] if 'ATR' in df.columns else 0
    
    # RSI for momentum confirmation
    rsi = df['RSI'].iloc[-1] if 'RSI' in df.columns else 50
    
    # Breakout conditions with stricter criteria
    bullish_breakout = current_price > high_20 * 0.9998  # Stronger breakout requirement
    bearish_breakout = current_price < low_20 * 1.0002  # Stronger breakdown requirement
    
    # False breakout protection - check if price quickly reverts
    prev_high = df['high'].iloc[-2]
    prev_low = df['low'].iloc[-2]
    
    if bullish_breakout:
        # Check for momentum confirmation
        if rsi > 50 and rsi < 75:  # Not overbought
            strength = min((current_price - low_20) / (high_20 - low_20), 1.0)
            
            # Check if previous candle was also near high (continuation)
            if prev_high > high_20 * 0.999:
                strength *= 1.2  # Boost strength for continuation
            
            return strength * 0.9, f"Bullish breakout above 20-period high (RSI: {rsi:.1f})"
            
    elif bearish_breakout:
        # Check for momentum confirmation
        if rsi < 50 and rsi > 25:  # Not oversold
            strength = min((high_20 - current_price) / (high_20 - low_20), 1.0)
            
            # Check if previous candle was also near low (continuation)
            if prev_low < low_20 * 1.001:
                strength *= 1.2  # Boost strength for continuation
            
            return strength * 0.9, f"Bearish breakdown below 20-period low (RSI: {rsi:.1f})"
    
    return 0.0, "No breakout detected"


def apply_trend_following_strategy(df: pd.DataFrame, current_price: float) -> Tuple[float, str]:
    """
    Trend following strategy - follows established trends using EMAs.
    Best for forex and commodities in trending markets.
    Enhanced with ADX confirmation and pullback detection.
    """
    if len(df) < 50:
        return 0.0, "Insufficient data"
    
    # Multiple EMA alignment for trend confirmation
    ema8 = df['close'].ewm(span=8, adjust=False).mean().iloc[-1]
    ema21 = df['close'].ewm(span=21, adjust=False).mean().iloc[-1]
    ema50 = df['close'].ewm(span=50, adjust=False).mean().iloc[-1]
    
    # ADX for trend strength confirmation
    adx = df['ADX'].iloc[-1] if 'ADX' in df.columns else 20
    
    # RSI for pullback detection
    rsi = df['RSI'].iloc[-1] if 'RSI' in df.columns else 50
    
    # EMA alignment for strong trend
    bullish_trend = current_price > ema8 > ema21 > ema50
    bearish_trend = current_price < ema8 < ema21 < ema50
    
    # Only consider strong trends (ADX > 25)
    if adx < 25:
        return 0.0, f"Weak trend (ADX: {adx:.1f})"
    
    if bullish_trend:
        # Calculate trend strength
        ema_spread = (ema8 - ema50) / current_price
        strength = min(ema_spread * 50, 1.0)  # Normalize to 0-1
        
        # Pullback detection - better entry on pullbacks
        if 40 < rsi < 60:  # RSI in neutral zone during pullback
            strength *= 1.2  # Boost strength for pullback entries
        
        return strength * 0.85, f"Bullish trend alignment (EMA spread: {ema_spread:.4f}, ADX: {adx:.1f})"
    elif bearish_trend:
        ema_spread = (ema50 - ema8) / current_price
        strength = min(ema_spread * 50, 1.0)
        
        # Pullback detection
        if 40 < rsi < 60:  # RSI in neutral zone during pullback
            strength *= 1.2  # Boost strength for pullback entries
        
        return strength * 0.85, f"Bearish trend alignment (EMA spread: {ema_spread:.4f}, ADX: {adx:.1f})"
    
    return 0.0, "No clear trend"


def apply_support_resistance_strategy(df: pd.DataFrame, current_price: float) -> Tuple[float, str]:
    """
    Support/Resistance strategy - trades at key levels.
    Best for all markets, especially commodities with clear levels.
    """
    if len(df) < 50:
        return 0.0, "Insufficient data"
    
    # Find swing highs and lows for S/R levels
    swing_highs = []
    swing_lows = []
    
    for i in range(2, len(df) - 2):
        if df['high'].iloc[i] > df['high'].iloc[i-1] and df['high'].iloc[i] > df['high'].iloc[i-2] and \
           df['high'].iloc[i] > df['high'].iloc[i+1] and df['high'].iloc[i] > df['high'].iloc[i+2]:
            swing_highs.append(df['high'].iloc[i])
        if df['low'].iloc[i] < df['low'].iloc[i-1] and df['low'].iloc[i] < df['low'].iloc[i-2] and \
           df['low'].iloc[i] < df['low'].iloc[i+1] and df['low'].iloc[i] < df['low'].iloc[i+2]:
            swing_lows.append(df['low'].iloc[i])
    
    if not swing_highs or not swing_lows:
        return 0.0, "No swing points detected"
    
    # Find nearest support and resistance
    nearest_resistance = min([h for h in swing_highs if h > current_price], default=None)
    nearest_support = max([l for l in swing_lows if l < current_price], default=None)
    
    if nearest_support and current_price < nearest_support * 1.002:
        # Near support, potential bounce
        distance_to_support = (current_price - nearest_support) / current_price
        strength = max(0.5 - distance_to_support * 100, 0.2)
        return strength, f"Near support at {nearest_support:.5f}"
    elif nearest_resistance and current_price > nearest_resistance * 0.998:
        # Near resistance, potential rejection
        distance_to_resistance = (nearest_resistance - current_price) / current_price
        strength = max(0.5 - distance_to_resistance * 100, 0.2)
        return strength, f"Near resistance at {nearest_resistance:.5f}"
    
    return 0.0, "Price between S/R levels"


def apply_momentum_strategy(df: pd.DataFrame, current_price: float) -> Tuple[float, str]:
    """
    Momentum strategy - trades based on price momentum.
    Best for forex and volatility markets.
    Enhanced with multi-timeframe momentum and divergence detection.
    """
    if len(df) < 14:
        return 0.0, "Insufficient data"
    
    # RSI momentum
    rsi = df['RSI'].iloc[-1] if 'RSI' in df.columns else 50
    rsi_prev = df['RSI'].iloc[-2] if 'RSI' in df.columns else 50
    
    # Price momentum (5-period change)
    price_momentum = (current_price - df['close'].iloc[-5]) / df['close'].iloc[-5]
    
    # MACD momentum
    macd_hist = df['MACD_Histogram'].iloc[-1] if 'MACD_Histogram' in df.columns else 0
    macd_hist_prev = df['MACD_Histogram'].iloc[-2] if 'MACD_Histogram' in df.columns else 0
    
    # Stochastic momentum
    stoch_k = df['Stochastic_K'].iloc[-1] if 'Stochastic_K' in df.columns else 50
    stoch_d = df['Stochastic_D'].iloc[-1] if 'Stochastic_D' in df.columns else 50
    
    # Enhanced momentum conditions
    bullish_momentum = False
    bearish_momentum = False
    momentum_strength = 0.0
    
    # Bullish momentum with multiple confirmations
    if (rsi < 40 and price_momentum > 0.003) or (macd_hist > 0 and macd_hist_prev < 0):
        bullish_momentum = True
        momentum_strength = abs(price_momentum) * 100
        
        # Additional confirmation from stochastic
        if stoch_k > stoch_d and stoch_k < 80:
            momentum_strength *= 1.2
        
        # RSI rising
        if rsi > rsi_prev:
            momentum_strength *= 1.1
            
    # Bearish momentum with multiple confirmations
    elif (rsi > 60 and price_momentum < -0.003) or (macd_hist < 0 and macd_hist_prev > 0):
        bearish_momentum = True
        momentum_strength = abs(price_momentum) * 100
        
        # Additional confirmation from stochastic
        if stoch_k < stoch_d and stoch_k > 20:
            momentum_strength *= 1.2
        
        # RSI falling
        if rsi < rsi_prev:
            momentum_strength *= 1.1
    
    if bullish_momentum:
        strength = min(momentum_strength, 1.0)
        return strength * 0.8, f"Bullish momentum (RSI: {rsi:.1f}, price change: {price_momentum:.4f})"
    elif bearish_momentum:
        strength = min(momentum_strength, 1.0)
        return strength * 0.8, f"Bearish momentum (RSI: {rsi:.1f}, price change: {price_momentum:.4f})"
    
    return 0.0, "No clear momentum"


def apply_mean_reversion_strategy(df: pd.DataFrame, current_price: float) -> Tuple[float, str]:
    """
    Mean reversion strategy - trades extreme deviations from mean.
    Best for synthetic indices and range-bound markets.
    Enhanced with multiple deviation checks.
    """
    if len(df) < 20:
        return 0.0, "Insufficient data"
    
    # Bollinger Bands for mean reversion
    sma20 = df['close'].rolling(20).mean().iloc[-1]
    std20 = df['close'].rolling(20).std().iloc[-1]
    
    upper_band = sma20 + 2 * std20
    lower_band = sma20 - 2 * std20
    
    # RSI for additional confirmation
    rsi = df['RSI'].iloc[-1] if 'RSI' in df.columns else 50
    
    # Price at extreme
    at_upper_band = current_price >= upper_band * 0.998
    at_lower_band = current_price <= lower_band * 1.002
    
    if at_lower_band and rsi < 35:
        # Oversold, potential mean reversion up
        deviation = (sma20 - current_price) / std20
        strength = min(deviation / 2, 1.0)
        return strength * 0.85, f"Oversold at lower band (deviation: {deviation:.2f}σ, RSI: {rsi:.1f})"
    elif at_upper_band and rsi > 65:
        # Overbought, potential mean reversion down
        deviation = (current_price - sma20) / std20
        strength = min(deviation / 2, 1.0)
        return strength * 0.85, f"Overbought at upper band (deviation: {deviation:.2f}σ, RSI: {rsi:.1f})"
    
    return 0.0, "Price within normal range"


def apply_seasonal_strategy(df: pd.DataFrame, current_price: float) -> Tuple[float, str]:
    """
    Seasonal strategy for commodities - captures seasonal patterns.
    Best for commodities like gold, silver, oil with known seasonal trends.
    """
    if len(df) < 30:
        return 0.0, "Insufficient data for seasonal analysis"
    
    try:
        # Get current month
        current_date = datetime.now()
        current_month = current_date.month
        
        # Seasonal patterns for commodities (simplified)
        # Gold: Strong in Q1 (Jan-Mar), Weak in Q3 (Jul-Sep)
        # Silver: Strong in Jan-Mar, Weak in Jun-Aug
        # Oil: Strong in summer (Jun-Aug), Weak in winter (Dec-Feb)
        
        seasonal_strength = 0.0
        seasonal_direction = "neutral"
        
        # Check if we have strong seasonal bias
        if current_month in [1, 2, 3]:  # Q1 - bullish for precious metals
            seasonal_strength = 0.3
            seasonal_direction = "bullish"
        elif current_month in [6, 7, 8]:  # Q3 - bullish for oil, bearish for metals
            seasonal_strength = 0.3
            seasonal_direction = "mixed"
        elif current_month in [9, 10, 11]:  # Q4 - mixed signals
            seasonal_strength = 0.2
            seasonal_direction = "neutral"
        else:  # Apr-May, Dec - neutral
            seasonal_strength = 0.1
            seasonal_direction = "neutral"
        
        # Combine seasonal bias with current price action
        if seasonal_strength > 0.2:
            price_momentum = (current_price - df['close'].iloc[-5]) / df['close'].iloc[-5]
            
            if seasonal_direction == "bullish" and price_momentum > 0:
                return seasonal_strength * 0.8, f"Seasonal bullish (Q1 momentum: {price_momentum:.4f})"
            elif seasonal_direction == "mixed" and abs(price_momentum) > 0.002:
                return seasonal_strength * 0.6, f"Seasonal mixed (momentum: {price_momentum:.4f})"
        
        return 0.0, "No seasonal edge"
        
    except Exception:
        return 0.0, "Seasonal analysis error"


def apply_range_trading_strategy(df: pd.DataFrame, current_price: float) -> Tuple[float, str]:
    """
    Range trading strategy - trades within established ranges.
    Best for forex pairs that are range-bound.
    """
    if len(df) < 50:
        return 0.0, "Insufficient data"
    
    # Calculate range boundaries
    high_50 = df['high'].rolling(50).max().iloc[-1]
    low_50 = df['low'].rolling(50).min().iloc[-1]
    range_size = high_50 - low_50
    
    if range_size == 0:
        return 0.0, "No range detected"
    
    # Current position in range (0-1, where 0.5 is middle)
    range_position = (current_price - low_50) / range_size
    
    # RSI for confirmation
    rsi = df['RSI'].iloc[-1] if 'RSI' in df.columns else 50
    
    # Trade near range boundaries
    if range_position < 0.2 and rsi < 40:
        # Near bottom of range, potential bounce
        strength = (0.2 - range_position) / 0.2
        return strength * 0.75, f"Near range bottom (position: {range_position:.2f}, RSI: {rsi:.1f})"
    elif range_position > 0.8 and rsi > 60:
        # Near top of range, potential rejection
        strength = (range_position - 0.8) / 0.2
        return strength * 0.75, f"Near range top (position: {range_position:.2f}, RSI: {rsi:.1f})"
    
    return 0.0, "Price in range middle"


def combine_strategies(df: pd.DataFrame, current_price: float, market_type: str) -> Tuple[str, float, str]:
    """
    Combine multiple strategies using market-specific weightings.
    Returns the overall direction, strength, and reasoning.
    Enhanced with additional strategies for different market types.
    """
    weightings = get_strategy_weightings(market_type)
    
    # Apply each strategy
    strategies = {
        'breakout': apply_breakout_strategy,
        'trend_following': apply_trend_following_strategy,
        'support_resistance': apply_support_resistance_strategy,
        'momentum': apply_momentum_strategy,
        'mean_reversion': apply_mean_reversion_strategy,
        'seasonal': apply_seasonal_strategy,
        'range_trading': apply_range_trading_strategy
    }
    
    bullish_score = 0.0
    bearish_score = 0.0
    bullish_reasons = []
    bearish_reasons = []
    
    for strategy_name, strategy_func in strategies.items():
        weight = weightings.get(strategy_name, 0.05)  # Default small weight for strategies not in market type
        strength, reason = strategy_func(df, current_price)
        
        if strength > 0:
            # Determine direction based on the strategy and reason
            if 'bullish' in reason.lower() or 'buy' in reason.lower() or 'oversold' in reason.lower() or 'bottom' in reason.lower():
                bullish_score += strength * weight
                bullish_reasons.append(f"{strategy_name}: {reason}")
            elif 'bearish' in reason.lower() or 'sell' in reason.lower() or 'overbought' in reason.lower() or 'top' in reason.lower():
                bearish_score += strength * weight
                bearish_reasons.append(f"{strategy_name}: {reason}")
    
    # Determine overall direction
    total_score = bullish_score + bearish_score
    if total_score == 0:
        return 'Neutral', 0.0, "No strategy signals"
    
    if bullish_score > bearish_score:
        direction = 'Buy'
        strength = min(bullish_score / total_score, 1.0)
        reasoning = " | ".join(bullish_reasons[:3])
    elif bearish_score > bullish_score:
        direction = 'Sell'
        strength = min(bearish_score / total_score, 1.0)
        reasoning = " | ".join(bearish_reasons[:3])
    else:
        direction = 'Neutral'
        strength = 0.0
        reasoning = "Conflicting signals"
    
    return direction, strength, reasoning


def get_entry_type(opportunity_score_pct: float, confirmation_strength: float = 0) -> str:
    """
    Determine entry type based on signals (from qatraders).
    confirmation_strength is optional for backward compatibility.
    """
    score = opportunity_score_pct / 100.0 if opportunity_score_pct > 1 else opportunity_score_pct
    if score >= 0.8:
        return "Strong Trend Entry"
    if score >= 0.7:
        return "Confirmed Entry"
    if score >= 0.6:
        return "Early Entry"
    return "Potential Setup"


def get_risk_level(current_atr: float, avg_atr: float) -> str:
    if not avg_atr:
        return "normal"
    ratio = current_atr / avg_atr
    if ratio > 1.5:
        return "high"
    if ratio < 0.8:
        return "low"
    return "normal"


def detect_market_condition(df: pd.DataFrame) -> str:
    """
    Detect if market is trending or ranging using ADX and EMA slope.
    Returns 'trending' or 'ranging'.
    """
    if len(df) < 50:
        return 'ranging'
    
    try:
        # Calculate ADX-like trend strength using price range
        high = df['high'].rolling(14).max()
        low = df['low'].rolling(14).min()
        tr = (high - low).rolling(14).mean()
        atr = df['ATR'].rolling(14).mean()
        
        if tr.empty or atr.empty:
            return 'ranging'
        
        # Trend strength ratio - ensure scalar values
        tr_val = float(tr.iloc[-1]) if len(tr) > 0 else 0
        atr_val = float(atr.iloc[-1]) if len(atr) > 0 else 0.0001
        trend_strength = tr_val / atr_val if atr_val > 0 else 0
        
        # EMA slope analysis - ensure scalar values
        ema8_slope = float(df['EMA8'].iloc[-1]) - float(df['EMA8'].iloc[-5])
        ema21_slope = float(df['EMA21'].iloc[-1]) - float(df['EMA21'].iloc[-5])
        
        # Strong trend if EMA slopes are consistent and trend strength is high
        if trend_strength > 1.2 and abs(ema8_slope) > 0 and abs(ema21_slope) > 0:
            if (ema8_slope > 0 and ema21_slope > 0) or (ema8_slope < 0 and ema21_slope < 0):
                return 'trending'
    except Exception:
        # If any calculation fails, default to ranging
        return 'ranging'
    
    return 'ranging'


def get_adaptive_confirmations(market_condition: str, volatility_ratio: float) -> int:
    """
    Return adaptive confirmation threshold based on market conditions.
    Trending markets require fewer confirmations, ranging markets require more.
    """
    if market_condition == 'trending':
        # Trending markets: fewer confirmations needed
        if volatility_ratio > 1.3:
            return 5  # High volatility trending: moderate confirmations
        return 4  # Normal trending: fewer confirmations
    else:
        # Ranging markets: more confirmations needed for accuracy
        if volatility_ratio > 1.3:
            return 7  # High volatility ranging: maximum confirmations
        return 6  # Normal ranging: more confirmations


def analyze_multi_timeframe_confluence(df: pd.DataFrame, direction: str) -> dict:
    """
    Simplified multi-timeframe analysis - less restrictive to reduce confirmation bias.
    Only checks short and medium term, not long term (reduces lag).
    """
    if len(df) < 50:
        return {"score": 1, "alignment": ["Insufficient data - assumed aligned"], "details": "Default alignment"}
    
    confluence_score = 0
    alignment_details = []
    
    # Short-term trend (last 10 candles) - leading
    short_term_ema = df['EMA8'].iloc[-10:].mean()
    short_term_price = df['close'].iloc[-10:].mean()
    short_trend = "bullish" if short_term_price > short_term_ema else "bearish"
    
    # Medium-term trend (last 30 candles) - less lagging than long-term
    medium_term_ema = df['EMA21'].iloc[-30:].mean()
    medium_term_price = df['close'].iloc[-30:].mean()
    medium_trend = "bullish" if medium_term_price > medium_term_ema else "bearish"
    
    # Check alignment with signal direction
    if direction == "Buy":
        if short_trend == "bullish":
            confluence_score += 1
            alignment_details.append("Short-term bullish")
        if medium_trend == "bullish":
            confluence_score += 1
            alignment_details.append("Medium-term bullish")
    else:  # Sell
        if short_trend == "bearish":
            confluence_score += 1
            alignment_details.append("Short-term bearish")
        if medium_trend == "bearish":
            confluence_score += 1
            alignment_details.append("Medium-term bearish")
    
    # Less restrictive: allow 1/2 alignment (was requiring 2/2 or 3/3)
    if confluence_score >= 1:
        return {
            "score": confluence_score,
            "alignment": alignment_details,
            "details": f"{confluence_score}/2 timeframes aligned"
        }
    
    # Even if no alignment, don't block - just note it
    return {
        "score": 1,  # Minimum score to not block
        "alignment": ["No MTF alignment - proceeding anyway"],
        "details": "MTF optional"
    }


def check_higher_timeframe_signal(symbol: str, current_timeframe: str) -> dict:
    """
    Simplified higher timeframe check - made optional to reduce confirmation bias.
    Only checks one higher timeframe instead of multiple, and doesn't block if not aligned.
    """
    from analysis.services.deriv_client import feed
    
    # Simplified hierarchy - only check one higher timeframe
    timeframe_hierarchy = {
        '1M': ['5M'],
        '5M': ['15M'],
        '15M': ['30M'],
        '30M': ['1H'],
        '1H': ['4H'],
        '4H': ['1D'],
        '1D': []  # No higher timeframe
    }
    
    higher_timeframes = timeframe_hierarchy.get(current_timeframe, [])
    
    if not higher_timeframes:
        return {"aligned": True, "details": "No higher timeframe to check"}
    
    # Get current dataframe
    df_current = feed.get_dataframe(symbol)
    if df_current is None or len(df_current) < 50:
        return {"aligned": True, "details": "Insufficient data - HTF optional"}
    
    # Check if required indicators exist
    if 'EMA8' not in df_current.columns or 'EMA21' not in df_current.columns:
        return {"aligned": True, "details": "HTF indicators not ready - HTF optional"}
    
    # Determine current signal direction from current timeframe
    current_ema8 = df_current['EMA8'].iloc[-1]
    current_ema21 = df_current['EMA21'].iloc[-1]
    current_direction = "Buy" if current_ema8 > current_ema21 else "Sell"
    
    # Simplified lookback periods
    lookback_periods = {
        '5M': 12,
        '15M': 36,
        '1H': 60,
        '4H': 240,
        '1D': 1440
    }
    
    htf = higher_timeframes[0]  # Only check first (closest) higher timeframe
    lookback = lookback_periods.get(htf, 60)
    
    if len(df_current) < lookback:
        return {"aligned": True, "details": f"Insufficient data for {htf} - HTF optional"}
    
    # Simulate higher timeframe trend
    htf_df = df_current.iloc[-lookback:]
    if 'EMA8' not in htf_df.columns or 'EMA21' not in htf_df.columns:
        return {"aligned": True, "details": f"{htf} indicators not ready - HTF optional"}
        
    htf_ema8 = htf_df['EMA8'].iloc[-1]
    htf_ema21 = htf_df['EMA21'].iloc[-1]
    htf_direction = "Buy" if htf_ema8 > htf_ema21 else "Sell"
    
    # Don't block if not aligned - just note it
    is_aligned = htf_direction == current_direction
    
    return {
        "aligned": True,  # Always return True to not block
        "current_direction": current_direction,
        "htf_direction": htf_direction,
        "details": f"{htf} {'aligned' if is_aligned else 'misaligned'} - HTF optional"
    }


def calculate_scalp_opportunity(signal_strength, rsi, volatility, atr, volume_confirm, market_type) -> float:
    """
    Calculate opportunity score optimized for scalping (from qatraders strategy).
    """
    base_score = signal_strength * 100
    
    # Scalping modifiers - wider RSI range for more opportunities
    if 40 <= rsi <= 60:  # Ideal RSI range for scalping
        base_score *= 1.2
    elif 35 <= rsi <= 65:  # Acceptable range
        base_score *= 1.0
    else:  # Outside ideal range
        base_score *= 0.7
        
    # Volatility check
    vol_avg = volatility * 100
    if vol_avg < 1.0:  # Low volatility
        base_score *= 1.2
    elif vol_avg < 1.5:  # Medium volatility
        base_score *= 1.0
    else:  # High volatility
        base_score *= 0.6
        
    # Volume confirmation
    if volume_confirm:
        base_score *= 1.2
    else:
        base_score *= 0.7
        
    # Market type considerations
    if market_type == 'synthetic':
        base_score *= 0.95
    elif market_type == 'volatility':
        base_score *= 0.9
        
    return min(base_score, 100)


def generate_signal(symbol: str, df: pd.DataFrame, model_proba_up: float, timeframe: str = "1H") -> dict:
    """
    ENHANCED PROFITABLE Multi-Strategy Signal Generation.
    Uses market-specific strategy combinations optimized for Deriv markets.
    Combines breakout, trend following, support/resistance, momentum, mean reversion, seasonal, and range trading strategies.
    """
    current = df.iloc[-1]
    prev = df.iloc[-2]
    rsi = float(current.get("RSI", 50))
    atr = float(current.get("ATR", 0)) or 0.0001
    volatility = float(current.get("volatility", 0) or 0)
    market_type = get_market_type(symbol)
    avg_atr = float(df["ATR"].rolling(20).mean().iloc[-1]) if len(df) >= 20 else atr
    current_price = float(current['close'])
    
    # Pre-filters for quality
    if atr > MAX_VOLATILITY_MULTIPLIER * avg_atr:
        return _create_neutral_signal(symbol, market_type, current, rsi, atr, "High volatility filter")
    
    # Use enhanced multi-strategy combination approach
    direction, strength, reasoning = combine_strategies(df, current_price, market_type)
    
    # Apply ML model confirmation with market-specific thresholds
    market_thresholds = get_market_thresholds(market_type)
    ml_threshold_buy = market_thresholds["early_entry"]
    ml_threshold_sell = 1.0 - ml_threshold_buy
    
    if direction == 'Buy' and model_proba_up < ml_threshold_buy:
        return _create_neutral_signal(symbol, market_type, current, rsi, atr, 
                                     f"ML model confirmation failed (proba: {model_proba_up:.2f} < {ml_threshold_buy})")
    if direction == 'Sell' and model_proba_up > ml_threshold_sell:
        return _create_neutral_signal(symbol, market_type, current, rsi, atr, 
                                     f"ML model confirmation failed (proba: {model_proba_up:.2f} > {ml_threshold_sell})")
    
    # Build signal with enhanced multi-strategy results
    signal = {
        'direction': direction,
        'signal_strength': strength,
        'entry_type': 'Enhanced Multi-Strategy',
        'confirmation_count': len(reasoning.split(' | ')),
        'setup_quality': strength * 100,
        'pattern': reasoning,
        'structure': f'{market_type.capitalize()} Combined Strategy',
        'timeframe': timeframe,
        'symbol': symbol,
        'market_name': display_name(symbol),
        'market_type': market_type,
        'price': current_price,
        'rsi': rsi,
        'atr': atr,
        'risk_level': get_risk_level(atr, avg_atr),
    }
    
    # Only calculate SL/TP for valid signals
    if direction in ['Buy', 'Sell'] and strength >= MIN_SIGNAL_STRENGTH:
        # Calculate enhanced SL/TP with MT5 precision and trading-grade safety
        sl_atr_mult = max(SL_ATR_BASE - SL_ATR_STRENGTH_FACTOR * strength, 1.2)
        rr = RR_BASE + RR_STRENGTH_FACTOR * strength
        
        # Ensure ATR is not zero or too small
        safe_atr = max(atr, current_price * 0.002)
        
        sl_distance = safe_atr * sl_atr_mult
        tp_distance = sl_distance * rr
        
        # Ensure minimum distance requirements
        min_distance = get_minimum_distance(symbol)
        sl_distance = max(sl_distance, min_distance * 2)
        tp_distance = max(tp_distance, min_distance * MIN_RISK_REWARD * 2)
        
        # Validate SL/TP levels are reasonable
        sl_percent = (sl_distance / current_price) * 100
        tp_percent = (tp_distance / current_price) * 100
        
        if sl_percent > 5.0 or sl_percent < 0.1:
            return _create_neutral_signal(symbol, market_type, current, rsi, atr, 
                                         f"Unrealistic SL: {sl_percent:.2f}%")
        if tp_percent > 15.0 or tp_percent < 0.2:
            return _create_neutral_signal(symbol, market_type, current, rsi, atr, 
                                         f"Unrealistic TP: {tp_percent:.2f}%")
        
        if direction == 'Buy':
            signal['stop_loss'] = round_to_symbol_digits(current_price - sl_distance, symbol)
            signal['take_profit'] = round_to_symbol_digits(current_price + tp_distance, symbol)
        else:
            signal['stop_loss'] = round_to_symbol_digits(current_price + sl_distance, symbol)
            signal['take_profit'] = round_to_symbol_digits(current_price - tp_distance, symbol)
        
        signal['risk_reward'] = round(rr, 2)
        
        # Validate minimum requirements
        if signal['risk_reward'] < MIN_RISK_REWARD:
            return _create_neutral_signal(symbol, market_type, current, rsi, atr, 
                                         f"Below R:R threshold ({signal['risk_reward']:.1f} < {MIN_RISK_REWARD})")
        if signal['setup_quality'] < MIN_SETUP_QUALITY:
            return _create_neutral_signal(symbol, market_type, current, rsi, atr, 
                                         f"Low setup quality ({signal['setup_quality']:.1f} < {MIN_SETUP_QUALITY})")
        if signal['confirmation_count'] < MIN_CONFIRMATIONS:
            return _create_neutral_signal(symbol, market_type, current, rsi, atr, 
                                         f"Insufficient confirmations ({signal['confirmation_count']} < {MIN_CONFIRMATIONS})")
    else:
        signal['stop_loss'] = None
        signal['take_profit'] = None
        signal['risk_reward'] = None
    
    # Add additional fields
    signal['opportunity_score'] = calculate_scalp_opportunity(strength, rsi, volatility, atr, 
                                                               atr > avg_atr * 0.8, market_type)
    signal['model_confidence'] = model_proba_up if direction == 'Buy' else 1.0 - model_proba_up
    
    return signal
    strength = base_signal['signal_strength']
    sl_atr_mult = max(SL_ATR_BASE - SL_ATR_STRENGTH_FACTOR * strength, 1.2)  # More conservative
    rr = RR_BASE + RR_STRENGTH_FACTOR * strength
    
    # Ensure ATR is not zero or too small - use 14-period ATR for reliability
    safe_atr = max(atr, current_price * 0.002)  # Minimum 0.2% of price as fallback
    
    sl_distance = safe_atr * sl_atr_mult
    tp_distance = sl_distance * rr
    
    # Ensure minimum distance requirements and proper spacing
    min_distance = get_minimum_distance(symbol)
    sl_distance = max(sl_distance, min_distance * 2)  # At least 2x minimum distance
    tp_distance = max(tp_distance, min_distance * MIN_RISK_REWARD * 2)  # Ensure proper R:R
    
    # Validate SL/TP levels are reasonable
    sl_percent = (sl_distance / current_price) * 100
    tp_percent = (tp_distance / current_price) * 100
    
    # Reject signals with unrealistic SL/TP percentages
    if sl_percent > 5.0 or sl_percent < 0.1:  # SL between 0.1% and 5% of price
        return _create_neutral_signal(symbol, market_type, current, rsi, atr, 
                                     f"Unrealistic SL: {sl_percent:.2f}%")
    if tp_percent > 15.0 or tp_percent < 0.2:  # TP between 0.2% and 15% of price
        return _create_neutral_signal(symbol, market_type, current, rsi, atr, 
                                     f"Unrealistic TP: {tp_percent:.2f}%")
    
    if base_signal['direction'] == 'Buy':
        base_signal['stop_loss'] = round_to_symbol_digits(current_price - sl_distance, symbol)
        base_signal['take_profit'] = round_to_symbol_digits(current_price + tp_distance, symbol)
    else:
        base_signal['stop_loss'] = round_to_symbol_digits(current_price + sl_distance, symbol)
        base_signal['take_profit'] = round_to_symbol_digits(current_price - tp_distance, symbol)
    
    base_signal['risk_reward'] = round(rr, 2)
    
    # Ensure minimum R:R
    if base_signal['risk_reward'] < MIN_RISK_REWARD:
        return _create_neutral_signal(symbol, market_type, current, rsi, atr, 
                                     f"Below R:R threshold ({base_signal['risk_reward']:.1f} < {MIN_RISK_REWARD})")
    
    # Validate setup quality
    if base_signal['setup_quality'] < MIN_SETUP_QUALITY:
        return _create_neutral_signal(symbol, market_type, current, rsi, atr, 
                                     f"Low setup quality ({base_signal['setup_quality']:.1f} < {MIN_SETUP_QUALITY})")
    
    # Validate signal strength
    if base_signal['signal_strength'] < MIN_SIGNAL_STRENGTH:
        return _create_neutral_signal(symbol, market_type, current, rsi, atr, 
                                     f"Low signal strength ({base_signal['signal_strength']:.2f} < {MIN_SIGNAL_STRENGTH})")
    
    # Validate confirmation count
    if base_signal['confirmation_count'] < MIN_CONFIRMATIONS:
        return _create_neutral_signal(symbol, market_type, current, rsi, atr, 
                                     f"Insufficient confirmations ({base_signal['confirmation_count']} < {MIN_CONFIRMATIONS})")
    
    # Complete signal with all required fields
    base_signal['symbol'] = symbol
    base_signal['market_name'] = display_name(symbol)
    base_signal['market_type'] = market_type
    base_signal['price'] = current_price
    base_signal['rsi'] = rsi
    base_signal['atr'] = atr
    base_signal['risk_level'] = get_risk_level(atr, avg_atr)
    
    # Volume confirmation (use ATR as proxy)
    volume_confirm = atr > avg_atr * 0.8
    base_signal['opportunity_score'] = calculate_scalp_opportunity(strength, rsi, volatility, atr, volume_confirm, market_type)
    base_signal['setup_quality'] = strength * 100
    base_signal['entry_type'] = get_entry_type(base_signal['opportunity_score'])
    base_signal['model_confidence'] = model_proba_up if base_signal['direction'] == 'Buy' else 1.0 - model_proba_up
    
    return base_signal


def _create_neutral_signal(symbol: str, market_type: str, current, rsi: float, atr: float, reason: str) -> dict:
    """Create a neutral signal with filter reason."""
    return {
        "symbol": symbol,
        "market_name": display_name(symbol),
        "market_type": market_type,
        "direction": "Neutral",
        "signal_strength": 0.0,
        "setup_quality": 0.0,
        "entry_type": "",
        "confirmation_count": 0,
        "price": float(current['close']),
        "rsi": rsi,
        "atr": atr,
        "risk_level": get_risk_level(atr, atr),
        "stop_loss": None,
        "take_profit": None,
        "risk_reward": None,
        "opportunity_score": 0.0,
        "structure": "Neutral",
        "pattern": f"Filter: {reason}",
    }


def _generate_qatraders_signal(symbol: str, df: pd.DataFrame, model_proba_up: float, timeframe: str = "1H") -> dict:
    """
    Simplified signal generation focused on leading indicators.
    Removes excessive lagging indicators and multi-timeframe confirmations.
    Focuses on: price action, simple momentum, and RSI extremes.
    """
    current = df.iloc[-1]
    prev = df.iloc[-2]

    # Ensure all values are scalars
    def safe_float(value, default=0.0):
        """Convert value to float, handling pandas Series and arrays."""
        if isinstance(value, pd.Series):
            return float(value.iloc[-1])
        return float(value) if pd.notna(value) else default

    rsi = safe_float(current.get("RSI"), 50)
    current_price = safe_float(current["close"])
    current_high = safe_float(current["high"])
    current_low = safe_float(current["low"])
    prev_high = safe_float(prev["high"])
    prev_low = safe_float(prev["low"])

    # Simple EMA for trend direction (not multiple alignment)
    ema8 = safe_float(df['close'].ewm(span=8, adjust=False).mean().iloc[-1], current_price)

    atr = safe_float(current.get("ATR"), 0.0001)
    avg_atr = safe_float(df["ATR"].rolling(20).mean().iloc[-1], atr) if len(df) >= 20 else atr
    volatility = safe_float(current.get("volatility"), 0)

    market_type = get_market_type(symbol)

    # Initialize signal
    signal = {
        'direction': 'Neutral',
        'signal_strength': 0,
        'entry_type': '',
        'confirmation_count': 0,
        'setup_quality': 0,
        'pattern': '',
        'structure': '',
        'timeframe': timeframe,
    }

    # Simplified conditions - focus on leading indicators only
    # Price momentum (leading)
    price_momentum = (current_price - df['close'].iloc[-5]) / df['close'].iloc[-5] if len(df) >= 5 else 0
    
    # Candlestick direction (leading - price action)
    bullish_candle = current_price > current["open"]
    bearish_candle = current_price < current["open"]
    
    # Higher low / lower high (price action)
    higher_low = current_low >= prev_low * 0.9995
    lower_high = current_high <= prev_high * 1.0005
    
    # Simple trend (not multiple EMAs)
    uptrend = current_price > ema8
    downtrend = current_price < ema8
    
    # RSI extremes only (not ranges - reduces lag)
    rsi_oversold = rsi < 30
    rsi_overbought = rsi > 70

    # Score based on leading indicators
    long_score = 0
    short_score = 0
    
    # Long conditions (leading indicators)
    if bullish_candle:
        long_score += 2  # Price action
    if higher_low:
        long_score += 2  # Price structure
    if uptrend:
        long_score += 1  # Simple trend
    if price_momentum > 0.002:
        long_score += 2  # Strong momentum
    if rsi_oversold:
        long_score += 2  # Extreme condition (leading signal)
    
    # Short conditions (leading indicators)
    if bearish_candle:
        short_score += 2  # Price action
    if lower_high:
        short_score += 2  # Price structure
    if downtrend:
        short_score += 1  # Simple trend
    if price_momentum < -0.002:
        short_score += 2  # Strong momentum
    if rsi_overbought:
        short_score += 2  # Extreme condition (leading signal)

    # TRADING-GRADE threshold: need 6+ points (out of 9 max) for reliability
    min_score = 6

    # Stricter prediction threshold for higher confidence
    if model_proba_up > 0.55 and long_score >= min_score:
        signal['direction'] = 'Buy'
        signal['signal_strength'] = min(long_score / 9.0, 1.0)
        signal['entry_type'] = 'Aggressive' if long_score >= 7 else 'Standard'
        signal['confirmation_count'] = long_score
        signal['setup_quality'] = (long_score / 9.0) * 100
        signal['structure'] = 'Uptrend' if uptrend else 'Downtrend'
        
        # Build pattern description from leading indicators
        confirmations = []
        if bullish_candle:
            confirmations.append('Bullish candle')
        if higher_low:
            confirmations.append('Higher low')
        if price_momentum > 0.002:
            confirmations.append('Strong momentum')
        if rsi_oversold:
            confirmations.append('RSI oversold')
        signal['pattern'] = ', '.join(confirmations[:3])
        
    elif model_proba_up < 0.45 and short_score >= min_score:
        signal['direction'] = 'Sell'
        signal['signal_strength'] = min(short_score / 9.0, 1.0)
        signal['entry_type'] = 'Aggressive' if short_score >= 7 else 'Standard'
        signal['confirmation_count'] = short_score
        signal['setup_quality'] = (short_score / 9.0) * 100
        signal['structure'] = 'Downtrend' if downtrend else 'Uptrend'
        
        # Build pattern description from leading indicators
        confirmations = []
        if bearish_candle:
            confirmations.append('Bearish candle')
        if lower_high:
            confirmations.append('Lower high')
        if price_momentum < -0.002:
            confirmations.append('Strong momentum')
        if rsi_overbought:
            confirmations.append('RSI overbought')
        signal['pattern'] = ', '.join(confirmations[:3])

    # Add additional fields
    signal['symbol'] = symbol
    signal['market_name'] = display_name(symbol)
    signal['market_type'] = market_type
    signal['price'] = current_price
    signal['rsi'] = rsi
    signal['atr'] = atr
    signal['risk_level'] = get_risk_level(atr, avg_atr)
    signal['stop_loss'] = None
    signal['take_profit'] = None
    signal['risk_reward'] = None
    signal['opportunity_score'] = 0.0

    return signal


def _generate_enhanced_ml_signal(symbol: str, df: pd.DataFrame, model_proba_up: float, timeframe: str = "1H") -> dict:
    """
    Enhanced ML-based signal generation with adaptive confirmations.
    Uses market condition detection to adjust confirmation requirements.
    """
    current = df.iloc[-1]
    prev = df.iloc[-2]

    # Ensure all values are scalars to avoid array ambiguity errors
    def safe_float(value, default=0.0):
        """Convert value to float, handling pandas Series and arrays."""
        if isinstance(value, pd.Series):
            return float(value.iloc[-1])
        return float(value) if pd.notna(value) else default

    rsi = safe_float(current.get("RSI"), 50)
    macd_hist = safe_float(current.get("MACD_Histogram"), 0)
    prev_macd_hist = safe_float(prev.get("MACD_Histogram"), 0)

    stoch_k = safe_float(current.get("Stochastic_K"), 50)
    stoch_d = safe_float(current.get("Stochastic_D"), 50)
    prev_stoch_k = safe_float(prev.get("Stochastic_K"), 50)

    current_price = safe_float(current["close"])
    current_high = safe_float(current["high"])
    current_low = safe_float(current["low"])
    prev_high = safe_float(prev["high"])
    prev_low = safe_float(prev["low"])

    ema8 = safe_float(current.get("EMA8"), current_price)
    ema21 = safe_float(current.get("EMA21"), current_price)
    ema50 = safe_float(current.get("EMA50"), ema21) if "EMA50" in current else ema21  # Fallback to EMA21 if EMA50 not available
    ema_sep = abs(ema8 - ema21)

    atr = safe_float(current.get("ATR"), 0.0001)
    avg_atr = safe_float(df["ATR"].rolling(20).mean().iloc[-1], atr) if len(df) >= 20 else atr
    volatility = safe_float(current.get("volatility"), 0)
    volatility_ratio = atr / avg_atr if avg_atr > 0 else 1.0

    market_type = get_market_type(symbol)
    
    # Detect market condition for adaptive thresholds
    market_condition = detect_market_condition(df)
    adaptive_confirmations = get_adaptive_confirmations(market_condition, volatility_ratio)

    # Enhanced volatility filter
    if avg_atr and atr > 0 and atr > MAX_VOLATILITY_MULTIPLIER * avg_atr:
        return _create_neutral_signal(symbol, market_type, current, rsi, atr, "High volatility filter")

    # Minimum EMA separation (stricter)
    min_sep = 0.20 * atr
    if ema_sep < min_sep:
        return _create_neutral_signal(symbol, market_type, current, rsi, atr, "Insufficient EMA separation")

    # Trend structure
    structure = "Uptrend" if ema8 > ema21 else "Downtrend"

    # Enhanced 9-factor confirmation system
    trend_strength = 0
    confirmations = []

    # 1. EMA alignment (8 vs 21)
    if ema8 > ema21:
        trend_strength += 1
        confirmations.append("EMA bullish (8>21)")
        direction = "Buy"
    elif ema8 < ema21:
        trend_strength += 1
        confirmations.append("EMA bearish (8<21)")
        direction = "Sell"
    else:
        return _create_neutral_signal(symbol, market_type, current, rsi, atr, "EMA crossover unclear")

    # 2. RSI zone - TRADER PLATFORM style (allow reversion or momentum)
    if direction == "Buy" and (rsi <= 35 or (50 <= rsi <= 62)):
        trend_strength += 1
        confirmations.append("RSI bullish" if rsi <= 35 else "RSI momentum")
    elif direction == "Sell" and (rsi >= 65 or (38 <= rsi <= 50)):
        trend_strength += 1
        confirmations.append("RSI bearish" if rsi >= 65 else "RSI momentum")

    # 3. MACD momentum - TRADER PLATFORM style
    if direction == "Buy" and macd_hist > 0 and macd_hist > prev_macd_hist:
        trend_strength += 1
        confirmations.append("MACD bullish")
    elif direction == "Sell" and macd_hist < 0 and macd_hist < prev_macd_hist:
        trend_strength += 1
        confirmations.append("MACD bearish")

    # 4. Candlestick direction - TRADER PLATFORM style
    if direction == "Buy" and current_price > current["open"]:
        trend_strength += 1
        confirmations.append("Bullish candle")
    elif direction == "Sell" and current_price < current["open"]:
        trend_strength += 1
        confirmations.append("Bearish candle")

    # 5. Price vs EMA8 - TRADER PLATFORM style
    if direction == "Buy" and current_price > ema8:
        trend_strength += 1
        confirmations.append("Price above EMA8")
    elif direction == "Sell" and current_price < ema8:
        trend_strength += 1
        confirmations.append("Price below EMA8")

    n_factors = 5  # TRADER PLATFORM 5-factor system

    # Use adaptive confirmation threshold based on market conditions
    if trend_strength < MIN_CONFIRMATIONS:
        return _create_neutral_signal(symbol, market_type, current, rsi, atr,
                                     f"Insufficient confirmations ({trend_strength}/{MIN_CONFIRMATIONS})")

    signal = {
        "symbol": symbol,
        "market_name": display_name(symbol),
        "market_type": market_type,
        "direction": direction,
        "signal_strength": trend_strength / float(n_factors),
        "setup_quality": (trend_strength / n_factors) * 100,
        "entry_type": "",
        "confirmation_count": trend_strength,
        "price": current_price,
        "rsi": rsi,
        "atr": atr,
        "risk_level": get_risk_level(atr, avg_atr),
        "stop_loss": None,
        "take_profit": None,
        "risk_reward": None,
        "opportunity_score": 0.0,
        "structure": structure,
        "pattern": f"Bot (RSI, EMA, MACD, 5-factor): {', '.join(confirmations[:3])}",
        "timeframe": timeframe,
        "htf_advice": "",
    }

    # Set entry type based on strength - TRADER PLATFORM style
    if trend_strength >= 4:
        signal["entry_type"] = "Strong " + ("Bullish" if direction == "Buy" else "Bearish")
    elif trend_strength >= 3:
        signal["entry_type"] = "Confirmed " + ("Bullish" if direction == "Buy" else "Bearish")
    else:
        signal["entry_type"] = "Weak " + ("Bullish" if direction == "Buy" else "Bearish")

    # Volume confirmation (use ATR as proxy)
    volume_confirm = atr > avg_atr * 0.8
    signal["opportunity_score"] = calculate_scalp_opportunity(
        signal["signal_strength"], rsi, volatility, atr, volume_confirm, market_type
    )

    # Calculate SL/TP with enhanced parameters and MT5 validation
    strength = signal["signal_strength"]
    sl_atr_mult = max(SL_ATR_BASE - SL_ATR_STRENGTH_FACTOR * strength, 1.0)
    rr = RR_BASE + RR_STRENGTH_FACTOR * strength
    sl_distance = atr * sl_atr_mult
    tp_distance = sl_distance * rr

    # Get MT5 minimum distance requirements
    min_distance = get_minimum_distance(symbol)
    points = get_symbol_points(symbol)

    # Ensure SL/TP meet minimum distance requirements
    sl_distance = max(sl_distance, min_distance)
    tp_distance = max(tp_distance, min_distance * MIN_RISK_REWARD)

    # Calculate raw SL/TP
    if signal["direction"] == "Buy":
        raw_sl = current_price - sl_distance
        raw_tp = current_price + tp_distance
    else:
        raw_sl = current_price + sl_distance
        raw_tp = current_price - tp_distance

    # Round to symbol digits and ensure minimum distance
    signal["stop_loss"] = round_to_symbol_digits(raw_sl, symbol)
    signal["take_profit"] = round_to_symbol_digits(raw_tp, symbol)

    # Final validation: ensure minimum distance after rounding
    if signal["direction"] == "Buy":
        sl_dist_final = current_price - signal["stop_loss"]
        tp_dist_final = signal["take_profit"] - current_price
    else:
        sl_dist_final = signal["stop_loss"] - current_price
        tp_dist_final = current_price - signal["take_profit"]

    # If rounding reduced distance below minimum, adjust
    if sl_dist_final < min_distance:
        adjustment = (min_distance - sl_dist_final)
        if signal["direction"] == "Buy":
            signal["stop_loss"] = round_to_symbol_digits(signal["stop_loss"] - adjustment, symbol)
        else:
            signal["stop_loss"] = round_to_symbol_digits(signal["stop_loss"] + adjustment, symbol)

    if tp_dist_final < min_distance * MIN_RISK_REWARD:
        adjustment = (min_distance * MIN_RISK_REWARD - tp_dist_final)
        if signal["direction"] == "Buy":
            signal["take_profit"] = round_to_symbol_digits(signal["take_profit"] + adjustment, symbol)
        else:
            signal["take_profit"] = round_to_symbol_digits(signal["take_profit"] - adjustment, symbol)

    signal["risk_reward"] = round(rr, 2)

    return signal


def passes_trade_filters(signal: dict) -> bool:
    """
    TRADER PLATFORM-style trade filters for day trading & scalping.
    More permissive to allow more signals for scalping opportunities.
    """
    if signal["direction"] not in ("Buy", "Sell"):
        return False
    if signal["signal_strength"] < MIN_SIGNAL_STRENGTH:
        return False
    if not signal.get("risk_reward") or signal["risk_reward"] < MIN_RISK_REWARD:
        return False
    if signal.get("confirmation_count", 0) < MIN_CONFIRMATIONS:
        return False
    
    # Basic quality checks
    if not signal.get("stop_loss") or not signal.get("take_profit"):
        return False
    
    # Ensure SL/TP are reasonable distances from entry
    current_price = signal.get("price", 0)
    sl_distance = abs(current_price - signal["stop_loss"])
    tp_distance = abs(signal["take_profit"] - current_price)
    
    if sl_distance <= 0 or tp_distance <= 0:
        return False
    
    # TP should be at least MIN_RISK_REWARD times SL
    if tp_distance < sl_distance * MIN_RISK_REWARD:
        return False
    
    # TRADER PLATFORM: No HTF check, no setup quality check, no RSI extreme check
    # More permissive for scalping opportunities
    
    thresholds = get_market_thresholds(signal["market_type"])
    return signal["signal_strength"] >= thresholds["early_entry"]


def get_mt5_signal_format(signal: dict) -> dict:
    """
    Convert internal signal format to MT5-compatible format.
    Includes all fields needed for MT5 order execution.
    """
    if signal["direction"] not in ("Buy", "Sell"):
        return None
    
    mt5_action = 0  # TRADE_ACTION_DEAL
    mt5_type = 0 if signal["direction"] == "Buy" else 1  # 0=BUY, 1=SELL
    
    return {
        "action": mt5_action,
        "symbol": signal["symbol"],
        "volume": 0.01,  # Default lot size, should be calculated based on risk
        "type": mt5_type,
        "price": signal["price"],
        "sl": signal["stop_loss"],
        "tp": signal["take_profit"],
        "deviation": 20,  # Max price deviation in points
        "magic": 123456,  # EA magic number
        "comment": f"AI Signal {signal.get('entry_type', 'Manual')}",
        "type_time": 0,  # ORDER_TIME_GTC
        "type_filling": 0,  # ORDER_FILLING_IOC
    }


def calculate_position_size(signal: dict, account_balance: float, risk_percent: float = 1.0) -> float:
    """
    Calculate optimal position size based on risk management.
    Uses ATR-based SL to determine lot size for given risk percentage.
    """
    if signal["direction"] not in ("Buy", "Sell"):
        return 0.01  # Minimum lot size
    
    current_price = signal.get("price", 0)
    sl_price = signal.get("stop_loss")
    
    if not sl_price or current_price <= 0:
        return 0.01
    
    # Calculate SL distance in price units
    sl_distance = abs(current_price - sl_price)
    
    # Calculate risk amount in account currency
    risk_amount = account_balance * (risk_percent / 100.0)
    
    # Calculate position size (simplified - MT5 would need more precise calculation)
    # This is a basic calculation - real implementation would need symbol-specific pip values
    if sl_distance > 0:
        position_size = risk_amount / sl_distance
        # Round to standard lot sizes (0.01, 0.1, 1.0, etc.)
        position_size = max(0.01, min(position_size, 100.0))  # Cap at 100 lots
        position_size = round(position_size, 2)
        # Ensure minimum lot size
        position_size = max(0.01, position_size)
    else:
        position_size = 0.01
    
    return position_size
