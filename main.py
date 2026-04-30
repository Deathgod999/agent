import os, json, logging, threading
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
from telegram import Bot
from telegram.request import HTTPXRequest
import pytz

logging.basicConfig(level=logging.INFO)

BOT_TOKEN    = os.environ["BOT_TOKEN"]
DUMP_CHANNEL = int(os.environ["DUMP_CHANNEL"])
MAIN_CHANNEL = int(os.environ["MAIN_CHANNEL"])
EP_PER_DAY   = int(os.environ.get("EP_PER_DAY", "10"))
IST          = pytz.timezone("Asia/Kolkata")

PROGRESS_FILE = "progress.json"
app = Flask(__name__)

# Bot with increased pool size and timeout
request = HTTPXRequest(connection_pool_size=8, pool_timeout=30.0)
bot = Bot(token=BOT_TOKEN, request=request)

upload_lock = threading.Lock()

def get_next_msg_id():
    if not os.path.exists(PROGRESS_FILE):
        return 1
    with open(PROGRESS_FILE, "r") as f:
        return int(json.load(f).get("next_msg_id", 1))

def save_next_msg_id(n):
    with open(PROGRESS_FILE, "w") as f:
        json.dump({"next_msg_id": n}, f)

def upload_batch():
    with upload_lock:  # Prevent concurrent runs
        msg_id   = get_next_msg_id()
        uploaded = 0
        misses   = 0

        logging.info(f"Upload shuru: msg_id={msg_id}")

        while uploaded < EP_PER_DAY and misses < 30:
            try:
                bot.copy_message(
                    chat_id=MAIN_CHANNEL,
                    from_chat_id=DUMP_CHANNEL,
                    message_id=msg_id
                )
                uploaded += 1
                misses = 0
                logging.info(f"✅ msg_id={msg_id} ({uploaded}/{EP_PER_DAY})")

            except Exception as e:
                err = str(e).lower()
                if "not found" in err or "can't be copied" in err:
                    misses += 1
                else:
                    logging.warning(f"⚠️ msg_id={msg_id}: {e}")

            msg_id += 1

        save_next_msg_id(msg_id)

        if uploaded > 0:
            bot.send_message(
                MAIN_CHANNEL,
                f"📢 *{uploaded} episodes* upload ho gaye!",
                parse_mode="Markdown"
            )
        else:
            bot.send_message(
                MAIN_CHANNEL,
                "⚠️ Koi audio nahi mila."
            )

@app.get("/")
def home():
    return {
        "status": "✅ Running",
        "next_msg_id": get_next_msg_id(),
        "schedule": "Har 5 minute (TESTING)"
    }

@app.get("/upload-now")
def upload_now():
    threading.Thread(target=upload_batch).start()
    return {"ok": True}

@app.get("/reset")
def reset():
    save_next_msg_id(1)
    return {"ok": True, "msg": "Reset!"}

@app.get("/status")
def status():
    return {"next_msg_id": get_next_msg_id()}

if __name__ == "__main__":
    scheduler = BackgroundScheduler(timezone=IST)
    
    # TESTING: har 5 minute (1 min se zyada safe)
    scheduler.add_job(upload_batch, "interval", minutes=5)
    
    # PRODUCTION (baad me uncomment):
    # scheduler.add_job(upload_batch, "cron", hour=21, minute=0)
    
    scheduler.start()
    logging.info("⏰ Bot chalu! Har 5 minute pe upload.")
    
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
