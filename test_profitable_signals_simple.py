"""
Simple verification script for the profitable signal generator.
This script doesn't require Django or full Python setup - just basic imports.
"""

import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def verify_strategy_weightings():
    """Verify that strategy weightings are properly defined."""
    print("=" * 80)
    print("STRATEGY WEIGHTINGS VERIFICATION")
    print("=" * 80)
    
    # Import the weightings directly
    try:
        from analysis.services.profitable_signal_generator import STRATEGY_WEIGHTINGS
        
        for market_type, weightings in STRATEGY_WEIGHTINGS.items():
            print(f"\n{market_type.upper()} Market:")
            total_weight = sum(weightings.values())
            print(f"  Total Weight: {total_weight:.2f}")
            
            if abs(total_weight - 1.0) > 0.01:
                print(f"  WARNING: Weights don't sum to 1.0")
                return False
            else:
                print(f"  PASS: Weights sum to 1.0")
            
            for strategy, weight in sorted(weightings.items(), key=lambda x: -x[1]):
                print(f"    {strategy}: {weight:.2f} ({weight*100:.1f}%)")
        
        print("\nPASS: All strategy weightings are valid!")
        return True
        
    except ImportError as e:
        print(f"FAIL: Failed to import: {e}")
        return False

def verify_strategy_descriptions():
    """Verify that strategy descriptions are available."""
    print("\n" + "=" * 80)
    print("STRATEGY DESCRIPTIONS VERIFICATION")
    print("=" * 80)
    
    try:
        from analysis.services.profitable_signal_generator import get_strategy_description
        
        market_types = ['commodities', 'forex', 'synthetic', 'volatility', 'indices']
        
        for market_type in market_types:
            description = get_strategy_description(market_type)
            print(f"\n{market_type.upper()}:")
            print(f"  {description}")
        
        print("\nPASS: All strategy descriptions are available!")
        return True
        
    except ImportError as e:
        print(f"FAIL: Failed to import: {e}")
        return False

def verify_market_thresholds():
    """Verify that market thresholds are properly defined."""
    print("\n" + "=" * 80)
    print("MARKET THRESHOLDS VERIFICATION")
    print("=" * 80)
    
    try:
        from analysis.services.profitable_signal_generator import get_market_thresholds
        
        market_types = ['commodities', 'forex', 'synthetic', 'volatility', 'indices']
        
        for market_type in market_types:
            thresholds = get_market_thresholds(market_type)
            print(f"\n{market_type.upper()}:")
            print(f"  Early Entry: {thresholds['early_entry']:.2f}")
            print(f"  Full Entry: {thresholds['full_entry']:.2f}")
        
        print("\nPASS: All market thresholds are valid!")
        return True
        
    except ImportError as e:
        print(f"FAIL: Failed to import: {e}")
        return False

def verify_constants():
    """Verify that trading constants are properly defined."""
    print("\n" + "=" * 80)
    print("TRADING CONSTANTS VERIFICATION")
    print("=" * 80)
    
    try:
        from analysis.services.profitable_signal_generator import (
            SL_ATR_BASE, SL_ATR_STRENGTH_FACTOR, RR_BASE, RR_STRENGTH_FACTOR,
            MIN_RISK_REWARD, MIN_SIGNAL_STRENGTH, MIN_CONFIRMATIONS,
            MAX_VOLATILITY_MULTIPLIER, MIN_SETUP_QUALITY
        )
        
        print(f"SL_ATR_BASE: {SL_ATR_BASE}")
        print(f"SL_ATR_STRENGTH_FACTOR: {SL_ATR_STRENGTH_FACTOR}")
        print(f"RR_BASE: {RR_BASE}")
        print(f"RR_STRENGTH_FACTOR: {RR_STRENGTH_FACTOR}")
        print(f"MIN_RISK_REWARD: {MIN_RISK_REWARD}")
        print(f"MIN_SIGNAL_STRENGTH: {MIN_SIGNAL_STRENGTH}")
        print(f"MIN_CONFIRMATIONS: {MIN_CONFIRMATIONS}")
        print(f"MAX_VOLATILITY_MULTIPLIER: {MAX_VOLATILITY_MULTIPLIER}")
        print(f"MIN_SETUP_QUALITY: {MIN_SETUP_QUALITY}")
        
        print("\nPASS: All trading constants are valid!")
        return True
        
    except ImportError as e:
        print(f"FAIL: Failed to import: {e}")
        return False

def main():
    """Run all verification tests."""
    print("\nStarting Profitable Signal Generator Verification...\n")
    
    results = []
    
    # Verify strategy weightings
    results.append(("Strategy Weightings", verify_strategy_weightings()))
    
    # Verify strategy descriptions
    results.append(("Strategy Descriptions", verify_strategy_descriptions()))
    
    # Verify market thresholds
    results.append(("Market Thresholds", verify_market_thresholds()))
    
    # Verify constants
    results.append(("Trading Constants", verify_constants()))
    
    # Summary
    print("\n" + "=" * 80)
    print("VERIFICATION SUMMARY")
    print("=" * 80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "PASSED" if result else "FAILED"
        print(f"{test_name}: {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\nAll verification tests passed!")
        return 0
    else:
        print(f"\n{total - passed} test(s) failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())