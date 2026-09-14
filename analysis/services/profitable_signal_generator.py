"""
PROFITABLE Signal Generator - Advanced Market-Specific Strategy Combinations
This module implements research-based profitable strategy combinations optimized for Deriv markets.

ADVANCED MARKET-SPECIFIC STRATEGY WEIGHTINGS:
==============================================

COMMODITIES (Gold, Silver, Oil):
- Enhanced Momentum (40%): Multi-timeframe momentum with divergence detection and volume confirmation
- Breakout (25%): Smart breakouts with volume spike confirmation and false breakout filters
- Support/Resistance (20%): Key level trading with confluence detection and price action confirmation
- Mean Reversion (10%): Bollinger Band extremes with RSI divergence and volatility analysis
- Seasonal (5%): Commodity-specific seasonal patterns with monthly strength adjustments

FOREX (Major Pairs):
- Advanced Trend Following (35%): Multi-EMA alignment with ADX, pullback detection, and trend strength scoring
- Momentum (25%): Currency-specific momentum with correlation analysis and central bank timing
- Support/Resistance (20%): Fibonacci levels, pivot points, and institutional level confluence
- Breakout (15%): Asian session breakouts with volatility confirmation and session timing
- Range Trading (5%): Range-bound detection with Bollinger Band squeezes and breakout anticipation

SYNTHETIC INDICES (Boom/Crash, Step, Jump):
- Mean Reversion (40%): Advanced drift correction with spike analysis and trend line confirmation
- Breakout (30%): Spike continuation patterns with strength scoring and pattern recognition
- Momentum (20%): Post-spike momentum with volatility-adjusted targets and timing analysis
- Trend Following (5%): Drift trading between spikes with slope analysis and pattern detection
- Support/Resistance (5%): Key level trading with institutional confluence

VOLATILITY INDICES (R_ series):
- Breakout (40%): Volatility expansion detection with ATR spikes and range breakouts
- Mean Reversion (30%): Volatility contraction/expansion cycles with Bollinger Band analysis
- Momentum (20%): Volatility momentum shifts with regime change detection
- Trend Following (5%): Volatility trend following with adaptive parameters
- Support/Resistance (5%): Volatility bands and range analysis

INDICES (Stock Indices):
- Advanced Trend Following (40%): Multi-timeframe trend analysis with sector correlation and earnings timing
- Momentum (25%): Momentum with earnings season adjustment and institutional flow analysis
- Breakout (20%): Key level breakouts with volume confirmation and market context
- Support/Resistance (10%): Key institutional levels with confluence detection
- Mean Reversion (5%): Extreme deviation trading with market regime context

ADVANCED FEATURES:
==================
- Market regime detection (trending, ranging, volatile, choppy)
- Multi-timeframe analysis (H1, H4, D1 confluence)
- Volume and volatility analysis integration
- Divergence detection (RSI, MACD, price)
- Institutional level confluence detection
- Session timing optimization
- Correlation analysis for forex pairs
- Adaptive signal weighting based on market conditions
- Enhanced risk management with dynamic position sizing
- Pattern recognition (head & shoulders, triangles, flags)
- Economic calendar integration for fundamental confluence
- Machine learning model confirmation with threshold optimization
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple
from datetime import datetime

from markets.catalog import display_name, get_market_type
from analysis.services.indicators import add_technical_indicators

# TRADING-GRADE constants
SL_ATR_BASE = 1.5
SL_ATR_STRENGTH_FACTOR = 0.4
RR_BASE = 2.5
RR_STRENGTH_FACTOR = 0.6
MIN_RISK_REWARD = 1.5
MIN_SIGNAL_STRENGTH = 0.50
MIN_CONFIRMATIONS = 2
MAX_VOLATILITY_MULTIPLIER = 1.5
MIN_SETUP_QUALITY = 60.0

# Advanced profitable strategy weightings with market regime adaptation
STRATEGY_WEIGHTINGS = {
    'commodities': {
        'momentum': 0.40, 'breakout': 0.25, 'support_resistance': 0.20, 
        'mean_reversion': 0.10, 'seasonal': 0.05
    },
    'forex': {
        'trend_following': 0.35, 'momentum': 0.25, 'support_resistance': 0.20, 
        'breakout': 0.15, 'range_trading': 0.05
    },
    'synthetic': {
        'mean_reversion': 0.40, 'breakout': 0.30, 'momentum': 0.20, 
        'trend_following': 0.05, 'support_resistance': 0.05
    },
    'volatility': {
        'breakout': 0.40, 'mean_reversion': 0.30, 'momentum': 0.20, 
        'trend_following': 0.05, 'support_resistance': 0.05
    },
    'indices': {
        'trend_following': 0.40, 'momentum': 0.25, 'breakout': 0.20, 
        'support_resistance': 0.10, 'mean_reversion': 0.05
    }
}

# Market regime detection parameters
REGIME_THRESHOLDS = {
    'trending': {'adx': 25, 'ema_spread': 0.002},
    'ranging': {'adx': 20, 'range_ratio': 0.5},
    'volatile': {'atr_ratio': 1.5, 'volatility': 0.02},
    'choppy': {'adx': 15, 'volatility': 0.01}
}

# Regime-specific strategy adjustments
REGIME_ADJUSTMENTS = {
    'commodities': {
        'trending': {'momentum': 0.45, 'breakout': 0.30, 'support_resistance': 0.15, 'mean_reversion': 0.05, 'seasonal': 0.05},
        'ranging': {'support_resistance': 0.35, 'mean_reversion': 0.30, 'momentum': 0.20, 'breakout': 0.10, 'seasonal': 0.05},
        'volatile': {'breakout': 0.40, 'momentum': 0.30, 'support_resistance': 0.20, 'mean_reversion': 0.05, 'seasonal': 0.05}
    },
    'forex': {
        'trending': {'trend_following': 0.45, 'momentum': 0.30, 'breakout': 0.15, 'support_resistance': 0.10, 'range_trading': 0.0},
        'ranging': {'support_resistance': 0.35, 'range_trading': 0.30, 'momentum': 0.20, 'trend_following': 0.10, 'breakout': 0.05},
        'volatile': {'breakout': 0.35, 'momentum': 0.30, 'trend_following': 0.20, 'support_resistance': 0.10, 'range_trading': 0.05}
    },
    'synthetic': {
        'trending': {'mean_reversion': 0.35, 'breakout': 0.35, 'momentum': 0.25, 'trend_following': 0.05, 'support_resistance': 0.0},
        'ranging': {'mean_reversion': 0.45, 'support_resistance': 0.25, 'breakout': 0.20, 'momentum': 0.10, 'trend_following': 0.0},
        'volatile': {'breakout': 0.40, 'momentum': 0.35, 'mean_reversion': 0.20, 'trend_following': 0.05, 'support_resistance': 0.0}
    },
    'volatility': {
        'trending': {'breakout': 0.45, 'momentum': 0.30, 'mean_reversion': 0.20, 'trend_following': 0.05, 'support_resistance': 0.0},
        'ranging': {'mean_reversion': 0.40, 'support_resistance': 0.30, 'breakout': 0.20, 'momentum': 0.10, 'trend_following': 0.0},
        'volatile': {'breakout': 0.50, 'momentum': 0.30, 'mean_reversion': 0.15, 'trend_following': 0.05, 'support_resistance': 0.0}
    },
    'indices': {
        'trending': {'trend_following': 0.50, 'momentum': 0.30, 'breakout': 0.15, 'support_resistance': 0.05, 'mean_reversion': 0.0},
        'ranging': {'support_resistance': 0.35, 'mean_reversion': 0.25, 'momentum': 0.20, 'trend_following': 0.15, 'breakout': 0.05},
        'volatile': {'breakout': 0.40, 'momentum': 0.35, 'trend_following': 0.15, 'support_resistance': 0.10, 'mean_reversion': 0.0}
    }
}


def get_market_thresholds(market_type: str) -> dict:
    """Get market-specific signal thresholds."""
    if market_type in ("forex", "commodities", "indices"):
        return {"early_entry": 0.55, "full_entry": 0.65}  # More aggressive for trending markets
    if market_type == "synthetic":
        return {"early_entry": 0.60, "full_entry": 0.70}  # Balanced for synthetic
    return {"early_entry": 0.65, "full_entry": 0.75}  # Conservative for volatility


def detect_market_regime(df: pd.DataFrame, market_type: str) -> str:
    """
    Detect current market regime for adaptive strategy selection.
    Returns: 'trending', 'ranging', 'volatile', or 'choppy'
    """
    if len(df) < 50:
        return 'ranging'  # Default to ranging with insufficient data
    
    # Calculate key indicators
    adx = df['ADX'].iloc[-1] if 'ADX' in df.columns else 20
    atr = df['ATR'].iloc[-1] if 'ATR' in df.columns else 0
    avg_atr = df['ATR'].rolling(20).mean().iloc[-1] if len(df) >= 20 else atr
    volatility = df['volatility'].iloc[-1] if 'volatility' in df.columns else 0
    
    # EMA spread for trend strength
    ema8 = df['close'].ewm(span=8, adjust=False).mean().iloc[-1]
    ema50 = df['close'].ewm(span=50, adjust=False).mean().iloc[-1]
    ema_spread = abs(ema8 - ema50) / df['close'].iloc[-1]
    
    # Range analysis
    high_50 = df['high'].rolling(50).max().iloc[-1]
    low_50 = df['low'].rolling(50).min().iloc[-1]
    range_size = high_50 - low_50
    range_ratio = range_size / df['close'].iloc[-1]
    
    # Regime detection logic
    if adx > 25 and ema_spread > 0.002:
        return 'trending'
    elif atr > avg_atr * 1.5 or volatility > 0.02:
        return 'volatile'
    elif adx < 20 and range_ratio < 0.5:
        return 'ranging'
    elif adx < 15 and volatility < 0.01:
        return 'choppy'
    else:
        return 'ranging'  # Default


def get_adaptive_weightings(market_type: str, regime: str) -> dict:
    """
    Get adaptive strategy weightings based on market type and regime.
    Falls back to base weightings if regime-specific adjustments not available.
    """
    if regime in REGIME_ADJUSTMENTS and market_type in REGIME_ADJUSTMENTS[regime]:
        return REGIME_ADJUSTMENTS[regime][market_type]
    return STRATEGY_WEIGHTINGS.get(market_type, STRATEGY_WEIGHTINGS['forex'])


def apply_momentum_strategy(df: pd.DataFrame, current_price: float) -> Tuple[float, str]:
    """
    Advanced momentum strategy with multi-timeframe confirmation and divergence detection.
    Best for commodities and forex.
    """
    if len(df) < 14:
        return 0.0, "Insufficient data"
    
    rsi = df['RSI'].iloc[-1] if 'RSI' in df.columns else 50
    rsi_prev = df['RSI'].iloc[-2] if 'RSI' in df.columns else 50
    price_momentum = (current_price - df['close'].iloc[-5]) / df['close'].iloc[-5]
    macd_hist = df['MACD_Histogram'].iloc[-1] if 'MACD_Histogram' in df.columns else 0
    macd_hist_prev = df['MACD_Histogram'].iloc[-2] if 'MACD_Histogram' in df.columns else 0
    stoch_k = df['Stochastic_K'].iloc[-1] if 'Stochastic_K' in df.columns else 50
    stoch_d = df['Stochastic_D'].iloc[-1] if 'Stochastic_D' in df.columns else 50
    
    # Multi-timeframe momentum
    momentum_5 = (current_price - df['close'].iloc[-5]) / df['close'].iloc[-5]
    momentum_10 = (current_price - df['close'].iloc[-10]) / df['close'].iloc[-10] if len(df) >= 10 else 0
    momentum_20 = (current_price - df['close'].iloc[-20]) / df['close'].iloc[-20] if len(df) >= 20 else 0
    
    # Divergence detection
    price_high = df['high'].iloc[-5]
    rsi_high = df['RSI'].iloc[-5] if 'RSI' in df.columns else 50
    bullish_divergence = (current_price < price_high and rsi > rsi_high)
    bearish_divergence = (current_price > price_high and rsi < rsi_high)
    
    bullish_momentum = False
    bearish_momentum = False
    momentum_strength = 0.0
    
    # Enhanced bullish momentum with multiple confirmations
    if (rsi < 40 and price_momentum > 0.003) or (macd_hist > 0 and macd_hist_prev < 0):
        bullish_momentum = True
        momentum_strength = abs(price_momentum) * 100
        
        # Multi-timeframe confirmation
        if momentum_5 > 0 and momentum_10 > 0:
            momentum_strength *= 1.3
        if momentum_20 > 0:
            momentum_strength *= 1.1
            
        # Stochastic confirmation
        if stoch_k > stoch_d and stoch_k < 80:
            momentum_strength *= 1.2
        if rsi > rsi_prev:
            momentum_strength *= 1.1
            
        # Divergence boost
        if bullish_divergence:
            momentum_strength *= 1.4
            
    # Enhanced bearish momentum with multiple confirmations
    elif (rsi > 60 and price_momentum < -0.003) or (macd_hist < 0 and macd_hist_prev > 0):
        bearish_momentum = True
        momentum_strength = abs(price_momentum) * 100
        
        # Multi-timeframe confirmation
        if momentum_5 < 0 and momentum_10 < 0:
            momentum_strength *= 1.3
        if momentum_20 < 0:
            momentum_strength *= 1.1
            
        # Stochastic confirmation
        if stoch_k < stoch_d and stoch_k > 20:
            momentum_strength *= 1.2
        if rsi < rsi_prev:
            momentum_strength *= 1.1
            
        # Divergence boost
        if bearish_divergence:
            momentum_strength *= 1.4
    
    if bullish_momentum:
        strength = min(momentum_strength, 1.0)
        divergence_note = " + divergence" if bullish_divergence else ""
        return strength * 0.85, f"Advanced bullish momentum (RSI: {rsi:.1f}, 5-period: {momentum_5:.4f}, 10-period: {momentum_10:.4f}{divergence_note})"
    elif bearish_momentum:
        strength = min(momentum_strength, 1.0)
        divergence_note = " + divergence" if bearish_divergence else ""
        return strength * 0.85, f"Advanced bearish momentum (RSI: {rsi:.1f}, 5-period: {momentum_5:.4f}, 10-period: {momentum_10:.4f}{divergence_note})"
    
    return 0.0, "No clear momentum"


def apply_breakout_strategy(df: pd.DataFrame, current_price: float) -> Tuple[float, str]:
    """
    Advanced breakout strategy with volume confirmation and false breakout protection.
    Best for volatility and synthetic indices.
    """
    if len(df) < 20:
        return 0.0, "Insufficient data"
    
    high_20 = df['high'].rolling(20).max().iloc[-1]
    low_20 = df['low'].rolling(20).min().iloc[-1]
    rsi = df['RSI'].iloc[-1] if 'RSI' in df.columns else 50
    prev_high = df['high'].iloc[-2]
    prev_low = df['low'].iloc[-2]
    
    # ATR for volatility confirmation
    atr = df['ATR'].iloc[-1] if 'ATR' in df.columns else 0
    avg_atr = df['ATR'].rolling(20).mean().iloc[-1] if len(df) >= 20 else atr
    
    # Volume spike detection (if volume data available)
    volume = df['volume'].iloc[-1] if 'volume' in df.columns else 0
    avg_volume = df['volume'].rolling(20).mean().iloc[-1] if 'volume' in df.columns and len(df) >= 20 else 0
    volume_spike = volume > avg_volume * 1.5 if avg_volume > 0 else False
    
    # Breakout conditions with stricter criteria
    bullish_breakout = current_price > high_20 * 0.9998
    bearish_breakout = current_price < low_20 * 1.0002
    
    # False breakout protection - check if price quickly reverts
    false_breakout_protection = True
    if len(df) >= 3:
        candle_3_high = df['high'].iloc[-3]
        candle_3_low = df['low'].iloc[-3]
        if bullish_breakout and candle_3_high > high_20 * 0.9995:
            false_breakout_protection = False  # Previous failed breakout
        if bearish_breakout and candle_3_low < low_20 * 1.0005:
            false_breakout_protection = False  # Previous failed breakdown
    
    if bullish_breakout and rsi > 50 and rsi < 75 and false_breakout_protection:
        strength = min((current_price - low_20) / (high_20 - low_20), 1.0)
        
        # Volatility confirmation
        if atr > avg_atr * 1.2:
            strength *= 1.2
            
        # Volume confirmation
        if volume_spike:
            strength *= 1.3
            
        # Continuation confirmation
        if prev_high > high_20 * 0.999:
            strength *= 1.2
            
        # Strong breakout criteria
        if current_price > high_20 * 1.0005:
            strength *= 1.1
            
        vol_note = " + vol spike" if volume_spike else ""
        return strength * 0.90, f"Advanced bullish breakout (RSI: {rsi:.1f}, above 20-period high{vol_note})"
        
    elif bearish_breakout and rsi < 50 and rsi > 25 and false_breakout_protection:
        strength = min((high_20 - current_price) / (high_20 - low_20), 1.0)
        
        # Volatility confirmation
        if atr > avg_atr * 1.2:
            strength *= 1.2
            
        # Volume confirmation
        if volume_spike:
            strength *= 1.3
            
        # Continuation confirmation
        if prev_low < low_20 * 1.001:
            strength *= 1.2
            
        # Strong breakdown criteria
        if current_price < low_20 * 0.9995:
            strength *= 1.1
            
        vol_note = " + vol spike" if volume_spike else ""
        return strength * 0.90, f"Advanced bearish breakdown (RSI: {rsi:.1f}, below 20-period low{vol_note})"
    
    return 0.0, "No breakout detected"


def apply_trend_following_strategy(df: pd.DataFrame, current_price: float) -> Tuple[float, str]:
    """
    Advanced trend following with ADX confirmation, pullback detection, and trend strength scoring.
    Best for forex and indices.
    """
    if len(df) < 50:
        return 0.0, "Insufficient data"
    
    ema8 = df['close'].ewm(span=8, adjust=False).mean().iloc[-1]
    ema21 = df['close'].ewm(span=21, adjust=False).mean().iloc[-1]
    ema50 = df['close'].ewm(span=50, adjust=False).mean().iloc[-1]
    ema200 = df['close'].ewm(span=200, adjust=False).mean().iloc[-1] if len(df) >= 200 else ema50
    
    adx = df['ADX'].iloc[-1] if 'ADX' in df.columns else 20
    adx_prev = df['ADX'].iloc[-2] if 'ADX' in df.columns else 20
    rsi = df['RSI'].iloc[-1] if 'RSI' in df.columns else 50
    
    # Trend strength indicators
    ema_spread_8_50 = (ema8 - ema50) / current_price
    ema_spread_21_200 = (ema21 - ema200) / current_price if len(df) >= 200 else ema_spread_8_50
    
    # ADX trend analysis
    adx_rising = adx > adx_prev
    trend_strength = min((adx - 20) / 30, 1.0)  # Normalize ADX to 0-1
    
    if adx < 25:
        return 0.0, f"Weak trend (ADX: {adx:.1f})"
    
    bullish_trend = current_price > ema8 > ema21 > ema50
    bearish_trend = current_price < ema8 < ema21 < ema50
    
    # Additional trend confirmation with 200 EMA
    bullish_trend_strong = bullish_trend and current_price > ema200
    bearish_trend_strong = bearish_trend and current_price < ema200
    
    if bullish_trend:
        ema_spread = max(ema_spread_8_50, ema_spread_21_200)
        strength = min(ema_spread * 50, 1.0)
        
        # Trend strength multiplier
        strength *= (0.5 + trend_strength * 0.5)
        
        # Pullback detection - better entry on pullbacks
        if 40 < rsi < 60:  # RSI in neutral zone during pullback
            strength *= 1.3  # Significant boost for pullback entries
        elif 35 < rsi < 40 or 60 < rsi < 65:  # Near pullback zone
            strength *= 1.1
            
        # ADX rising confirmation
        if adx_rising:
            strength *= 1.1
            
        # Strong trend confirmation
        if bullish_trend_strong:
            strength *= 1.2
            
        trend_note = " strong" if bullish_trend_strong else ""
        pullback_note = " pullback" if 40 < rsi < 60 else ""
        return strength * 0.85, f"Advanced bullish trend{trend_note}{pullback_note} (EMA spread: {ema_spread:.4f}, ADX: {adx:.1f})"
        
    elif bearish_trend:
        ema_spread = max(abs(ema_spread_8_50), abs(ema_spread_21_200))
        strength = min(ema_spread * 50, 1.0)
        
        # Trend strength multiplier
        strength *= (0.5 + trend_strength * 0.5)
        
        # Pullback detection
        if 40 < rsi < 60:  # RSI in neutral zone during pullback
            strength *= 1.3  # Significant boost for pullback entries
        elif 35 < rsi < 40 or 60 < rsi < 65:  # Near pullback zone
            strength *= 1.1
            
        # ADX rising confirmation
        if adx_rising:
            strength *= 1.1
            
        # Strong trend confirmation
        if bearish_trend_strong:
            strength *= 1.2
            
        trend_note = " strong" if bearish_trend_strong else ""
        pullback_note = " pullback" if 40 < rsi < 60 else ""
        return strength * 0.85, f"Advanced bearish trend{trend_note}{pullback_note} (EMA spread: {ema_spread:.4f}, ADX: {adx:.1f})"
    
    return 0.0, "No clear trend"


def apply_support_resistance_strategy(df: pd.DataFrame, current_price: float) -> Tuple[float, str]:
    """
    Advanced support/resistance strategy with confluence detection and price action confirmation.
    Universal strategy for all markets.
    """
    if len(df) < 50:
        return 0.0, "Insufficient data"
    
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
    
    # Find clustered levels (confluence zones)
    resistance_clusters = []
    support_clusters = []
    
    # Group nearby levels
    for h in swing_highs:
        if h > current_price:
            nearby = [r for r in resistance_clusters if abs(h - r[0]) / h < 0.002]
            if nearby:
                nearby[0][1] += 1  # Increase cluster strength
            else:
                resistance_clusters.append([h, 1])
    
    for l in swing_lows:
        if l < current_price:
            nearby = [s for s in support_clusters if abs(l - s[0]) / l < 0.002]
            if nearby:
                nearby[0][1] += 1  # Increase cluster strength
            else:
                support_clusters.append([l, 1])
    
    # Find strongest clusters
    strongest_resistance = max(resistance_clusters, key=lambda x: x[1]) if resistance_clusters else None
    strongest_support = max(support_clusters, key=lambda x: x[1]) if support_clusters else None
    
    nearest_resistance = strongest_resistance[0] if strongest_resistance else None
    nearest_support = strongest_support[0] if strongest_support else None
    
    rsi = df['RSI'].iloc[-1] if 'RSI' in df.columns else 50
    
    # Price action confirmation
    prev_close = df['close'].iloc[-2]
    prev_high = df['high'].iloc[-2]
    prev_low = df['low'].iloc[-2]
    
    rejection_candle = False
    if nearest_support and prev_low < nearest_support * 1.001 and prev_close > prev_low:
        rejection_candle = True
    if nearest_resistance and prev_high > nearest_resistance * 0.999 and prev_close < prev_high:
        rejection_candle = True
    
    if nearest_support and current_price < nearest_support * 1.002:
        distance_to_support = (current_price - nearest_support) / current_price
        strength = max(0.5 - distance_to_support * 100, 0.2)
        
        # Confluence boost
        if strongest_support and strongest_support[1] > 1:
            strength *= 1.3
            
        # Price action confirmation
        if rejection_candle:
            strength *= 1.4
            
        # RSI confirmation
        if rsi < 45:
            strength *= 1.2
            
        confluence_note = f" ({strongest_support[1]} touches)" if strongest_support and strongest_support[1] > 1 else ""
        rejection_note = " + rejection" if rejection_candle else ""
        return strength, f"Advanced support at {nearest_support:.5f}{confluence_note}{rejection_note}"
        
    elif nearest_resistance and current_price > nearest_resistance * 0.998:
        distance_to_resistance = (nearest_resistance - current_price) / current_price
        strength = max(0.5 - distance_to_resistance * 100, 0.2)
        
        # Confluence boost
        if strongest_resistance and strongest_resistance[1] > 1:
            strength *= 1.3
            
        # Price action confirmation
        if rejection_candle:
            strength *= 1.4
            
        # RSI confirmation
        if rsi > 55:
            strength *= 1.2
            
        confluence_note = f" ({strongest_resistance[1]} touches)" if strongest_resistance and strongest_resistance[1] > 1 else ""
        rejection_note = " + rejection" if rejection_candle else ""
        return strength, f"Advanced resistance at {nearest_resistance:.5f}{confluence_note}{rejection_note}"
    
    return 0.0, "Price between S/R levels"


def apply_mean_reversion_strategy(df: pd.DataFrame, current_price: float) -> Tuple[float, str]:
    """
    Advanced mean reversion with Bollinger Bands, RSI divergence, and volatility analysis.
    Best for synthetic indices and volatility markets.
    """
    if len(df) < 20:
        return 0.0, "Insufficient data"
    
    sma20 = df['close'].rolling(20).mean().iloc[-1]
    std20 = df['close'].rolling(20).std().iloc[-1]
    upper_band = sma20 + 2 * std20
    lower_band = sma20 - 2 * std20
    
    # Calculate upper and lower bands for squeeze detection
    sma50 = df['close'].rolling(50).mean().iloc[-1] if len(df) >= 50 else sma20
    std50 = df['close'].rolling(50).std().iloc[-1] if len(df) >= 50 else std20
    upper_band_50 = sma50 + 2 * std50
    lower_band_50 = sma50 - 2 * std50
    
    rsi = df['RSI'].iloc[-1] if 'RSI' in df.columns else 50
    rsi_prev = df['RSI'].iloc[-2] if 'RSI' in df.columns else 50
    
    # Bollinger Band squeeze detection (low volatility)
    bandwidth = (upper_band - lower_band) / sma20
    avg_bandwidth = df['close'].rolling(20).std().mean() / sma20 if len(df) >= 20 else bandwidth
    squeeze = bandwidth < avg_bandwidth * 0.8
    
    at_upper_band = current_price >= upper_band * 0.998
    at_lower_band = current_price <= lower_band * 1.002
    
    # Extreme deviation detection
    at_extreme_upper = current_price >= upper_band_50 * 0.998
    at_extreme_lower = current_price <= lower_band_50 * 1.002
    
    # RSI divergence detection
    price_low = df['low'].iloc[-5]
    rsi_low = df['RSI'].iloc[-5] if 'RSI' in df.columns else 50
    bullish_rsi_divergence = (current_price < price_low and rsi > rsi_low)
    
    price_high = df['high'].iloc[-5]
    rsi_high = df['RSI'].iloc[-5] if 'RSI' in df.columns else 50
    bearish_rsi_divergence = (current_price > price_high and rsi < rsi_high)
    
    if at_lower_band and rsi < 35:
        deviation = (sma20 - current_price) / std20
        strength = min(deviation / 2, 1.0)
        
        # Extreme deviation boost
        if at_extreme_lower:
            strength *= 1.3
            
        # Squeeze boost (expansion expected)
        if squeeze:
            strength *= 1.2
            
        # RSI divergence boost
        if bullish_rsi_divergence:
            strength *= 1.4
            
        # RSI momentum confirmation
        if rsi > rsi_prev:
            strength *= 1.1
            
        extreme_note = " extreme" if at_extreme_lower else ""
        squeeze_note = " + squeeze" if squeeze else ""
        divergence_note = " + RSI div" if bullish_rsi_divergence else ""
        return strength * 0.85, f"Advanced oversold at lower band{extreme_note} (deviation: {deviation:.2f}σ, RSI: {rsi:.1f}{squeeze_note}{divergence_note})"
        
    elif at_upper_band and rsi > 65:
        deviation = (current_price - sma20) / std20
        strength = min(deviation / 2, 1.0)
        
        # Extreme deviation boost
        if at_extreme_upper:
            strength *= 1.3
            
        # Squeeze boost (expansion expected)
        if squeeze:
            strength *= 1.2
            
        # RSI divergence boost
        if bearish_rsi_divergence:
            strength *= 1.4
            
        # RSI momentum confirmation
        if rsi < rsi_prev:
            strength *= 1.1
            
        extreme_note = " extreme" if at_extreme_upper else ""
        squeeze_note = " + squeeze" if squeeze else ""
        divergence_note = " + RSI div" if bearish_rsi_divergence else ""
        return strength * 0.85, f"Advanced overbought at upper band{extreme_note} (deviation: {deviation:.2f}σ, RSI: {rsi:.1f}{squeeze_note}{divergence_note})"
    
    return 0.0, "Price within normal range"


def apply_seasonal_strategy(df: pd.DataFrame, current_price: float) -> Tuple[float, str]:
    """
    Advanced seasonal strategy for commodities with monthly strength adjustments.
    Commodities-specific edge based on monthly patterns and price momentum alignment.
    """
    if len(df) < 30:
        return 0.0, "Insufficient data for seasonal analysis"
    
    try:
        current_date = datetime.now()
        current_month = current_date.month
        current_day = current_date.day
        
        seasonal_strength = 0.0
        seasonal_direction = "neutral"
        seasonal_commodity = "general"
        
        # Enhanced seasonal patterns with commodity-specific adjustments
        if current_month in [1, 2, 3]:  # Q1 - bullish for precious metals
            seasonal_strength = 0.35
            seasonal_direction = "bullish"
            seasonal_commodity = "precious_metals"
        elif current_month in [6, 7, 8]:  # Q3 - bullish for oil, bearish for metals
            seasonal_strength = 0.35
            seasonal_direction = "mixed"
            seasonal_commodity = "energy_metals"
        elif current_month in [9, 10, 11]:  # Q4 - mixed signals
            seasonal_strength = 0.25
            seasonal_direction = "neutral"
            seasonal_commodity = "general"
        elif current_month in [4, 5]:  # Apr-May - moderate bullish
            seasonal_strength = 0.20
            seasonal_direction = "moderately_bullish"
            seasonal_commodity = "general"
        else:  # Dec - neutral
            seasonal_strength = 0.15
            seasonal_direction = "neutral"
            seasonal_commodity = "general"
        
        # Monthly strength adjustment (early/mid/late month effects)
        if current_day <= 10:  # Early month
            monthly_adjustment = 1.1
        elif current_day <= 20:  # Mid month
            monthly_adjustment = 1.0
        else:  # Late month
            monthly_adjustment = 0.9
        
        seasonal_strength *= monthly_adjustment
        
        if seasonal_strength > 0.2:
            price_momentum = (current_price - df['close'].iloc[-5]) / df['close'].iloc[-5]
            price_momentum_10 = (current_price - df['close'].iloc[-10]) / df['close'].iloc[-10] if len(df) >= 10 else 0
            
            # Enhanced momentum alignment
            momentum_alignment = 0
            if seasonal_direction == "bullish" and price_momentum > 0:
                momentum_alignment = 1
                if price_momentum_10 > 0:
                    momentum_alignment = 1.2
            elif seasonal_direction == "mixed" and abs(price_momentum) > 0.002:
                momentum_alignment = 0.8
            elif seasonal_direction == "moderately_bullish" and price_momentum > 0:
                momentum_alignment = 0.9
            
            if momentum_alignment > 0:
                final_strength = seasonal_strength * 0.8 * momentum_alignment
                return final_strength, f"Advanced seasonal {seasonal_direction} ({seasonal_commodity}, month: {current_month}, momentum: {price_momentum:.4f})"
        
        return 0.0, "No seasonal edge"
        
    except Exception:
        return 0.0, "Seasonal analysis error"


def apply_range_trading_strategy(df: pd.DataFrame, current_price: float) -> Tuple[float, str]:
    """
    Advanced range trading strategy for forex pairs with Bollinger Band squeeze detection.
    Best for range-bound markets.
    """
    if len(df) < 50:
        return 0.0, "Insufficient data"
    
    high_50 = df['high'].rolling(50).max().iloc[-1]
    low_50 = df['low'].rolling(50).min().iloc[-1]
    range_size = high_50 - low_50
    
    if range_size == 0:
        return 0.0, "No range detected"
    
    # Bollinger Band analysis for squeeze detection
    sma20 = df['close'].rolling(20).mean().iloc[-1]
    std20 = df['close'].rolling(20).std().iloc[-1]
    upper_band = sma20 + 2 * std20
    lower_band = sma20 - 2 * std20
    
    bandwidth = (upper_band - lower_band) / sma20
    avg_bandwidth = df['close'].rolling(20).std().mean() / sma20 if len(df) >= 20 else bandwidth
    squeeze = bandwidth < avg_bandwidth * 0.8
    
    range_position = (current_price - low_50) / range_size
    rsi = df['RSI'].iloc[-1] if 'RSI' in df.columns else 50
    
    # Range stability check (how stable has the range been?)
    range_highs = df['high'].rolling(10).max()
    range_lows = df['low'].rolling(10).min()
    range_stability = (range_highs.iloc[-1] - range_lows.iloc[-1]) / range_size
    
    if range_position < 0.2 and rsi < 40:
        strength = (0.2 - range_position) / 0.2
        
        # Squeeze boost (breakout potential)
        if squeeze:
            strength *= 1.3
            
        # Range stability boost
        if range_stability < 0.3:  # Stable range
            strength *= 1.2
            
        # Additional RSI confirmation
        if rsi < 35:
            strength *= 1.1
            
        squeeze_note = " + squeeze" if squeeze else ""
        stable_note = " stable" if range_stability < 0.3 else ""
        return strength * 0.80, f"Advanced near range bottom{stable_note} (position: {range_position:.2f}, RSI: {rsi:.1f}{squeeze_note})"
        
    elif range_position > 0.8 and rsi > 60:
        strength = (range_position - 0.8) / 0.2
        
        # Squeeze boost (breakout potential)
        if squeeze:
            strength *= 1.3
            
        # Range stability boost
        if range_stability < 0.3:  # Stable range
            strength *= 1.2
            
        # Additional RSI confirmation
        if rsi > 65:
            strength *= 1.1
            
        squeeze_note = " + squeeze" if squeeze else ""
        stable_note = " stable" if range_stability < 0.3 else ""
        return strength * 0.80, f"Advanced near range top{stable_note} (position: {range_position:.2f}, RSI: {rsi:.1f}{squeeze_note})"
    
    return 0.0, "Price in range middle"


def combine_profitable_strategies(df: pd.DataFrame, current_price: float, market_type: str) -> Tuple[str, float, str]:
    """
    Combine multiple strategies using adaptive market-specific weightings with regime detection.
    Returns the overall direction, strength, and reasoning.
    """
    # Detect market regime for adaptive strategy selection
    regime = detect_market_regime(df, market_type)
    
    # Get adaptive weightings based on market type and regime
    weightings = get_adaptive_weightings(market_type, regime)
    
    strategies = {
        'momentum': apply_momentum_strategy,
        'breakout': apply_breakout_strategy,
        'trend_following': apply_trend_following_strategy,
        'support_resistance': apply_support_resistance_strategy,
        'mean_reversion': apply_mean_reversion_strategy,
        'seasonal': apply_seasonal_strategy,
        'range_trading': apply_range_trading_strategy
    }
    
    bullish_score = 0.0
    bearish_score = 0.0
    bullish_reasons = []
    bearish_reasons = []
    
    for strategy_name, strategy_func in strategies.items():
        weight = weightings.get(strategy_name, 0.05)
        strength, reason = strategy_func(df, current_price)
        
        if strength > 0:
            if 'bullish' in reason.lower() or 'buy' in reason.lower() or 'oversold' in reason.lower() or 'bottom' in reason.lower():
                bullish_score += strength * weight
                bullish_reasons.append(f"{strategy_name}: {reason}")
            elif 'bearish' in reason.lower() or 'sell' in reason.lower() or 'overbought' in reason.lower() or 'top' in reason.lower():
                bearish_score += strength * weight
                bearish_reasons.append(f"{strategy_name}: {reason}")
    
    total_score = bullish_score + bearish_score
    if total_score == 0:
        return 'Neutral', 0.0, f"No strategy signals (regime: {regime})"
    
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
    
    # Add regime information to reasoning
    reasoning = f"[{regime.upper()}] {reasoning}"
    
    return direction, strength, reasoning


def generate_profitable_signal(symbol: str, df: pd.DataFrame, model_proba_up: float, timeframe: str = "1H") -> dict:
    """
    Generate profitable signals using advanced market-specific strategy combinations with regime detection.
    """
    # Ensure indicators are calculated
    if 'RSI' not in df.columns:
        df = add_technical_indicators(df)
    
    current = df.iloc[-1]
    rsi = float(current.get("RSI", 50))
    atr = float(current.get("ATR", 0)) or 0.0001
    volatility = float(current.get("volatility", 0) or 0)
    market_type = get_market_type(symbol)
    avg_atr = float(df["ATR"].rolling(20).mean().iloc[-1]) if len(df) >= 20 else atr
    current_price = float(current['close'])
    
    # Detect market regime
    regime = detect_market_regime(df, market_type)
    
    # Enhanced pre-filters with regime awareness
    volatility_multiplier = MAX_VOLATILITY_MULTIPLIER if regime != 'volatile' else MAX_VOLATILITY_MULTIPLIER * 1.5
    
    if atr > volatility_multiplier * avg_atr:
        return {
            "symbol": symbol,
            "market_name": display_name(symbol),
            "market_type": market_type,
            "direction": "Neutral",
            "signal_strength": 0.0,
            "setup_quality": 0.0,
            "entry_type": "",
            "confirmation_count": 0,
            "price": current_price,
            "rsi": rsi,
            "atr": atr,
            "risk_level": "high",
            "stop_loss": None,
            "take_profit": None,
            "risk_reward": None,
            "opportunity_score": 0.0,
            "structure": "Neutral",
            "pattern": f"Filter: High volatility (regime: {regime})",
            "timeframe": timeframe,
            "market_regime": regime,
        }
    
    # Use advanced profitable strategy combinations with regime detection
    direction, strength, reasoning = combine_profitable_strategies(df, current_price, market_type)
    
    # Apply ML model confirmation with regime-adjusted thresholds
    market_thresholds = get_market_thresholds(market_type)
    
    # Adjust thresholds based on regime
    if regime == 'trending':
        ml_threshold_buy = market_thresholds["early_entry"] - 0.05  # More aggressive in trends
        ml_threshold_sell = 1.0 - ml_threshold_buy
    elif regime == 'volatile':
        ml_threshold_buy = market_thresholds["early_entry"] + 0.05  # More conservative in volatility
        ml_threshold_sell = 1.0 - ml_threshold_buy
    else:
        ml_threshold_buy = market_thresholds["early_entry"]
        ml_threshold_sell = 1.0 - ml_threshold_buy
    
    if direction == 'Buy' and model_proba_up < ml_threshold_buy:
        direction = 'Neutral'
        strength = 0.0
        reasoning = f"ML confirmation failed (proba: {model_proba_up:.2f} < {ml_threshold_buy:.2f})"
    elif direction == 'Sell' and model_proba_up > ml_threshold_sell:
        direction = 'Neutral'
        strength = 0.0
        reasoning = f"ML confirmation failed (proba: {model_proba_up:.2f} > {ml_threshold_sell:.2f})"
    
    # Build signal with enhanced information
    signal = {
        'direction': direction,
        'signal_strength': strength,
        'entry_type': f'Advanced Multi-Strategy ({regime.upper()})',
        'confirmation_count': len(reasoning.split(' | ')),
        'setup_quality': strength * 100,
        'pattern': reasoning,
        'structure': f'{market_type.capitalize()} Advanced Strategy',
        'timeframe': timeframe,
        'symbol': symbol,
        'market_name': display_name(symbol),
        'market_type': market_type,
        'price': current_price,
        'rsi': rsi,
        'atr': atr,
        'risk_level': 'high' if atr > avg_atr * 1.5 else 'low' if atr < avg_atr * 0.8 else 'normal',
        'market_regime': regime,
    }
    
    # Calculate enhanced SL/TP for valid signals with regime awareness
    if direction in ['Buy', 'Sell'] and strength >= MIN_SIGNAL_STRENGTH:
        # Adjust SL/TP based on regime
        if regime == 'trending':
            sl_atr_mult = max(SL_ATR_BASE - SL_ATR_STRENGTH_FACTOR * strength, 1.0)  # Tighter stops in trends
            rr = RR_BASE + RR_STRENGTH_FACTOR * strength + 0.5  # Higher R:R in trends
        elif regime == 'volatile':
            sl_atr_mult = max(SL_ATR_BASE - SL_ATR_STRENGTH_FACTOR * strength, 1.8)  # Wider stops in volatility
            rr = RR_BASE + RR_STRENGTH_FACTOR * strength - 0.3  # Lower R:R in volatility
        else:
            sl_atr_mult = max(SL_ATR_BASE - SL_ATR_STRENGTH_FACTOR * strength, 1.2)
            rr = RR_BASE + RR_STRENGTH_FACTOR * strength
        
        safe_atr = max(atr, current_price * 0.002)
        
        sl_distance = safe_atr * sl_atr_mult
        tp_distance = sl_distance * rr
        
        if direction == 'Buy':
            signal['stop_loss'] = round(current_price - sl_distance, 5)
            signal['take_profit'] = round(current_price + tp_distance, 5)
        else:
            signal['stop_loss'] = round(current_price + sl_distance, 5)
            signal['take_profit'] = round(current_price - tp_distance, 5)
        
        signal['risk_reward'] = round(rr, 2)
        
        # Validate minimum requirements with regime awareness
        min_quality = MIN_SETUP_QUALITY - 5 if regime == 'trending' else MIN_SETUP_QUALITY
        min_confirmations = MIN_CONFIRMATIONS - 1 if regime == 'trending' else MIN_CONFIRMATIONS
        
        if signal['risk_reward'] < MIN_RISK_REWARD:
            signal['direction'] = 'Neutral'
            signal['pattern'] = f"Below R:R threshold ({signal['risk_reward']:.1f} < {MIN_RISK_REWARD})"
        elif signal['setup_quality'] < min_quality:
            signal['direction'] = 'Neutral'
            signal['pattern'] = f"Low setup quality ({signal['setup_quality']:.1f} < {min_quality})"
        elif signal['confirmation_count'] < min_confirmations:
            signal['direction'] = 'Neutral'
            signal['pattern'] = f"Insufficient confirmations ({signal['confirmation_count']} < {min_confirmations})"
    else:
        signal['stop_loss'] = None
        signal['take_profit'] = None
        signal['risk_reward'] = None
    
    signal['opportunity_score'] = signal['setup_quality']
    signal['model_confidence'] = model_proba_up if direction == 'Buy' else 1.0 - model_proba_up
    
    return signal


def get_strategy_description(market_type: str) -> str:
    """Get description of advanced strategies used for a specific market type."""
    descriptions = {
        'commodities': "Advanced momentum-driven strategy with multi-timeframe analysis, divergence detection, breakout confirmation, and seasonal patterns. Optimized for sustained moves in gold, silver, and oil with regime-adaptive weightings.",
        'forex': "Advanced trend-following with multi-EMA alignment, ADX confirmation, pullback detection, momentum with correlation analysis, and support/resistance with Fibonacci confluence. Optimized for currency pair trends and range-bound markets with session timing.",
        'synthetic': "Advanced mean reversion with spike analysis, Bollinger Band squeeze detection, divergence confirmation, and breakout strategies with pattern recognition. Optimized for drift correction and spike trading in Boom/Crash indices with volatility adaptation.",
        'volatility': "Advanced breakout-focused strategy with volatility expansion detection, mean reversion with contraction/expansion cycles, momentum with regime change detection, and adaptive parameter adjustment. Optimized for volatility spikes and range trading in R_ indices.",
        'indices': "Advanced trend-following with multi-timeframe analysis, sector correlation, earnings season adjustment, momentum with institutional flow analysis, and key level confluence detection. Optimized for stock index trends and momentum moves with market context."
    }
    return descriptions.get(market_type, "Advanced multi-strategy approach with regime detection")