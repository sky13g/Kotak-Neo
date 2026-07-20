import os
import sys
import time
from datetime import datetime, timedelta, time as datetime_time
import pandas as pd
import numpy as np
import requests
from neo_api_client import NeoAPI

# ==============================================================================
# 1. OPTIMIZED NMH-5 SYSTEMS CONFIGURATION PARAMETERS
# ==============================================================================
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

# RISK MANAGEMENT ENGINE CONSTANTS
MAX_DAILY_LOSS_LIMIT = 3000.00  # Strict intraday capital protection circuit-breaker

# ==============================================================================
# 2. TELEGRAM BROADCASTING SERVICE ENGINE
# ==============================================================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_telegram_alert(message):
    """Sends a real-time status or trade notification directly to your phone."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"⚠️ Telegram config missing. Print alert: {message}")
        return
        
    url = f"https://telegram.org{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            print(f"❌ Telegram API Error Details: {response.text}")
    except Exception as e:
        print(f"⚠️ Failed to broadcast Telegram notification packet: {e}")

# ==============================================================================
# 3. SECURE CORE SYSTEM ENVIRONMENT AUTHENTICATION
# ==============================================================================
CONSUMER_KEY = os.environ.get("KOTAK_CONSUMER_KEY")
CONSUMER_SECRET = os.environ.get("KOTAK_CONSUMER_SECRET")
NEO_USERNAME = os.environ.get("KOTAK_USERNAME")
NEO_PASSWORD = os.environ.get("KOTAK_PASSWORD")
MPIN = os.environ.get("KOTAK_MPIN")

if not all([CONSUMER_KEY, CONSUMER_SECRET, NEO_USERNAME, NEO_PASSWORD, MPIN]):
    err_txt = "❌ Structural Boot Error: Missing essential environment profiles on Ubuntu shell."
    print(err_txt)
    sys.exit(1)

print("🔄 Connecting to Kotak Neo APIs...")
client = NeoAPI(consumer_key=CONSUMER_KEY, consumer_secret=CONSUMER_SECRET, environment="PROD")
client.login(username=NEO_USERNAME, password=NEO_PASSWORD)
client.session_2fa(OTP=MPIN)
print("✅ Secure API Authenticated Successfully.")

# Global state arrays
long_peak_reached = False
short_floor_reached = False
bot_shutdown_today = False  # Soft lock flag to prevent over-trading after risk limits are breached

# ==============================================================================
# 4. MATH ENGINE & DYNAMIC OPTION EXPIRY CALCULATOR
# ==============================================================================
def get_dynamic_expiry_string():
    """Calculates the current week's Thursday Nifty option contract expiry date string."""
    today = datetime.now()
    days_until_thursday = (3 - today.weekday()) % 7
    expiry_date = today + timedelta(days=days_until_thursday)
    
    if today.weekday() == 3 and today.time() > datetime_time(15, 30):
        expiry_date += timedelta(days=7)
        
    return expiry_date.strftime("%d%b%y").upper()

def get_kotak_live_candles():
    history = client.historical_data(instrument_token="26000", exchange="NSE", interval="5")
    df = pd.DataFrame(history)
    df.rename(columns={'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close'}, inplace=True)
    return df

def calculate_nmh5_vectors(df):
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
    rounded_base = round(spot_price / 100) * 100
    strike = rounded_base - OPTIONS_OFFSET if option_type == "CE" else rounded_base + OPTIONS_OFFSET
    expiry_string = get_dynamic_expiry_string()
    return f"NIFTY{expiry_string}{option_type}{strike}"

