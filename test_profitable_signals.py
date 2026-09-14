"""
Test script for the new profitable signal generator.
Tests the market-specific strategy combinations for different market types.
"""

import pandas as pd
import numpy as np
from analysis.services.profitable_signal_generator import (
    generate_profitable_signal,
    get_strategy_description,
    STRATEGY_WEIGHTINGS,
    get_market_thresholds
)
from markets.catalog import get_market_type, display_name

def create_test_dataframe(symbol: str, market_type: str) -> pd.DataFrame:
    """Create a test dataframe with realistic price data for testing."""
    np.random.seed(42)
    
    # Generate realistic price data based on market type
    if market_type == 'commodities':
        base_price = 2000.0  # Gold-like
        volatility = 0.02
    elif market_type == 'forex':
        base_price = 1.1000  # EUR/USD-like
        volatility = 0.001
    elif market_type == 'synthetic':
        base_price = 1000.0  # Boom/Crash-like
        volatility = 0.03
    elif market_type == 'volatility':
        base_price = 500.0  # Volatility index-like
        volatility = 0.04
    else:  # indices
        base_price = 4000.0  # Stock index-like
        volatility = 0.015
    
    # Generate 100 candles of data
    data = []
    price = base_price
    
    for i in range(100):
        # Random walk with trend
        change = np.random.normal(0, volatility * base_price)
        price += change
        
        # Add some trend for realism
        if i < 50:
            price += base_price * 0.001  # Uptrend
        else:
            price -= base_price * 0.0005  # Downtrend
        
        # Create OHLC
        high = price + abs(np.random.normal(0, volatility * base_price * 0.5))
        low = price - abs(np.random.normal(0, volatility * base_price * 0.5))
        open_price = low + (high - low) * np.random.random()
        close_price = low + (high - low) * np.random.random()
        
        data.append({
            'open': open_price,
            'high': high,
            'low': low,
            'close': close_price,
            'volume': np.random.randint(1000, 10000)
        })
    
    df = pd.DataFrame(data)
    return df

def test_market_specific_strategies():
    """Test the profitable signal generator for different market types."""
    
    test_symbols = [
        ('frxXAUUSD', 'commodities'),  # Gold
        ('frxEURUSD', 'forex'),        # EUR/USD
        ('BOOM_1000', 'synthetic'),    # Boom index
        ('R_75', 'volatility'),        # Volatility 75
        ('frxUS30', 'indices'),        # US30 index
    ]
    
    print("=" * 80)
    print("PROFITABLE SIGNAL GENERATOR TEST")
    print("=" * 80)
    
    for symbol, expected_market_type in test_symbols:
        print(f"\n{'=' * 80}")
        print(f"Testing: {symbol} ({display_name(symbol)})")
        print(f"Expected Market Type: {expected_market_type}")
        print(f"{'=' * 80}")
        
        # Verify market type detection
        detected_market_type = get_market_type(symbol)
        print(f"Detected Market Type: {detected_market_type}")
        
        if detected_market_type != expected_market_type:
            print(f"⚠️  Market type mismatch!")
            continue
        
        # Get strategy description
        description = get_strategy_description(detected_market_type)
        print(f"Strategy Description: {description}")
        
        # Get strategy weightings
        weightings = STRATEGY_WEIGHTINGS.get(detected_market_type, {})
        print(f"Strategy Weightings: {weightings}")
        
        # Get market thresholds
        thresholds = get_market_thresholds(detected_market_type)
        print(f"Market Thresholds: {thresholds}")
        
        # Create test data
        df = create_test_dataframe(symbol, detected_market_type)
        
        # Add technical indicators
        from analysis.services.indicators import add_technical_indicators
        df = add_technical_indicators(df)
        
        # Generate signal
        model_proba_up = 0.65  # Simulated ML prediction
        signal = generate_profitable_signal(symbol, df, model_proba_up, timeframe="1H")
        
        print(f"\nGenerated Signal:")
        print(f"  Direction: {signal['direction']}")
        print(f"  Signal Strength: {signal['signal_strength']:.2f}")
        print(f"  Setup Quality: {signal['setup_quality']:.1f}")
        print(f"  Entry Type: {signal['entry_type']}")
        print(f"  Confirmation Count: {signal['confirmation_count']}")
        print(f"  Pattern: {signal['pattern']}")
        print(f"  Structure: {signal['structure']}")
        print(f"  Risk Level: {signal['risk_level']}")
        
        if signal['direction'] in ['Buy', 'Sell']:
            print(f"  Stop Loss: {signal['stop_loss']}")
            print(f"  Take Profit: {signal['take_profit']}")
            print(f"  Risk/Reward: {signal['risk_reward']}")
        
        print(f"  Model Confidence: {signal['model_confidence']:.2f}")
        print(f"  Opportunity Score: {signal['opportunity_score']:.1f}")
        
        # Validate signal quality
        if signal['direction'] in ['Buy', 'Sell']:
            if signal['signal_strength'] >= 0.50:
                print("✅ Signal strength meets minimum threshold")
            else:
                print("⚠️  Signal strength below minimum threshold")
            
            if signal['setup_quality'] >= 60.0:
                print("✅ Setup quality meets minimum threshold")
            else:
                print("⚠️  Setup quality below minimum threshold")
            
            if signal['confirmation_count'] >= 2:
                print("✅ Confirmation count meets minimum threshold")
            else:
                print("⚠️  Confirmation count below minimum threshold")
        
        print(f"\n{'=' * 80}")

def test_strategy_combinations():
    """Test that strategy combinations are properly applied."""
    print("\n" + "=" * 80)
    print("STRATEGY COMBINATION TEST")
    print("=" * 80)
    
    for market_type, weightings in STRATEGY_WEIGHTINGS.items():
        print(f"\n{market_type.upper()} Market:")
        total_weight = sum(weightings.values())
        print(f"  Total Weight: {total_weight:.2f}")
        
        if abs(total_weight - 1.0) > 0.01:
            print(f"  ⚠️  Warning: Weights don't sum to 1.0")
        else:
            print(f"  ✅ Weights sum to 1.0")
        
        for strategy, weight in sorted(weightings.items(), key=lambda x: -x[1]):
            print(f"    {strategy}: {weight:.2f} ({weight*100:.1f}%)")

def main():
    """Run all tests."""
    print("\n🚀 Starting Profitable Signal Generator Tests...\n")
    
    # Test market-specific strategies
    test_market_specific_strategies()
    
    # Test strategy combinations
    test_strategy_combinations()
    
    print("\n" + "=" * 80)
    print("✅ All tests completed!")
    print("=" * 80)

if __name__ == "__main__":
    main()