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
# ==============================================================================
# 7. ENHANCED RISK MONITORING & DATA LOGGING ENGINE (COMPLETE)
# ==============================================================================
def verify_daily_risk_limits():
    """Checks your account's total realized P&L and triggers an emergency halt if needed."""
    global bot_shutdown_today, paper_realized_pnl
    
    try:
        if MODE == "LIVE":
            # Fetch real-time realized intraday profit and loss data streams from Kotak Neo API
            trade_report = client.trade_report()
            if not trade_report or 'realised_pnl' not in trade_report:
                return True # Proceed safely if no transactions have been executed yet
            current_realized_pnl = float(trade_report['realised_pnl'])
        else:
            # Maintain virtual validation using internal memory arrays
            current_realized_pnl = paper_realized_pnl
        
        # Trigger an emergency stop if your maximum intraday loss barrier is violated
        if current_realized_pnl <= -MAX_DAILY_LOSS_LIMIT:
            if not bot_shutdown_today:
                alert_msg = (
                    f"🚨 *EMERGENCY RISK SHUTDOWN* 🚨\n\n"
                    f"Daily loss limit breached: *₹{current_realized_pnl:.2f}*\n"
                    f"Max allowed threshold: *₹{MAX_DAILY_LOSS_LIMIT}*\n\n"
                    f"Stopping all tracking loops on the Ubuntu Server for the day."
                )
                logger.error(f"Risk Management Breach! Total Realized Loss: ₹{current_realized_pnl:.2f}. Executing account lock.")
                send_telegram_alert(alert_msg)
                
                if MODE == "LIVE":
                    # Fetch active portfolio positions to square them off immediately
                    positions = client.positions()
                    active_pos = [p for p in positions if p.get('tradingSymbol', '').startswith("NIFTY") and int(p.get('flgOpenPosition', 0)) != 0]
                    for pos in active_pos:
                        sym = pos['tradingSymbol']
                        qty = int(pos['netQty'])
                        # Route emergency market sell/buy order based on the position vector
                        client.place_order(exchange_segment="NCO", product="INTRADAY", price="0", order_type="MKT", quantity=str(abs(qty)), trading_symbol=sym, transaction_type="S")
                        logger.info(f"Emergency square-off order placed for live contract: {sym}")
                else:
                    # Clear out the paper database memory state instantly
                    paper_position["active"] = False
                
                bot_shutdown_today = True
            return False # Block the execution pipeline completely
            
    except Exception as risk_err:
        logger.error(f"Risk Engine Exception Encountered: {risk_err}", exc_info=True)
    return True # Capital boundaries are secure; proceed to entry/exit filters

def monitor_and_print_dashboard(current, spot, has_active_position, active_symbol):
    """Logs data parameters to disk and prints a system status overview to terminal."""
    # Write a clean, timestamped data snapshot straight to your nmh5_execution.log file
    logger.info(f"Spot Check: Nifty={spot:.2f} | ADX={current['ADX']:.2f} | RSI={current['RSI']:.2f} | PositionActive={has_active_position}")
    
    # Render an explicit visual diagnostic console dashboard layout inside your tmux view
    print("\n" + "="*60)
    print(f"📊 NMH-5 ENGINE LIVE MONITORING MATRIX | MODE: {MODE}")
    print("="*60)
    print(f"📈 Nifty Spot Index Close : {spot:.2f}")
    print(f"📉 Analytical Metrics     : ADX: {current['ADX']:.2f} | RSI: {current['RSI']:.2f}")
    print(f"🔄 Moving Average Vector  : EMA(5): {current['EMA_5']:.2f} | EMA(10): {current['EMA_10']:.2f}")
    print("-"*60)
    
    if MODE == "PAPER":
        print(f"💰 Cumulative Realized P&L: ₹{paper_realized_pnl:.2f}")
        if has_active_position:
            current_prem = get_intrinsic_premium(spot, paper_position["strike"], paper_position["type"])
            floating_pnl = (current_prem - paper_position["entry_premium"]) * paper_position["qty"]
            print(f"📂 Active Paper Position  : {active_symbol} (Qty: {paper_position['qty']})")
            print(f"🎟️ Entry Option Premium   : ₹{paper_position['entry_premium']:.2f}")
            print(f"🎯 Current Option Premium : ₹{current_prem:.2f}")
            print(f"📊 Floating Intraday P&L  : ₹{floating_pnl:.2f}")
        else:
            print("📂 Active Paper Position  : NO OPEN POSITIONS")
    else:
        print("⚡ Live account status is monitored via Kotak Trade Console Dashboard directly.")
    print("="*60 + "\n")

    # Render terminal visual display dashboard layout
