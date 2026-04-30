import os
import json
import logging
import time
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
import requests
import pytz

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# Environment variables
BOT_TOKEN    = os.environ["BOT_TOKEN"]
DUMP_CHANNEL = int(os.environ["DUMP_CHANNEL"])
MAIN_CHANNEL = int(os.environ["MAIN_CHANNEL"])
EP_PER_RUN   = int(os.environ.get("EP_PER_RUN", "2"))
IST          = pytz.timezone("Asia/Kolkata")

PROGRESS_FILE = "progress.json"
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = Flask(__name__)

# Progress management
def get_next_msg_id():
    if not os.path.exists(PROGRESS_FILE):
        return 1
    with open(PROGRESS_FILE, "r") as f:
        return int(json.load(f).get("next_msg_id", 1))

def save_next_msg_id(n):
    with open(PROGRESS_FILE, "w") as f:
        json.dump({"next_msg_id": n}, f)

# Direct API calls (no library)
def copy_message(from_chat, to_chat, msg_id):
    """Copy message using direct API call"""
    url = f"{TELEGRAM_API}/copyMessage"
    data = {
        "from_chat_id": from_chat,
        "chat_id": to_chat,
        "message_id": msg_id
    }
    
    try:
        response = requests.post(url, json=data, timeout=10)
        result = response.json()
        
        if result.get("ok"):
            return True
        else:
            error = result.get("description", "Unknown error")
            if "not found" in error.lower() or "can't be copied" in error.lower():
                return False
            else:
                logging.warning(f"Copy failed: {error}")
                return False
    except Exception as e:
        logging.error(f"Request failed: {e}")
        return False

def send_message(chat_id, text):
    """Send message using direct API call"""
    url = f"{TELEGRAM_API}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=data, timeout=10)
        return response.json().get("ok", False)
    except Exception as e:
        logging.error(f"Send message failed: {e}")
        return False

# Main upload function
def upload_batch():
    msg_id = get_next_msg_id()
    uploaded = 0
    checked = 0
    max_check = 50
    
    logging.info(f"🔄 Upload start: msg_id={msg_id}")
    
    while uploaded < EP_PER_RUN and checked < max_check:
        checked += 1
        
        success = copy_message(DUMP_CHANNEL, MAIN_CHANNEL, msg_id)
        
        if success:
            uploaded += 1
            logging.info(f"✅ msg_id={msg_id} copied ({uploaded}/{EP_PER_RUN})")
            time.sleep(0.5)  # Rate limit protection
        else:
            logging.debug(f"⏩ msg_id={msg_id} skip")
        
        msg_id += 1
    
    save_next_msg_id(msg_id)
    
    # Send summary
    if uploaded > 0:
        message = f"✅ *{uploaded} episodes* upload ho gaye!\n📍 Next: msg_id {msg_id}"
        send_message(MAIN_CHANNEL, message)
        logging.info(f"🎉 {uploaded} episodes uploaded!")
    else:
        logging.warning(f"⚠️ No audio found (checked {checked} messages)")

# Flask routes
@app.get("/")
def home():
    return {
        "status": "✅ Bot Running",
        "next_msg_id": get_next_msg_id(),
        "schedule": "Every 2 minutes",
        "episodes_per_run": EP_PER_RUN
    }

@app.get("/upload-now")
def upload_now():
    upload_batch()
    return {"ok": True, "msg": "Upload done!"}

@app.get("/reset")
def reset():
    save_next_msg_id(1)
    return {"ok": True, "msg": "Reset to msg_id 1"}

@app.get("/status")
def status():
    return {"next_msg_id": get_next_msg_id()}

# Main
if __name__ == "__main__":
    scheduler = BackgroundScheduler(timezone=IST)
    
    # Har 2 minute
    scheduler.add_job(
        upload_batch,
        "interval",
        minutes=2,
        id="upload_job",
        max_instances=1
    )
    
    scheduler.start()
    logging.info("⏰ Bot started! Upload every 2 minutes.")
    
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
