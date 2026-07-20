import os
import sys
import time
from datetime import datetime, timedelta, time as datetime_time
import pandas as pd
import numpy as np
from neo_api_client import NeoAPI

# ==============================================================================
# 1. NMH-5 MAXIMUM PROFIT CONFIGURATION PARAMETERS (SETUP C)
# ==============================================================================
TIMEFRAME = "5minute"
ADX_ENTRY_THRESHOLD = 18
RSI_LONG_ENTRY = 50
RSI_SHORT_ENTRY = 50

RSI_LONG_PEAK = 82
RSI_LONG_EXIT = 80

RSI_SHORT_FLOOR = 18
RSI_SHORT_EXIT = 20

OPTIONS_OFFSET = 500  # 500-point Ultra-Deep ITM
LOT_SIZE = 65        # Current NSE Nifty Lot Specification

# ==============================================================================
# 2. SECURE LINUX ENVIRONMENT ENVIRONMENT VARIABLES
# ==============================================================================
CONSUMER_KEY = os.environ.get("KOTAK_CONSUMER_KEY")
CONSUMER_SECRET = os.environ.get("KOTAK_CONSUMER_SECRET")
NEO_USERNAME = os.environ.get("KOTAK_USERNAME")
NEO_PASSWORD = os.environ.get("KOTAK_PASSWORD")
MPIN = os.environ.get("KOTAK_MPIN")

if not all([CONSUMER_KEY, CONSUMER_SECRET, NEO_USERNAME, NEO_PASSWORD, MPIN]):
    print("❌ Fatal Security Error: Missing required Kotak environment variables in Ubuntu shell.")
    sys.exit(1)

# Initialize the Kotak Client Engine
print("🔄 Connecting to Kotak Neo APIs...")
client = NeoAPI(consumer_key=CONSUMER_KEY, consumer_secret=CONSUMER_SECRET, environment="PROD")
client.login(username=NEO_USERNAME, password=NEO_PASSWORD)
client.session_2fa(OTP=MPIN)
print("✅ Secure API Authenticated Successfully.")

# State tracking global arrays
long_peak_reached = False
short_floor_reached = False

# ==============================================================================
# 3. AUTOMATED STRUCTURAL MATH ENGINE
# ==============================================================================
def get_dynamic_expiry_string():
    """Calculates the current week's Thursday Nifty option contract expiry date string."""
    today = datetime.now()
    # Nifty options expire weekly on Thursdays
    days_until_thursday = (3 - today.weekday()) % 7
    expiry_date = today + timedelta(days=days_until_thursday)
    
    # If today is Thursday but past 3:30 PM, roll over to the next week's Thursday contract
    if today.weekday() == 3 and today.time() > datetime_time(15, 30):
        expiry_date += timedelta(days=7)
        
    # Format output to match Kotak formatting syntax: DDMMMYY -> e.g., "23JUL26"
    return expiry_date.strftime("%d%b%y").upper()

def get_kotak_live_candles():
    """Fetches 5-minute historical data for Nifty 50 Spot from Kotak Neo API."""
    history = client.historical_data(instrument_token="26000", exchange="NSE", interval="5")
    df = pd.DataFrame(history)
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
    """Formats contract codes using calculated dynamic weekly expiry values."""
    rounded_base = round(spot_price / 100) * 100
    strike = rounded_base - OPTIONS_OFFSET if option_type == "CE" else rounded_base + OPTIONS_OFFSET
    expiry_string = get_dynamic_expiry_string()
    return f"NIFTY{expiry_string}{option_type}{strike}"

# ==============================================================================
# 4. EXECUTION LOOP LAYER
# ==============================================================================
def run_kotak_harvester_loop():
    global long_peak_reached, short_floor_reached
    
    now = datetime.now().time()
    # Enforce standard Indian market operating hour limits
    if now < datetime_time(9, 20) or now > datetime_time(15, 10): 
        return

    df = get_kotak_live_candles()
    current, previous = calculate_nmh5_vectors(df)
    spot = current["close"]
    
    positions = client.positions()
    active_pos = [p for p in positions if p.get('tradingSymbol', '').startswith("NIFTY") and int(p.get('flgOpenPosition', 0)) != 0]

    # 🟢 HARVESTER EXTREME MOMENTUM PROFIT SECURING LAYER
    if active_pos:
        pos = active_pos
        sym = pos['tradingSymbol']
        qty = int(pos['netQty'])
        
        if "C" in sym:
            if current["RSI"] > RSI_LONG_PEAK: 
                long_peak_reached = True
            if long_peak_reached and current["RSI"] < RSI_LONG_EXIT:
                client.place_order(exchange_segment="NCO", product="INTRADAY", price="0", order_type="MKT", quantity=str(abs(qty)), trading_symbol=sym, transaction_type="S")
                print(f"💰 [{datetime.now().strftime('%H:%M:%S')}] CE Profits Safely Harvested.")
                return
        elif "P" in sym:
            if current["RSI"] < RSI_SHORT_FLOOR: 
                short_floor_reached = True
            if short_floor_reached and current["RSI"] > RSI_SHORT_EXIT:
                client.place_order(exchange_segment="NCO", product="INTRADAY", price="0", order_type="MKT", quantity=str(abs(qty)), trading_symbol=sym, transaction_type="S")
                print(f"💰 [{datetime.now().strftime('%H:%M:%S')}] PE Profits Safely Harvested.")
                return

    # 🔵 TREND CROSSOVER ENTRY SELECTION LAYER
    if not active_pos:
        long_peak_reached, short_floor_reached = False, False
        is_gold = previous["EMA_5"] <= previous["EMA_10"] and current["EMA_5"] > current["EMA_10"]
        is_death = previous["EMA_5"] >= previous["EMA_10"] and current["EMA_5"] < current["EMA_10"]
        
        if is_gold and current["ADX"] > ADX_ENTRY_THRESHOLD and current["RSI"] > RSI_LONG_ENTRY:
            target_ce = get_kotak_option_symbol(spot, "CE")
            client.place_order(exchange_segment="NCO", product="INTRADAY", price="0", order_type="MKT", quantity=str(LOT_SIZE), trading_symbol=target_ce, transaction_type="B")
            print(f"🚀 [{datetime.now().strftime('%H:%M:%S')}] Bought 500 ITM Call -> {target_ce}")
            
        elif is_death and current["ADX"] > ADX_ENTRY_THRESHOLD and current["RSI"] < RSI_SHORT_ENTRY:
            target_pe = get_kotak_option_symbol(spot, "PE")
            client.place_order(exchange_segment="NCO", product="INTRADAY", price="0", order_type="MKT", quantity=str(LOT_SIZE), trading_symbol=target_pe, transaction_type="B")
            print(f"🛑 [{datetime.now().strftime('%H:%M:%S')}] Bought 500 ITM Put -> {target_pe}")

# Infinite headless daemon driver loop
while True:
    try:
        run_kotak_harvester_loop()
    except Exception as e:
        print(f"⚠️ Ubuntu Server Runtime Exception Warning: {e}", file=sys.stderr)
    time.sleep(300) # Synchronize on a steady 5-minute schedule
