# 1. Update system packages and install python essentials
sudo apt update && sudo apt install python3-pip python3-venv tmux -y

# 2. Clone your GitHub repository to the VM
git clone https://github.com
cd nifty-momentum-harvester

# 3. Create and activate an isolated python environment
python3 -m venv venv
source venv/bin/activate

# 4. Install the required trading library files
pip install -r requirements.txt

# 5. Inject your secure API keys into your current Ubuntu environment profile session
export KOTAK_CONSUMER_KEY="your_actual_consumer_key"
export KOTAK_CONSUMER_SECRET="your_actual_consumer_secret"
export KOTAK_USERNAME="your_kotak_id"
export KOTAK_PASSWORD="your_kotak_password"
export KOTAK_MPIN="your_mpin"

# 6. Open a virtual headless window screen so the bot stays active after you close your terminal
tmux new -s niftybot
python3 main.py




 DevOps Environment Update for UbuntuTo enable Telegram alerts and protect your capital on your Ubuntu Linux VM, you must add two new environment variables to your system.Run these commands in your Ubuntu terminal before starting the script:


export TELEGRAM_BOT_TOKEN="your_bot_token_from_botfather"
export TELEGRAM_CHAT_ID="your_personal_telegram_chat_id"
