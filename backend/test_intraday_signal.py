"""
Tests for the intraday trading model components:
- compute_dynamic_levels (ATR-based SL/TP with regime + IPO modifiers)
- detect_market_regime (4-state VIX-aware classification)
- risk_check_position_size (risk-per-trade capping)
"""

import sys
sys.path.insert(0, ".")

from trader import compute_dynamic_levels, detect_market_regime, risk_check_position_size


def test_dynamic_levels_basic():
    """Base ATR-based SL/TP in SIDEWAYS regime."""
    result = compute_dynamic_levels(
        current_price=1000.0, atr=10.0, regime="SIDEWAYS", is_ipo=False
    )
    assert result["sl_price"] < 1000.0, f"SL should be below entry: {result}"
    assert result["tp1_price"] > 1000.0, f"TP1 should be above entry: {result}"
    assert result["tp1_pct"] >= 0.5, f"TP1 pct should be >= 0.5%: {result}"
    assert result["tp1_pct"] <= 5.0, f"TP1 pct should be <= 5.0%: {result}"
    assert result["include_tp2"] is False, "SIDEWAYS should not include TP2"
    print(f"  PASS: basic levels = SL {result['sl_pct']}%, TP1 {result['tp1_pct']}%")


def test_dynamic_levels_bull_low_vol():
    """Bullish low-vol regime should have tighter stop, wider target."""
    sideways = compute_dynamic_levels(1000, 10, "SIDEWAYS")
    bull = compute_dynamic_levels(1000, 10, "BULL_LOW_VOL")
    assert bull["sl_price"] > sideways["sl_price"], "Bull SL should be tighter (higher)"
    assert bull["tp1_pct"] >= sideways["tp1_pct"], "Bull TP should be >= Sideways TP"
    assert bull["include_tp2"] is True, "BULL_LOW_VOL should include TP2"
    print(f"  PASS: BULL_LOW_VOL SL={bull['sl_pct']}%, TP1={bull['tp1_pct']}%")


def test_dynamic_levels_bear_high_vol():
    """Bear regime should have wider stop, tighter target."""
    bear = compute_dynamic_levels(1000, 10, "BEAR_HIGH_VOL")
    sideways = compute_dynamic_levels(1000, 10, "SIDEWAYS")
    assert bear["sl_price"] < sideways["sl_price"], "Bear SL should be wider (lower)"
    assert bear["include_tp2"] is False, "BEAR should not include TP2"
    print(f"  PASS: BEAR_HIGH_VOL SL={bear['sl_pct']}%, TP1={bear['tp1_pct']}%")


def test_dynamic_levels_ipo():
    """IPO stocks should get boosted targets and tighter stop."""
    normal = compute_dynamic_levels(1000, 10, "BULL_LOW_VOL", is_ipo=False)
    ipo = compute_dynamic_levels(1000, 10, "BULL_LOW_VOL", is_ipo=True)
    assert ipo["tp1_pct"] >= normal["tp1_pct"], "IPO TP should be >= normal"
    assert ipo["include_tp2"] is True, "IPO should include TP2"
    print(f"  PASS: IPO TP1={ipo['tp1_pct']}% vs normal TP1={normal['tp1_pct']}%")


def test_regime_bullish_low_vol():
    """VIX < 18 + Nifty bullish + bullish stock signals."""
    regime = detect_market_regime(
        indicators={"RSI": 35, "price": 100, "Supertrend_Dir": 1, "MACD": 1, "MACD_Signal": 0},
        vix={"vix_level": 14.0},
        nifty={"trend": "bullish"},
    )
    assert regime["regime"] == "BULL_LOW_VOL", f"Expected BULL_LOW_VOL, got {regime['regime']}"
    print(f"  PASS: regime={regime['regime']}, entry_threshold={regime['entry_threshold']}")


def test_regime_bear_high_vol():
    """VIX >= 22 + Nifty bearish + bearish stock signals."""
    regime = detect_market_regime(
        indicators={"RSI": 70, "price": 90, "Supertrend_Dir": -1, "MACD": -1, "MACD_Signal": 0},
        vix={"vix_level": 25.0},
        nifty={"trend": "bearish"},
    )
    assert regime["regime"] == "BEAR_HIGH_VOL", f"Expected BEAR_HIGH_VOL, got {regime['regime']}"
    assert regime["entry_threshold"] > 0, "Bear should have a positive entry threshold"
    print(f"  PASS: regime={regime['regime']}, entry_threshold={regime['entry_threshold']}")


def test_regime_sideways():
    """Flat Nifty + moderate VIX."""
    regime = detect_market_regime(
        indicators={"RSI": 50, "price": 100},
        vix={"vix_level": 16.0},
        nifty={"trend": "flat"},
    )
    assert regime["regime"] == "SIDEWAYS", f"Expected SIDEWAYS, got {regime['regime']}"
    print(f"  PASS: regime={regime['regime']}")


def test_regime_no_data():
    """No indicators, VIX, or Nifty data — should default to SIDEWAYS."""
    regime = detect_market_regime()
    assert regime["regime"] == "SIDEWAYS", f"Expected SIDEWAYS, got {regime['regime']}"
    print(f"  PASS: no-data regime={regime['regime']}")


def test_risk_position_size():
    """Position size should cap loss at ~1% of capital."""
    balance = 1_000_000.0
    entry = 1000.0
    sl = 985.0  # 15 rupees risk per share
    shares = risk_check_position_size(balance, entry, sl)
    max_loss = shares * (entry - sl)
    assert max_loss <= balance * 0.015 + 1, f"Max loss {max_loss} exceeds 1.5% of capital"
    assert shares > 0, "Should buy at least 1 share"
    print(f"  PASS: shares={shares}, max_loss={max_loss:.0f} ({max_loss/balance*100:.2f}% of capital)")


if __name__ == "__main__":
    tests = [
        ("Dynamic levels — basic", test_dynamic_levels_basic),
        ("Dynamic levels — BULL_LOW_VOL", test_dynamic_levels_bull_low_vol),
        ("Dynamic levels — BEAR_HIGH_VOL", test_dynamic_levels_bear_high_vol),
        ("Dynamic levels — IPO", test_dynamic_levels_ipo),
        ("Regime — BULL_LOW_VOL", test_regime_bullish_low_vol),
        ("Regime — BEAR_HIGH_VOL", test_regime_bear_high_vol),
        ("Regime — SIDEWAYS", test_regime_sideways),
        ("Regime — no data", test_regime_no_data),
        ("Risk position sizing", test_risk_position_size),
    ]

    passed = 0
    failed = 0
    for name, test_fn in tests:
        try:
            print(f"[TEST] {name}")
            test_fn()
            passed += 1
        except Exception as e:
            print(f"  FAIL: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    if failed == 0:
        print("All tests passed!")
    else:
        sys.exit(1)
