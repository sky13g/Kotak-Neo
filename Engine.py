import time
from datetime import datetime, time as datetime_time
import pandas as pd
import numpy as np
from neo_api_client import NeoAPI

# 1. NMH-5 MAXIMUM PROFIT PARAMETERS (SETUP C)
TIMEFRAME = "5minute"
ADX_ENTRY_THRESHOLD = 18
RSI_LONG_ENTRY = 50
RSI_SHORT_ENTRY = 50

RSI_LONG_PEAK = 82
RSI_LONG_EXIT = 80

RSI_SHORT_FLOOR = 18
RSI_SHORT_EXIT = 20

OPTIONS_OFFSET = 500  
LOT_SIZE = 65        

# 2. KOTAK NEO API CONFIGURATION & LOGIN
# Install via terminal first: pip install neo-api-client
CONSUMER_KEY = "your_kotak_consumer_key"
CONSUMER_SECRET = "your_kotak_consumer_secret"
NEO_USERNAME = "your_registered_mobile_or_pan"
NEO_PASSWORD = "your_kotak_neo_password"
MPIN = "your_6_digit_mpin"

client = NeoAPI(
    consumer_key=CONSUMER_KEY, 
    consumer_secret=CONSUMER_SECRET, 
    environment="PROD" # Toggle to "UAT" for testing environments
)

# Complete the Kotak Neo secure multi-factor authentication
client.login(username=NEO_USERNAME, password=NEO_PASSWORD)
client.session_2fa(OTP=MPIN)

# State tracking engine arrays
long_peak_reached = False
short_floor_reached = False

def get_kotak_live_candles():
    """Fetches 5-minute historical data points for Nifty 50 Spot from Kotak Neo."""
    # Kotak Neo Master Token for Nifty 50 Spot Index is generally 26000 on NSE
    # We poll historical bars for technical vector mapping
    history = client.historical_data(
        instrument_token="26000",
        exchange="NSE",
        interval="5" # Represents 5-minute intervals
    )
    df = pd.DataFrame(history)
    # Map Kotak's API keys to standard dataframe column headers
    df.rename(columns={'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close'}, inplace=True)
    return df

def calculate_nmh5_vectors(df):
    """Mathematical indicator calculations tailored for NMH-5."""
    df["EMA_5"] = df["close"].ewm(span=5, adjust=False).mean()
    df["EMA_10"] = df["close"].ewm(span=10, adjust=False).mean()
    
    delta = df['close'].diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    df['RSI'] = 100 - (100 / (1 + (pd.Series(gain).ewm(alpha=1/14, adjust=False).mean() / pd.Series(loss).ewm(alpha=1/14, adjust=False).mean())))
    
    df['prev_high'], df['prev_low'], df['prev_close'] = df['high'].shift(1), df['low'].shift(1), df['close'].shift(1)
    tr = df[['high' - df['low'], abs(df['high'] - df['prev_close']), abs(df['low'] - df['prev_close'])]].max(axis=1)
    df['tr_smooth'] = tr.ewm(alpha=1/14, adjust=False).mean()
    
    plus_dm = np.where((df['high'] - df['prev_high'] > df['prev_low'] - df['low']) & (df['high'] - df['prev_high'] > 0), df['high'] - df['prev_high'], 0)
    minus_dm = np.where((df['prev_low'] - df['low'] > df['high'] - df['prev_high']) & (df['prev_low'] - df['low'] > 0), df['prev_low'] - df['low'], 0)
    
    di_plus = (pd.Series(plus_dm).ewm(alpha=1/14, adjust=False).mean() / df['tr_smooth']) * 100
    di_minus = (pd.Series(minus_dm).ewm(alpha=1/14, adjust=False).mean() / df['tr_smooth']) * 100
    df['ADX'] = ((abs(di_plus - di_minus) / (di_plus + di_minus)) * 100).ewm(alpha=1/14, adjust=False).mean()
    
    return df.iloc[-1], df.iloc[-2]

