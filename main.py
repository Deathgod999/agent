import os, json, logging, time, threading
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
from telegram import Bot
from telegram.request import HTTPXRequest
import pytz

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

BOT_TOKEN    = os.environ["BOT_TOKEN"]
DUMP_CHANNEL = int(os.environ["DUMP_CHANNEL"])
MAIN_CHANNEL = int(os.environ["MAIN_CHANNEL"])
EP_PER_RUN   = int(os.environ.get("EP_PER_RUN", "2"))  # Har run me kitne
IST          = pytz.timezone("Asia/Kolkata")

PROGRESS_FILE = "progress.json"
app = Flask(__name__)

# Bot with bigger pool and timeout
request_obj = HTTPXRequest(
    connection_pool_size=16,
    pool_timeout=60.0,
    read_timeout=30.0,
    write_timeout=30.0
)
bot = Bot(token=BOT_TOKEN, request=request_obj)

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
    if not upload_lock.acquire(blocking=False):
        logging.warning("⚠️ Upload already running, skipping...")
        return
    
    try:
        msg_id   = get_next_msg_id()
        uploaded = 0
        checked  = 0
        max_check = 50  # max 50 messages check karenge
        
        logging.info(f"🔄 Upload shuru: msg_id={msg_id}")
        
        while uploaded < EP_PER_RUN and checked < max_check:
            checked += 1
            
            try:
                result = bot.copy_message(
                    chat_id=MAIN_CHANNEL,
                    from_chat_id=DUMP_CHANNEL,
                    message_id=msg_id
                )
                
                uploaded += 1
                logging.info(f"✅ msg_id={msg_id} copy hua ({uploaded}/{EP_PER_RUN})")
                time.sleep(0.5)  # Telegram rate limit se bachne ke liye
                
            except Exception as e:
                err_text = str(e).lower()
                
                if "not found" in err_text or "can't be copied" in err_text:
                    # Message nahi mila, skip karo
                    pass
                elif "pool timeout" in err_text or "occupied" in err_text:
                    logging.warning(f"⚠️ Pool busy, waiting...")
                    time.sleep(2)
                    continue  # Retry same msg_id
                else:
                    logging.warning(f"⚠️ msg_id={msg_id}: {e}")
            
            msg_id += 1
        
        save_next_msg_id(msg_id)
        
        # Summary bhejo
        if uploaded > 0:
            bot.send_message(
                MAIN_CHANNEL,
                f"✅ {uploaded} episodes upload ho gaye!\nNext: msg_id {msg_id}",
            )
            logging.info(f"🎉 {uploaded} episodes uploaded successfully!")
        else:
            logging.warning(f"⚠️ Koi audio nahi mila (checked {checked} messages)")
    
    finally:
        upload_lock.release()

@app.get("/")
def home():
    return {
        "status": "✅ Bot Running",
        "next_msg_id": get_next_msg_id(),
        "schedule": "Har 2 minute",
        "episodes_per_run": EP_PER_RUN
    }

@app.get("/upload-now")
def upload_now():
    threading.Thread(target=upload_batch, daemon=True).start()
    return {"ok": True, "msg": "Upload triggered!"}

@app.get("/reset")
def reset():
    save_next_msg_id(1)
    return {"ok": True, "msg": "Reset to msg_id 1"}

@app.get("/status")
def status():
    return {
        "next_msg_id": get_next_msg_id(),
        "lock_acquired": upload_lock.locked()
    }

if __name__ == "__main__":
    scheduler = BackgroundScheduler(timezone=IST)
    
    # Har 2 minute pe upload
    scheduler.add_job(
        upload_batch,
        "interval",
        minutes=2,
        id="upload_job",
        max_instances=1  # Sirf ek instance chale
    )
    
    scheduler.start()
    logging.info("⏰ Scheduler chalu! Har 2 minute pe 2 episodes upload honge.")
    
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, threaded=True)