# ==============================================================================
# 8. UNIFIED CORE EXECUTION DRIVER BLOCK (REPLACEMENT ZONE)
# ==============================================================================
def run_kotak_harvester_loop():
    global long_peak_reached, short_floor_reached, bot_shutdown_today, paper_realized_pnl, last_tracked_day
    
    # 🕒 CRITICAL: Explicitly lock runtime evaluations to Indian Standard Time (IST)
    IST = pytz.timezone('Asia/Kolkata')
    now_dt = datetime.now(IST)
    now_time = now_dt.time()
    
    # AUTOMATED MIDNIGHT BALANCES RESET LOGIC
    if now_dt.date() > last_tracked_day:
        logger.info(f"Midnight IST date rollover detected. Previous day's realized P&L: ₹{paper_realized_pnl:.2f}")
        reset_msg = f"🌅 *New Market Day Initialized*\n\nResetting all paper accounts ledger states.\nPrevious Day Closed Realized Balance: *₹{paper_realized_pnl:.2f}*"
        send_telegram_alert(reset_msg)
        
        # Reset variable conditions
        paper_realized_pnl = 0.0
        paper_position["active"] = False
        bot_shutdown_today = False
        long_peak_reached = False
        short_floor_reached = False
        last_tracked_day = now_dt.date()
        logger.info("Internal strategy memory clear completed for the new day.")
        return

    if now_time < datetime_time(9, 20) or now_time > datetime_time(15, 10): 
        return
        
    if bot_shutdown_today or not verify_daily_risk_limits():
        return

    df = get_kotak_live_candles()
    current, previous = calculate_nmh5_vectors(df)
    spot = current["close"]
    
    has_active_position = False
    active_symbol = ""
    active_qty = 0
    
    if MODE == "LIVE":
        positions = client.positions()
        active_pos = [p for p in positions if p.get('tradingSymbol', '').startswith("NIFTY") and int(p.get('flgOpenPosition', 0)) != 0]
        if active_pos:
            has_active_position = True
            active_symbol = active_pos['tradingSymbol']
            active_qty = int(active_pos['netQty'])
    else:
        if paper_position["active"]:
            has_active_position = True
            active_symbol = paper_position["symbol"]
            active_qty = paper_position["qty"]

    # Trigger terminal display dashboard stream
    monitor_and_print_dashboard(current, spot, has_active_position, active_symbol)

    # 🟢 LAYER 1: UNIFIED HARVESTER PROFIT SECURING MODULE
    if has_active_position:
        if "C" in active_symbol:  
            if current["RSI"] > RSI_LONG_PEAK: 
                long_peak_reached = True
                logger.info(f"RSI breached Long overbought peak boundary ({RSI_LONG_PEAK}). Trailing engine activated.")
            if long_peak_reached and current["RSI"] < RSI_LONG_EXIT:
                logger.info(f"Long Harvester Target Met. Spot RSI: {current['RSI']:.2f}. Closing trade.")
                if MODE == "LIVE":
                    client.place_order(exchange_segment="NCO", product="INTRADAY", price="0", order_type="MKT", quantity=str(abs(active_qty)), trading_symbol=active_symbol, transaction_type="S")
                else:
                    exit_prem = get_intrinsic_premium(spot, paper_position["strike"], "CE")
                    trade_pnl = (exit_prem - paper_position["entry_premium"]) * paper_position["qty"]
                    paper_realized_pnl += trade_pnl
                    paper_position["active"] = False
                    
                send_telegram_alert(f"💰 *Profit Harvested*\n\nClosed Call Contract: `{active_symbol}`\nReason: Spot RSI reached peak value and cooled below {RSI_LONG_EXIT}.")
                return
                
        elif "P" in active_symbol:  
            if current["RSI"] < RSI_SHORT_FLOOR: 
                short_floor_reached = True
                logger.info(f"RSI breached Short oversold floor boundary ({RSI_SHORT_FLOOR}). Trailing engine activated.")
            if short_floor_reached and current["RSI"] > RSI_SHORT_EXIT:
                logger.info(f"Short Harvester Target Met. Spot RSI: {current['RSI']:.2f}. Closing trade.")
                if MODE == "LIVE":
                    client.place_order(exchange_segment="NCO", product="INTRADAY", price="0", order_type="MKT", quantity=str(abs(active_qty)), trading_symbol=active_symbol, transaction_type="S")
                else:
                    exit_prem = get_intrinsic_premium(spot, paper_position["strike"], "PE")
                    trade_pnl = (exit_prem - paper_position["entry_premium"]) * paper_position["qty"]
                    paper_realized_pnl += trade_pnl
                    paper_position["active"] = False
                    
                send_telegram_alert(f"💰 *Profit Harvested*\n\nClosed Put Contract: `{active_symbol}`\nReason: Spot RSI hit floor value and bounced above {RSI_SHORT_EXIT}.")
                return

    # 🔵 LAYER 2: TREND SELECTION ENTRY MODULE
    if not has_active_position:
        long_peak_reached, short_floor_reached = False, False
        is_gold = previous["EMA_5"] <= previous["EMA_10"] and current["EMA_5"] > current["EMA_10"]
        is_death = previous["EMA_5"] >= previous["EMA_10"] and current["EMA_5"] < current["EMA_10"]
        
        if is_gold and current["ADX"] > ADX_ENTRY_THRESHOLD and current["RSI"] > RSI_LONG_ENTRY:
            target_symbol, target_strike = get_kotak_option_details(spot, "CE")
            logger.info(f"Strategy Criteria Matched: Bullish Golden Crossover. Target Contract: {target_symbol}")
            if MODE == "LIVE":
                client.place_order(exchange_segment="NCO", product="INTRADAY", price="0", order_type="MKT", quantity=str(LOT_SIZE), trading_symbol=target_symbol, transaction_type="B")
            else:
                paper_position["active"] = True
                paper_position["symbol"] = target_symbol
                paper_position["type"] = "CE"
                paper_position["strike"] = target_strike
                paper_position["entry_spot"] = spot
                paper_position["entry_premium"] = get_intrinsic_premium(spot, target_strike, "CE")
                paper_position["qty"] = LOT_SIZE
                
            send_telegram_alert(f"🚀 *Long Trade Executed*\n\nBought 500-PT ITM Call Option: `{target_symbol}`\nSpot Entry Reference Level: *{spot}*")
            
        elif is_death and current["ADX"] > ADX_ENTRY_THRESHOLD and current["RSI"] < RSI_SHORT_ENTRY:
            target_symbol, target_strike = get_kotak_option_details(spot, "PE")
            logger.info(f"Strategy Criteria Matched: Bearish Death Crossover. Target Contract: {target_symbol}")
            if MODE == "LIVE":
                client.place_order(exchange_segment="NCO", product="INTRADAY", price="0", order_type="MKT", quantity=str(LOT_SIZE), trading_symbol=target_symbol, transaction_type="B")
            else:
                paper_position["active"] = True
                paper_position["symbol"] = target_symbol
                paper_position["type"] = "PE"
                paper_position["strike"] = target_strike
                paper_position["entry_spot"] = spot
                paper_position["entry_premium"] = get_intrinsic_premium(spot, target_strike, "PE")
                paper_position["qty"] = LOT_SIZE
                
            send_telegram_alert(f"🛑 *Short Trade Executed*\n\nBought 500-PT ITM Put Option: `{target_symbol}`\nSpot Entry Reference Level: *{spot}*")

# Headless production background server execution driver
while True:
    try:
        run_kotak_harvester_loop()
    except Exception as e:
        logger.error(f"Critical Runtime Exception Caught: {e}", exc_info=True)
    time.sleep(300)
    