def get_kotak_option_symbol(spot_price, option_type):
    """Calculates contract details according to Kotak Neo symbology formatting."""
    rounded_base = round(spot_price / 100) * 100
    strike = rounded_base - OPTIONS_OFFSET if option_type == "CE" else rounded_base + OPTIONS_OFFSET
    
    # Kotak Option Naming Structure Syntax: NIFTY DDMMMYY P/C STRIKE
    # Example format string: "NIFTY30JUL26C24500"
    current_expiry_string = "30JUL26" 
    return f"NIFTY{current_expiry_string}{option_type[0]}{strike}"

def run_kotak_harvester_loop():
    global long_peak_reached, short_floor_reached
    
    now = datetime.now().time()
    if now < datetime_time(9, 20) or now > datetime_time(15, 10): return

    df = get_kotak_live_candles()
    current, previous = calculate_nmh5_vectors(df)
    spot = current["close"]
    
    # Query Kotak active positional portfolio metrics
    positions = client.positions()
    # Filter to extract any active Nifty option contract allocations
    active_pos = [p for p in positions if p.get('tradingSymbol', '').startswith("NIFTY") and int(p.get('flgOpenPosition', 0)) != 0]

    # 🟢 HARVESTER EMERGENCY PROFIT SECURING LAYER
    if active_pos:
        pos = active_pos[0]
        sym = pos['tradingSymbol']
        qty = int(pos['netQty'])
        
        if sym.count("C") > 0:  # Active Call Option contract identified
            if current["RSI"] > RSI_LONG_PEAK: long_peak_reached = True
            if long_peak_reached and current["RSI"] < RSI_LONG_EXIT:
                client.place_order(
                    exchange_segment="NCO", product="INTRADAY", price="0",
                    order_type="MKT", quantity=str(abs(qty)), trading_symbol=sym,
                    transaction_type="B" if qty < 0 else "S"
                )
                print("💰 Kotak Neo: CE Profit Targets Secured successfully.")
                return
                
        elif sym.count("P") > 0:  # Active Put Option contract identified
            if current["RSI"] < RSI_SHORT_FLOOR: short_floor_reached = True
            if short_floor_reached and current["RSI"] > RSI_SHORT_EXIT:
                client.place_order(
                    exchange_segment="NCO", product="INTRADAY", price="0",
                    order_type="MKT", quantity=str(abs(qty)), trading_symbol=sym,
                    transaction_type="B" if qty < 0 else "S"
                )
                print("💰 Kotak Neo: PE Profit Targets Secured successfully.")
                return

    # 🔵 LOGICAL ENTRY EVALUATION LAYER
    if not active_pos:
        long_peak_reached, short_floor_reached = False, False
        is_gold = previous["EMA_5"] <= previous["EMA_10"] and current["EMA_5"] > current["EMA_10"]
        is_death = previous["EMA_5"] >= previous["EMA_10"] and current["EMA_5"] < current["EMA_10"]
        
        if is_gold and current["ADX"] > ADX_ENTRY_THRESHOLD and current["RSI"] > RSI_LONG_ENTRY:
            target_ce = get_kotak_option_symbol(spot, "CE")
            client.place_order(
                exchange_segment="NCO", product="INTRADAY", price="0",
                order_type="MKT", quantity=str(LOT_SIZE), trading_symbol=target_ce,
                transaction_type="B"
            )
            print(f"🚀 Kotak Entry: Bought 500 ITM Call Option -> {target_ce}")
            
        elif is_death and current["ADX"] > ADX_ENTRY_THRESHOLD and current["RSI"] < RSI_SHORT_ENTRY:
            target_pe = get_kotak_option_symbol(spot, "PE")
            client.place_order(
                exchange_segment="NCO", product="INTRADAY", price="0",
                order_type="MKT", quantity=str(LOT_SIZE), trading_symbol=target_pe,
                transaction_type="B"
            )
            print(f"🛑 Kotak Entry: Bought 500 ITM Put Option -> {target_pe}")

while True:
    try:
        run_kotak_harvester_loop()
    except Exception as e:
        print(f"Kotak Neo System Exception Note: {e}")
    time.sleep(300) # Maintain steady 5-minute synchronization loops
  
