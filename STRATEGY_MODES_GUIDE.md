# Strategy Analysis Modes Guide

## Overview
The signal table now supports 5 different analysis modes for signal generation. Users can switch between modes to use different trading methodologies.

## Available Modes

### 1. Default (Original Signal System)
- **Description**: Uses the original signal generation system that was in place before strategy modes were added
- **Strategy**: `generate_signal` from `signal_engine.py`
- **Best For**: Users who want the proven, original signal system
- **SL/TP**: Uses original stop loss and take profit calculations

### 2. Quant (Quantitative Analysis)
- **Description**: Statistical analysis using mathematical models and patterns
- **Key Features**:
  - Z-score analysis for mean reversion
  - Statistical metrics (skewness, kurtosis)
  - Momentum based on statistical significance
  - Trend following based on returns
- **Strength Calculation**: Based on Z-score and statistical edge
- **SL/TP**: 1.5x ATR for SL, 3.0x ATR for TP (2:1 R:R)
- **Best For**: Data-driven traders who prefer statistical approaches

### 3. Price Action
- **Description**: Candlestick patterns and market structure analysis
- **Key Features**:
  - Candlestick pattern recognition (engulfing, strong candles)
  - Market structure analysis (higher highs/lows)
  - Breakout and breakdown detection
  - Trend analysis using moving averages
- **Strength Calculation**: Based on number of bullish/bearish patterns
- **SL/TP**: 1.2x ATR for SL, 2.5x ATR for TP (~2:1 R:R)
- **Best For**: Traders who prefer pure price action analysis

### 4. ICT (Inner Circle Trader Concepts)
- **Description**: ICT methodology with liquidity and order block analysis
- **Key Features**:
  - Order block detection (opposite of strong moves)
  - Fair Value Gap (FVG) analysis
  - Liquidity sweep detection
  - Market structure analysis
- **Strength Calculation**: Based on ICT confluence factors
- **SL/TP**: 1.8x ATR for SL, 3.5x ATR for TP (~2:1 R:R)
- **Best For**: Traders who follow ICT methodology

### 5. SMC (Smart Money Concepts)
- **Description**: Institutional order flow and market structure analysis
- **Key Features**:
  - Market structure breaks (BOS)
  - Institutional order block analysis
  - Premium/Discount zone analysis
  - Change of Character (CHoCH) detection
  - Imbalance zone analysis
- **Strength Calculation**: Based on SMC confluence factors
- **SL/TP**: 2.0x ATR for SL, 4.0x ATR for TP (2:1 R:R)
- **Best For**: Traders who follow Smart Money Concepts

## Mode Switching

### How to Switch Modes
1. Navigate to the Signal Table page
2. Look for the "Analysis Mode" selector in the toolbar
3. Click on any of the 5 mode buttons:
   - Default (Advanced Profitable Multi-Strategy)
   - Quant (Quantitative Analysis)
   - Price Action (Price Action Analysis)
   - ICT (ICT Concepts Analysis)
   - SMC (Smart Money Concepts)
4. The table will regenerate signals using the selected mode
5. A notification will appear confirming the mode change

### Visual Feedback
- **Active Button**: Highlighted with accent color
- **Table Header**: Shows current mode in parentheses
- **Notification**: Toast notification appears on mode change
- **Loading Indicator**: Shows during signal regeneration

### Mode-Specific Behavior
- **Default Mode**: Now uses the new advanced profitable signal generator with market regime detection, adaptive weightings, and enhanced risk management
- **Analysis Modes**: Quant, Price Action, ICT, and SMC use their specific analysis methods while maintaining consistency with the new system architecture

## Signal Generation Process

### For Each Mode:
1. **Data Collection**: Fetches price data with technical indicators
2. **Mode-Specific Analysis**: Applies the selected strategy's logic
3. **Signal Generation**: Creates direction, strength, and reasoning
4. **Risk Management**: Calculates SL/TP based on mode parameters
5. **Return Signal**: Returns complete signal dictionary

### Signal Fields
- `symbol`: Market symbol
- `direction`: Buy/Sell/Neutral
- `signal_strength`: 0.0 to 1.0
- `setup_quality`: 0 to 100
- `entry_type`: Analysis type (e.g., "Quantitative Analysis")
- `confirmation_count`: Number of confirmations
- `price`: Current price
- `rsi`: RSI value
- `atr`: ATR value
- `stop_loss`: Calculated stop loss
- `take_profit`: Calculated take profit
- `risk_reward`: Risk/reward ratio
- `pattern`: Pattern reasoning
- `structure`: Market structure description
- `timeframe`: Analysis timeframe
- `strategy_mode`: Selected mode

## API Integration

### Endpoint
- **URL**: `/analysis/signals/strategy-mode/`
- **Method**: POST
- **Body**:
  ```json
  {
    "symbol": "frxEURUSD",
    "strategy_mode": "quant",
    "timeframe": "1H"
  }
  ```
- **Response**:
  ```json
  {
    "signal": {
      "symbol": "frxEURUSD",
      "direction": "Buy",
      "signal_strength": 0.75,
      ...
    }
  }
  ```

## Technical Implementation

### File Structure
- `analysis/services/strategy_modes.py`: Core strategy mode logic
- `analysis/services/signal_engine.py`: Original signal generation
- `analysis/views.py`: API endpoint for mode switching
- `analysis/urls.py`: URL routing
- `templates/dashboard/live_signals.html`: UI implementation
- `static/css/style.css`: Styling for mode selector

### Key Functions
- `apply_quant_strategy()`: Quantitative analysis
- `apply_price_action_strategy()`: Price action analysis
- `apply_ict_strategy()`: ICT concepts analysis
- `apply_smc_strategy()`: Smart Money Concepts analysis
- `generate_strategy_mode_signal()`: Main signal generation function

## Usage Recommendations

### When to Use Each Mode

**Default**: 
- New users unfamiliar with specific methodologies
- Proven historical performance
- General signal generation

**Quant**:
- Markets with clear statistical patterns
- Mean reversion strategies
- Data-driven decision making

**Price Action**:
- Markets with clear candlestick patterns
- Pure technical analysis without indicators
- Short-term trading

**ICT**:
- Markets with clear liquidity levels
- Following institutional footprints
- Swing trading

**SMC**:
- Markets with institutional participation
- Market structure analysis
- Institutional flow trading

## Notes

- **Default mode** uses the original signal system (before strategy modes were added)
- **Other modes** are new specialized strategies
- **Each mode** has its own SL/TP calculation methodology
- **Mode switching** is instant and triggers signal regeneration
- **All modes** use the same technical indicators as input
- **Mode selection** is saved in the signal's `strategy_mode` field

## Future Enhancements

Potential additions:
- Custom mode parameters (user-configurable SL/TP multipliers)
- Mode performance tracking and comparison
- Hybrid modes combining multiple strategies
- Backtesting results for each mode
- Mode-specific alerts and notifications