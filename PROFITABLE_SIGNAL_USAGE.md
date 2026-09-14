# Profitable Signal Generator - Usage Guide

## Quick Start

### Basic Usage

```python
from analysis.services.profitable_signal_generator import generate_profitable_signal
from analysis.services.indicators import add_technical_indicators
import pandas as pd

# Prepare your data (assuming you have OHLC data)
df = pd.DataFrame({
    'open': [...],
    'high': [...], 
    'low': [...],
    'close': [...],
    'volume': [...]
})

# Add technical indicators
df = add_technical_indicators(df)

# Generate signal
signal = generate_profitable_signal(
    symbol='frxXAUUSD',  # Gold
    df=df,
    model_proba_up=0.65,  # ML model prediction (0.0-1.0)
    timeframe='1H'
)

# Check signal
if signal['direction'] in ['Buy', 'Sell']:
    print(f"Signal: {signal['direction']}")
    print(f"Strength: {signal['signal_strength']:.2f}")
    print(f"Setup Quality: {signal['setup_quality']:.1f}")
    print(f"Stop Loss: {signal['stop_loss']}")
    print(f"Take Profit: {signal['take_profit']}")
    print(f"Risk/Reward: {signal['risk_reward']}")
    print(f"Pattern: {signal['pattern']}")
else:
    print("No valid signal generated")
```

## Advanced Usage

### Market-Specific Strategy Information

```python
from analysis.services.profitable_signal_generator import (
    get_strategy_description,
    STRATEGY_WEIGHTINGS,
    get_market_thresholds
)

# Get strategy description for a market type
description = get_strategy_description('commodities')
print(f"Commodities Strategy: {description}")

# Get strategy weightings
weightings = STRATEGY_WEIGHTINGS['forex']
print("Forex Strategy Weightings:")
for strategy, weight in weightings.items():
    print(f"  {strategy}: {weight:.2f} ({weight*100:.1f}%)")

# Get market thresholds
thresholds = get_market_thresholds('synthetic')
print(f"Synthetic Market Thresholds: {thresholds}")
```

### Batch Signal Generation

```python
from analysis.services.profitable_signal_generator import generate_profitable_signal
from markets.catalog import all_symbols
from analysis.services.indicators import add_technical_indicators
import pandas as pd

# Generate signals for multiple symbols
symbols = all_symbols()[:5]  # First 5 symbols for example
signals = {}

for symbol in symbols:
    # Get data for each symbol (you'd implement your data source)
    df = get_symbol_data(symbol)  # Your data retrieval function
    df = add_technical_indicators(df)
    
    # Generate signal
    signal = generate_profitable_signal(
        symbol=symbol,
        df=df,
        model_proba_up=0.65,
        timeframe='1H'
    )
    
    signals[symbol] = signal
    
    # Only consider strong signals
    if signal['direction'] in ['Buy', 'Sell'] and signal['signal_strength'] >= 0.70:
        print(f"Strong signal for {symbol}: {signal['direction']} (Strength: {signal['signal_strength']:.2f})")
```

### Integration with Trading System

```python
from analysis.services.profitable_signal_generator import generate_profitable_signal
from analysis.services.indicators import add_technical_indicators

class TradingBot:
    def __init__(self):
        self.position_size = 0.01  # Default lot size
        self.risk_per_trade = 1.0  # 1% risk per trade
    
    def analyze_and_trade(self, symbol, df, model_proba_up):
        """Analyze market and execute trade if signal is strong enough."""
        # Add indicators
        df = add_technical_indicators(df)
        
        # Generate signal
        signal = generate_profitable_signal(
            symbol=symbol,
            df=df,
            model_proba_up=model_proba_up,
            timeframe='1H'
        )
        
        # Check signal quality
        if signal['direction'] in ['Buy', 'Sell']:
            if signal['signal_strength'] >= 0.70:  # Strong signal threshold
                if signal['risk_reward'] >= 2.0:  # Minimum R:R ratio
                    self.execute_trade(signal)
        
        return signal
    
    def execute_trade(self, signal):
        """Execute trade based on signal."""
        print(f"Executing {signal['direction']} trade for {signal['symbol']}")
        print(f"Entry: {signal['price']}")
        print(f"Stop Loss: {signal['stop_loss']}")
        print(f"Take Profit: {signal['take_profit']}")
        print(f"Risk/Reward: {signal['risk_reward']}")
        
        # Your trade execution logic here
        # - Calculate position size based on risk
        # - Place order
        # - Set up monitoring
```

