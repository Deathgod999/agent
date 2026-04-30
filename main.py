import os, json, logging, time, threading
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
from telegram import Bot
import pytz

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

BOT_TOKEN    = os.environ["BOT_TOKEN"]
DUMP_CHANNEL = int(os.environ["DUMP_CHANNEL"])
MAIN_CHANNEL = int(os.environ["MAIN_CHANNEL"])
EP_PER_RUN   = int(os.environ.get("EP_PER_RUN", "2"))
IST          = pytz.timezone("Asia/Kolkata")

PROGRESS_FILE = "progress.json"
app = Flask(__name__)

# v13 fully sync hai, koi issue nahi
bot = Bot(token=BOT_TOKEN)

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
        max_check = 50
        
        logging.info(f"🔄 Upload shuru: msg_id={msg_id}")
        
        while uploaded < EP_PER_RUN and checked < max_check:
            checked += 1
            
            try:
                # Sync call — v13 me koi await nahi chahiye
                bot.copy_message(
                    chat_id=MAIN_CHANNEL,
                    from_chat_id=DUMP_CHANNEL,
                    message_id=msg_id
                )
                
                uploaded += 1
                logging.info(f"✅ msg_id={msg_id} SUCCESSFULLY COPIED! ({uploaded}/{EP_PER_RUN})")
                time.sleep(1)  # Rate limit
                
            except Exception as e:
                err_text = str(e).lower()
                
                if "not found" in err_text or "can't be copied" in err_text or "message to copy not found" in err_text:
                    # Skip
                    pass
                else:
                    logging.warning(f"⚠️ msg_id={msg_id}: {e}")
                    time.sleep(0.5)
            
            msg_id += 1
        
        save_next_msg_id(msg_id)
        
        if uploaded > 0:
            bot.send_message(
                chat_id=MAIN_CHANNEL,
                text=f"✅ {uploaded} episodes upload ho gaye!\nNext start: msg_id {msg_id}"
            )
            logging.info(f"🎉 SUCCESS! {uploaded} episodes channel me bhej diye!")
        else:
            logging.warning(f"⚠️ Koi audio nahi mila (checked {checked} msg_ids)")
            bot.send_message(
                chat_id=MAIN_CHANNEL,
                text=f"⚠️ msg_id {get_next_msg_id()-checked} se {get_next_msg_id()} tak koi audio nahi mila."
            )
    
    except Exception as e:
        logging.error(f"❌ Upload batch failed: {e}")
    
    finally:
        upload_lock.release()

@app.get("/")
def home():
    return {
        "status": "✅ Bot Running (v13 sync)",
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
    return {"next_msg_id": get_next_msg_id()}

if __name__ == "__main__":
    scheduler = BackgroundScheduler(timezone=IST)
    
    scheduler.add_job(
        upload_batch,
        "interval",
        minutes=2,
        id="upload_job",
        max_instances=1
    )
    
    scheduler.start()
    logging.info("⏰ Bot start! Har 2 minute pe upload hoga.")
    
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, threaded=True)
