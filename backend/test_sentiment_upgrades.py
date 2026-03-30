
import sys
import os
sys.path.append(os.path.join(os.getcwd(), "backend"))

from sentiment import analyze_sentiment, _is_relevant, _check_overrides, _is_noise

# Test Cases
headlines = [
    # 1. Guidance Cut (Should be Negative Override)
    "L&T Technology Services cuts revenue forecast, sees mid single-digit growth",
    
    # 2. Irrelevant Noise (Should be Filtered)
    "106-year-old retailer closing all stores in Chapter 11 bankruptcy",
    
    # 3. Metadata Hallucination (Should be Filtered)
    "ICICI Bank Ltd",
    
    # 4. Legit Positive News (Should remain Positive)
    "RBI approves ICICI Group stake hike in eight banks",
    
    # 5. Generic Noise (Should be Filtered)
    "Reliance share price live updates",

    # 6. Alias Check: Tata Steel (Should be Relevant now)
    "Tata Steel reports 10% growth in production",

    # 7. Alias Check: Bajaj Finance (Should be Relevant now)
    "Bajaj Finance profit jumps 20%",
]

ticker_icici = "ICICIBANK.NS"
ticker_tata = "TATASTEEL.NS"
ticker_bajaj = "BAJFINANCE.NS"

print("--- Unit Tests ---")
print(f"1. Is '106-year-old retailer...' relevant for ICICI? {_is_relevant(headlines[1], ticker_icici)} (Expected: False)")
print(f"2. Is 'ICICI Bank Ltd' noise? {_is_noise(headlines[2])} (Expected: True)")
print(f"3. Override score for 'cuts revenue forecast': {_check_overrides(headlines[0])} (Expected: -0.8)")
print(f"4. Is 'Tata Steel reports...' relevant for TATASTEEL? {_is_relevant(headlines[5], ticker_tata)} (Expected: True)")
print(f"5. Is 'Bajaj Finance profit...' relevant for BAJFINANCE? {_is_relevant(headlines[6], ticker_bajaj)} (Expected: True)")

print("\n--- Full Analysis Simulation ---")
# Mocking fetch_news_headlines is hard without mocking the module, 
# so we'll test the logic components directly as above.
