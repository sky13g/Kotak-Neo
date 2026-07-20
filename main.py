import os
import sys
import time
import logging
from datetime import datetime, timedelta, time as datetime_time
import pandas as pd
import numpy as np
import requests
from neo_api_client import NeoAPI

# ==============================================================================
# 1. SYSTEM LOGGING FILE SPECIFICATION CONFIGURATION
# ==============================================================================
# Set up file path tracking inside your Ubuntu Linux project directory
log_filename = "nmh5_execution.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_filename),  # Appends data smoothly into the log file
        logging.StreamHandler(sys.stdout)   # Simultaneously routes text prints to the terminal screen
    ]
)
logger = logging.getLogger("NMH5_HARVESTER")

# ==============================================================================
# 2. NMH-5 ENGINE MODE SELECTOR & CONFIGURATION PARAMETERS (SETUP C)
# ==============================================================================
MODE = "PAPER"  # 🟢 CHANGE TO "LIVE" TO DEPLOY REAL CAPITAL VIA KOTAK NEO

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

MAX_DAILY_LOSS_LIMIT = 3000.00  # Strict Intraday Capital Protection Stop

# ==============================================================================
# 3. VIRTUAL PAPER TRADING STATE LEDGER
# ==============================================================================
paper_position = {
    "active": False,
    "symbol": None,
    "type": None,       # "CE" or "PE"
    "strike": 0,
    "entry_spot": 0.0,
    "entry_premium": 0.0,
    "qty": 0
}
paper_realized_pnl = 0.0
last_tracked_day = datetime.now().date()  

# ==============================================================================
# 4. TELEGRAM BROADCASTING SERVICE ENGINE
# ==============================================================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_telegram_alert(message):
    """Sends a real-time status or trade notification directly to your phone."""
    mode_prefix = "🧪 [PAPER MODE] " if MODE == "PAPER" else "⚡ [LIVE TRADING] "
    formatted_message = f"{mode_prefix}{message}"
    
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning(f"Telegram configuration keys missing. Suppressing wire alert.")
        return
        
    url = f"https://telegram.org{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": formatted_message, "parse_mode": "Markdown"}
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            logger.error(f"Telegram API Response Error Code: {response.status_code} | Text: {response.text}")
    except Exception as e:
        logger.error(f"Failed to transmit Telegram network package: {e}")

# ==============================================================================
# 5. SECURE CORE SYSTEM ENVIRONMENT AUTHENTICATION
# ==============================================================================
CONSUMER_KEY = os.environ.get("KOTAK_CONSUMER_KEY")
CONSUMER_SECRET = os.environ.get("KOTAK_CONSUMER_SECRET")
NEO_USERNAME = os.environ.get("KOTAK_USERNAME")
NEO_PASSWORD = os.environ.get("KOTAK_PASSWORD")
MPIN = os.environ.get("KOTAK_MPIN")

if not all([CONSUMER_KEY, CONSUMER_SECRET, NEO_USERNAME, NEO_PASSWORD, MPIN]):
    logger.critical("Fatal Security Error: Missing required system variables in Ubuntu environment.")
    sys.exit(1)

logger.info(f"Initializing Nifty Momentum Harvester Engine Core in [{MODE}] profile...")
logger.info("Establishing secure handshakes with Kotak Neo API infrastructure...")

try:
    client = NeoAPI(consumer_key=CONSUMER_KEY, consumer_secret=CONSUMER_SECRET, environment="PROD")
    client.login(username=NEO_USERNAME, password=NEO_PASSWORD)
    client.session_2fa(OTP=MPIN)
    logger.info("✅ Kotak Neo multi-factor session validation cleared. Bot is active.")
except Exception as login_err:
    logger.critical(f"Failed to authenticate connection session with broker servers: {login_err}")
    sys.exit(1)

# Global tracking variables
long_peak_reached = False
short_floor_reached = False
bot_shutdown_today = False  

# ==============================================================================
# 6. MATH ENGINE & DYNAMIC OPTION EXPIRY CALCULATOR
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

def get_kotak_option_details(spot_price, option_type):
    rounded_base = round(spot_price / 100) * 100
    strike = rounded_base - OPTIONS_OFFSET if option_type == "CE" else rounded_base + OPTIONS_OFFSET
    expiry_string = get_dynamic_expiry_string()
    symbol = f"NIFTY{expiry_string}{option_type}{strike}"
    return symbol, strike

def get_intrinsic_premium(spot_price, strike_price, option_type):
    """Approximates deep ITM pricing structures via mathematical intrinsic value models."""
    if option_type == "CE":
        return max(0.0, spot_price - strike_price)
    else:
        return max(0.0, strike_price - spot_price)

# ==============================================================================
# 7. ENHANCED RISK MONITORING & DATA LOGGING ENGINE
# ==============================================================================
def verify_daily_risk_limits():
    global bot_shutdown_today, paper_realized_pnl
    
    try:
        if MODE == "LIVE":
            trade_report = client.trade_report()
            if not trade_report or 'realised_pnl' not in trade_report:
                return True
            current_realized_pnl = float(trade_report['realised_pnl'])
        else:
            current_realized_pnl = paper_realized_pnl
        
        if current_realized_pnl <= -MAX_DAILY_LOSS_LIMIT:
            if not bot_shutdown_today:
                alert_msg = f"🚨 *EMERGENCY RISK SHUTDOWN* 🚨\n\nDaily loss limit hit: *₹{current_realized_pnl:.2f}*\nMax allowed loss: *₹{MAX_DAILY_LOSS_LIMIT}*\n\nStopping all tracking modules on Ubuntu Server."
                logger.error(f"Risk Management Breach Detected. Total Realized Loss: ₹{current_realized_pnl:.2f}. Executing account lock.")
                send_telegram_alert(alert_msg)
                
                if MODE == "LIVE":
                    positions = client.positions()
                    active_pos = [p for p in positions if p.get('tradingSymbol', '').startswith("NIFTY") and int(p.get('flgOpenPosition', 0)) != 0]
                    for pos in active_pos:
                        sym = pos['tradingSymbol']
                        qty = int(pos['netQty'])
                        client.place_order(exchange_segment="NCO", product="INTRADAY", price="0", order_type="MKT", quantity=str(abs(qty)), trading_symbol=sym, transaction_type="S")
                        logger.info(f"Emergency square-off order placed for live position: {sym}")
                else:
                    paper_position["active"] = False
                
                bot_shutdown_today = True
            return False
            
    except Exception as risk_err:
        logger.error(f"Risk Engine Exception Encountered: {risk_err}")
    return True

def monitor_and_print_dashboard(current, spot, has_active_position, active_symbol):
    """Logs data parameters and prints a system status overview."""
    # Write a clean data log event to the file
    logger.info(f"Spot Check: Nifty={spot:.2f} | ADX={current['ADX']:.2f} | RSI={current['RSI']:.2f} | PositionActive={has_active_position}")
    
    # Render terminal visual display dashboard layout