# ==============================================================================
# 5. CORE RISK PROTECTION METRICS & EXECUTION ENGINE
# ==============================================================================
def verify_daily_risk_limits():
    """Checks your Kotak account's total realized P&L and triggers an emergency halt if needed."""
    global bot_shutdown_today
    
    try:
        # Fetch realized intraday profit and loss data streams from Kotak Neo API
        trade_report = client.trade_report()
        if not trade_report or 'realised_pnl' not in trade_report:
            return True # Proceed if no trading transactions are found yet

        current_realized_pnl = float(trade_report['realised_pnl'])
        
        # Trigger an emergency stop if realized losses exceed your limit
        if current_realized_pnl <= -MAX_DAILY_LOSS_LIMIT:
            if not bot_shutdown_today:
                alert_msg = f"🚨 *NMH-5 EMERGENCY RISK SHUTDOWN* 🚨\n\nDaily loss limit hit: *₹{current_realized_pnl:.2f}*\nMax allowed loss: *₹{MAX_DAILY_LOSS_LIMIT}*\n\nStopping all bot logic on Ubuntu Server for the day."
                send_telegram_alert(alert_msg)
                print(alert_msg)
                
                # Check for and clear any unexpected open orders left on the account
                positions = client.positions()
                active_pos = [p for p in positions if p.get('tradingSymbol', '').startswith("NIFTY") and int(p.get('flgOpenPosition', 0)) != 0]
                for pos in active_pos:
                    sym = pos['tradingSymbol']
                    qty = int(pos['netQty'])
                    client.place_order(exchange_segment="NCO", product="INTRADAY", price="0", order_type="MKT", quantity=str(abs(qty)), trading_symbol=sym, transaction_type="S")
                
                bot_shutdown_today = True
            return False
            
    except Exception as risk_err:
        print(f"⚠️ Risk Monitor Exception warning token: {risk_err}")
    return True

def run_kotak_harvester_loop():
    global long_peak_reached, short_floor_reached, bot_shutdown_today
    
    now = datetime.now().time()
    
    # Automatically reset the daily risk lock before the morning bell
    if now < datetime_time(9, 15):
        bot_shutdown_today = False
        return

    if now < datetime_time(9, 20) or now > datetime_time(15, 10): 
        return
        
    # Run the risk validation engine first
    if bot_shutdown_today or not verify_daily_risk_limits():
        return

    df = get_kotak_live_candles()
    current, previous = calculate_nmh5_vectors(df)
    spot = current["close"]
    
    positions = client.positions()
    active_pos = [p for p in positions if p.get('tradingSymbol', '').startswith("NIFTY") and int(p.get('flgOpenPosition', 0)) != 0]

    # 🟢 LAYER 1: UNIFIED HARVESTER HARVEST EXITS
    if active_pos:
        pos = active_pos
        sym = pos['tradingSymbol']
        qty = int(pos['netQty'])
        
        if "C" in sym:
            if current["RSI"] > RSI_LONG_PEAK: 
                long_peak_reached = True
            if long_peak_reached and current["RSI"] < RSI_LONG_EXIT:
                client.place_order(exchange_segment="NCO", product="INTRADAY", price="0", order_type="MKT", quantity=str(abs(qty)), trading_symbol=sym, transaction_type="S")
                send_telegram_alert(f"💰 *NMH-5 Profit Harvested*\n\nClosed Call Contract: `{sym}`\nReason: Spot RSI reached peak value and cooled below {RSI_LONG_EXIT}.")
                return
        elif "P" in sym:
            if current["RSI"] < RSI_SHORT_FLOOR: 
                short_floor_reached = True
            if short_floor_reached and current["RSI"] > RSI_SHORT_EXIT:
                client.place_order(exchange_segment="NCO", product="INTRADAY", price="0", order_type="MKT", quantity=str(abs(qty)), trading_symbol=sym, transaction_type="S")
                send_telegram_alert(f"💰 *NMH-5 Profit Harvested*\n\nClosed Put Contract: `{sym}`\nReason: Spot RSI hit floor value and bounced above {RSI_SHORT_EXIT}.")
                return

    # 🔵 LAYER 2: SYSTEM CRITERIA MOMENTUM ENTRIES
    if not active_pos:
        long_peak_reached, short_floor_reached = False, False
        is_gold = previous["EMA_5"] <= previous["EMA_10"] and current["EMA_5"] > current["EMA_10"]
        is_death = previous["EMA_5"] >= previous["EMA_10"] and current["EMA_5"] < current["EMA_10"]

    
