# Kotak-Neo
# Nifty Momentum Harvester (NMH-5)

NMH-5 is a production-grade, fully automated algorithmic trading system designed specifically for the Nifty 50 Index. Operating on a strict **5-minute candle-close validation framework**, the system uses an optimized triple-criteria entry model alongside an aggressive momentum-harvesting exit layer. It executes orders using 500-point Ultra-Deep In-The-Money (ITM) options via the **Kotak Neo API Client SDK**.

---

## 📊 Core Strategy Architecture (Setup C)

The system is fine-tuned to capture strong intraday volatility trends while insulating capital from consolidation traps:

*   **Execution Timeframe**: 5 Minutes (Strict Candle-Close verification).
*   **Contract Vehicle**: 500-Point Deep ITM Weekly Options (Delta ≈ 0.95, near-zero Theta decay).
*   **Entry Triggers**: 5/10 EMA Golden/Death Crossover + ADX > 18 + RSI Directional Filter (>50 for Longs / <50 for Shorts).
*   **Harvester Exits**: Captures peak momentum spikes by tracking overextended zones (RSI > 82 or < 18) and executing immediate market exits on a micro-reversal.
*   **Risk Engine**: Built-in maximum intraday loss circuit-breaker set at **₹3,000.00**.

---

## 📂 Repository File Structure

Ensure your repository layout matches the following configuration before deploying to your server:

```text
nifty-momentum-harvester/
│
├── .gitignore          # Blocks sensitive files and session logs from GitHub
├── README.md           # System and deployment documentation (This file)
├── requirements.txt    # Application dependencies for the virtual environment
└── main.py             # Core production execution script
```

---

## 🛡️ DevOps Security: Environment Variables

**CRITICAL WARNING:** Never hardcode passwords, pins, or API secret keys inside `main.py`. This script relies entirely on standard Linux environment variables to fetch credentials securely. 

To permanently map your credentials to your Ubuntu VM profile, run the following block in your terminal (replace placeholders with your actual keys):

```bash
echo 'export KOTAK_CONSUMER_KEY="your_kotak_consumer_key"' >> ~/.bashrc
echo 'export KOTAK_CONSUMER_SECRET="your_kotak_consumer_secret"' >> ~/.bashrc
echo 'export KOTAK_USERNAME="your_kotak_login_id"' >> ~/.bashrc
echo 'export KOTAK_PASSWORD="your_kotak_password"' >> ~/.bashrc
echo 'export KOTAK_MPIN="your_6_digit_mpin"' >> ~/.bashrc
echo 'export TELEGRAM_BOT_TOKEN="your_telegram_bot_token_from_botfather"' >> ~/.bashrc
echo 'export TELEGRAM_CHAT_ID="your_personal_telegram_chat_id"' >> ~/.bashrc
source ~/.bashrc
```

---

## 🚀 Headless VM Deployment Guide (Ubuntu Linux)

Follow these terminal steps to initialize your environment and run the bot permanently in the background:

### 1. Provision Server Prerequisites
```bash
sudo apt update && sudo apt install python3-pip python3-venv tmux git -y
```

### 2. Clone Your Repository
```bash
git clone https://github.com
cd nifty-momentum-harvester
```

### 3. Establish Isolated Python Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Deploy Background Headless Daemon View via TMUX
To prevent the execution loop from terminating when you close your SSH terminal shell session, route it inside a persistent `tmux` container:

```bash
# Create a dedicated tmux session window named niftybot
tmux new -s niftybot

# Activate virtual environment inside tmux session
source venv/bin/activate

# Launch the execution script
python3 main.py
```
*   **To Detach cleanly from the view**: Press `CTRL + B`, then release and hit `D`.
*   **To Re-attach and inspect live performance terminal logs**: Run `tmux attach -t niftybot`.

---

## 📈 Server Diagnostics & Auditing

The system keeps a dual-layer transactional record. It streams a visual diagnostic dashboard directly to your active stdout terminal window while maintaining an append-only file log thread for off-hours checking.

### View Real-Time Strategy Logs
```bash
tail -f nmh5_execution.log
```

### Log Levels Reference
*   `[INFO]`: Metric computations, spot evaluations, position sizing alerts, and trade executions.
*   `[WARNING]`: Transient network API timeouts or missed heartbeat packets.
*   `[ERROR]`: Risk management limits breached or automated trade cancellation logs.
*   `[CRITICAL]`: Inverted login credentials or severe platform connection drops causing script termination.

---

## ⚙️ Configuration Tuning (`main.py`)

To change how the system behaves, open `main.py` and modify the control tokens at the top of the file:

```python
MODE = "PAPER"               # Toggle to "LIVE" to deploy actual retail capital
MAX_DAILY_LOSS_LIMIT = 3000  # Tailor the emergency account drawdown shield
```
