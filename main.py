import os, json, asyncio, logging
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
from telegram import Bot
import pytz

logging.basicConfig(level=logging.INFO)

BOT_TOKEN    = os.environ["BOT_TOKEN"]
DUMP_CHANNEL = int(os.environ["DUMP_CHANNEL"])
MAIN_CHANNEL = int(os.environ["MAIN_CHANNEL"])
EP_PER_DAY   = int(os.environ.get("EP_PER_DAY", "10"))
IST          = pytz.timezone("Asia/Kolkata")

PROGRESS_FILE = "progress.json"
app = Flask(__name__)
bot = Bot(BOT_TOKEN)

def get_next_msg_id():
    if not os.path.exists(PROGRESS_FILE):
        return 1
    with open(PROGRESS_FILE, "r") as f:
        return int(json.load(f).get("next_msg_id", 1))

def save_next_msg_id(n):
    with open(PROGRESS_FILE, "w") as f:
        json.dump({"next_msg_id": n}, f)

async def upload_batch():
    msg_id   = get_next_msg_id()
    uploaded = 0
    misses   = 0

    logging.info(f"Upload shuru: msg_id={msg_id}")

    while uploaded < EP_PER_DAY:
        try:
            await bot.copy_message(
                chat_id=MAIN_CHANNEL,
                from_chat_id=DUMP_CHANNEL,
                message_id=msg_id
            )
            uploaded += 1
            misses = 0
            logging.info(f"✅ msg_id={msg_id} copy hua ({uploaded}/{EP_PER_DAY})")
            await asyncio.sleep(1.0)

        except Exception as e:
            err = str(e).lower()
            if "not found" in err or "message to copy not found" in err:
                misses += 1
                logging.info(f"⏩ msg_id={msg_id} nahi mila, skip")
                if misses >= 30:
                    logging.info("Dump channel me aur audio nahi. Ruk gaya.")
                    break
            else:
                logging.warning(f"⚠️ Error msg_id={msg_id}: {e}")

        msg_id += 1

    save_next_msg_id(msg_id)

    if uploaded > 0:
        await bot.send_message(
            MAIN_CHANNEL,
            f"📢 Aaj ke *{uploaded} episodes* upload ho gaye!",
            parse_mode="Markdown"
        )
    else:
        await bot.send_message(
            MAIN_CHANNEL,
            "⚠️ Aaj koi audio nahi mila dump channel me."
        )

def run_upload():
    asyncio.run(upload_batch())

@app.get("/")
def home():
    return {
        "status"      : "✅ Bot chal raha hai",
        "next_msg_id" : get_next_msg_id(),
        "schedule"    : "Har 1 minute (TESTING MODE)"
    }

@app.get("/upload-now")
def upload_now():
    run_upload()
    return {"ok": True, "msg": "Upload ho gaya!"}

@app.get("/reset")
def reset():
    save_next_msg_id(1)
    return {"ok": True, "msg": "Reset! Message 1 se shuru hoga"}

@app.get("/status")
def status():
    return {"next_msg_id": get_next_msg_id()}

if __name__ == "__main__":
    scheduler = BackgroundScheduler(timezone=IST)

    # ✅ TESTING: har 1 minute
    scheduler.add_job(run_upload, "interval", minutes=1)

    # ❌ PRODUCTION (baad me ye karna):
    # scheduler.add_job(run_upload, "cron", hour=21, minute=0)

    scheduler.start()
    logging.info("⏰ Bot chalu! Har 1 minute pe upload hoga.")
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