## Configuration

### Toggle Between Signal Generators

In `analysis/management/commands/run_analysis.py`:

```python
# Set to True to use profitable signal generator
# Set to False to use original signal engine
USE_PROFITABLE_SIGNALS = True
```

### Customize Strategy Weightings

You can modify the strategy weightings in `analysis/services/profitable_signal_generator.py`:

```python
STRATEGY_WEIGHTINGS = {
    'commodities': {
        'momentum': 0.35,      # Adjust based on your research
        'breakout': 0.30,
        'support_resistance': 0.20,
        'mean_reversion': 0.10,
        'seasonal': 0.05
    },
    # ... other market types
}
```

### Adjust Trading Constants

Modify the risk management constants in `analysis/services/profitable_signal_generator.py`:

```python
# Risk Management Constants
SL_ATR_BASE = 1.5              # Base stop loss multiplier
SL_ATR_STRENGTH_FACTOR = 0.4   # Strength-based adjustment
RR_BASE = 2.5                  # Base risk/reward ratio
RR_STRENGTH_FACTOR = 0.6       # Strength-based adjustment
MIN_RISK_REWARD = 1.5          # Minimum R:R requirement
MIN_SIGNAL_STRENGTH = 0.50     # Minimum signal strength
MIN_CONFIRMATIONS = 2          # Minimum confirmations needed
MAX_VOLATILITY_MULTIPLIER = 1.5 # Maximum volatility filter
MIN_SETUP_QUALITY = 60.0       # Minimum setup quality score
```

## Market Type Detection

The system automatically detects market types from symbols:

```python
from markets.catalog import get_market_type

# Examples
print(get_market_type('frxXAUUSD'))  # 'commodities'
print(get_market_type('frxEURUSD'))  # 'forex'
print(get_market_type('BOOM_1000'))  # 'synthetic'
print(get_market_type('R_75'))       # 'volatility'
print(get_market_type('frxUS30'))    # 'indices'
```

## Signal Quality Filters

The system applies several quality filters:

1. **Volatility Filter**: Rejects signals during excessive volatility
2. **ML Confirmation**: Signals must align with ML model predictions
3. **Minimum Strength**: Signals must meet minimum strength threshold (0.50)
4. **Setup Quality**: Signals must meet minimum setup quality (60.0)
5. **Confirmations**: Signals must have minimum confirmations (2)
6. **Risk/Reward**: Signals must meet minimum R:R ratio (1.5)

## Signal Fields

A generated signal contains the following fields:

```python
{
    'symbol': 'frxXAUUSD',              # Symbol identifier
    'market_name': 'Gold/USD',         # Human-readable name
    'market_type': 'commodities',      # Market category
    'direction': 'Buy',                # Buy, Sell, or Neutral
    'signal_strength': 0.75,           # 0.0 to 1.0
    'setup_quality': 75.0,             # 0 to 100
    'entry_type': 'Profitable Multi-Strategy',
    'confirmation_count': 3,           # Number of confirmations
    'price': 2015.50,                 # Current price
    'rsi': 55.2,                      # RSI value
    'atr': 15.3,                      # ATR value
    'risk_level': 'normal',            # low, normal, or high
    'stop_loss': 2000.00,             # Stop loss price
    'take_profit': 2030.00,           # Take profit price
    'risk_reward': 2.0,               # Risk/reward ratio
    'pattern': 'momentum: Bullish momentum | breakout: Bullish breakout',
    'structure': 'Commodities Profitable Strategy',
    'timeframe': '1H',                # Timeframe
    'model_confidence': 0.65,         # ML model confidence
    'opportunity_score': 75.0          # Opportunity score
}
```

## Error Handling

```python
from analysis.services.profitable_signal_generator import generate_profitable_signal

try:
    signal = generate_profitable_signal(
        symbol='frxXAUUSD',
        df=df,
        model_proba_up=0.65,
        timeframe='1H'
    )
    
    if signal['direction'] == 'Neutral':
        print(f"No signal: {signal['pattern']}")
    else:
        print(f"Valid signal: {signal['direction']}")
        
except Exception as e:
    print(f"Error generating signal: {e}")
    # Handle error appropriately
```

## Performance Optimization

### Cache Technical Indicators

```python
from functools import lru_cache
from analysis.services.indicators import add_technical_indicators

@lru_cache(maxsize=128)
def get_indicators_cached(symbol_hash, df_hash):
    """Cache technical indicators calculation."""
    df = add_technical_indicators(df)
    return df
```

### Batch Processing

```python
import concurrent.futures

def generate_signals_batch(symbols_data):
    """Generate signals for multiple symbols in parallel."""
    signals = {}
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {}
        
        for symbol, (df, model_proba) in symbols_data.items():
            future = executor.submit(
                generate_profitable_signal,
                symbol, df, model_proba, '1H'
            )
            futures[future] = symbol
        
        for future in concurrent.futures.as_completed(futures):
            symbol = futures[future]
            try:
                signals[symbol] = future.result()
            except Exception as e:
                print(f"Error processing {symbol}: {e}")
    
    return signals
```

## Monitoring and Logging

```python
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Generate signal with logging
logger.info(f"Generating signal for {symbol}")
signal = generate_profitable_signal(symbol, df, model_proba_up, '1H')

if signal['direction'] in ['Buy', 'Sell']:
    logger.info(f"Strong signal generated: {signal['direction']} (Strength: {signal['signal_strength']:.2f})")
    logger.info(f"Pattern: {signal['pattern']}")
else:
    logger.debug(f"No signal: {signal['pattern']}")
```

## Troubleshooting

### No Signals Generated

If you're not getting signals, check:

1. **Data Quality**: Ensure you have sufficient data (minimum 30 candles)
2. **Indicators**: Verify technical indicators are calculated correctly
3. **Volatility**: Check if volatility filter is rejecting signals
4. **ML Confidence**: Verify ML model predictions are reasonable
5. **Market Hours**: Ensure market is open for the symbol

### Weak Signals

If signals are consistently weak:

1. **Strategy Weightings**: Adjust strategy weightings for your market
2. **Thresholds**: Lower minimum thresholds (but be careful with risk)
3. **Market Conditions**: Current market conditions may not favor your strategies
4. **Data Quality**: Ensure your data is accurate and timely

### Integration Issues

If integration with existing system fails:

1. **Import Path**: Verify import paths are correct
2. **Dependencies**: Ensure all required libraries are installed
3. **Configuration**: Check USE_PROFITABLE_SIGNALS flag
4. **Database**: Verify database models are compatible

## Best Practices

1. **Start Small**: Test with one symbol and timeframe first
2. **Monitor Results**: Track signal performance over time
3. **Adjust Gradually**: Make small adjustments to parameters
4. **Risk Management**: Always use proper position sizing and stop losses
5. **Diversify**: Don't rely on signals from a single market type
6. **Backtest**: Test strategies on historical data before live trading
7. **Stay Updated**: Regularly review and update strategy parameters

## Support

For issues or questions:
1. Check the logs for error messages
2. Review the PROFITABLE_STRATEGY_GUIDE.md for detailed information
3. Verify your data quality and market conditions
4. Test with known good data to isolate the issue