import os, json, asyncio, logging
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
from telegram import Bot
import pytz

logging.basicConfig(level=logging.INFO)

# Render se aayenge ye values
BOT_TOKEN    = os.environ["BOT_TOKEN"]
DUMP_CHANNEL = int(os.environ["DUMP_CHANNEL"])   # jahan tum audio daalte ho
MAIN_CHANNEL = int(os.environ["MAIN_CHANNEL"])   # jahan subscribers hain
EP_PER_DAY   = int(os.environ.get("EP_PER_DAY", "10"))
IST          = pytz.timezone("Asia/Kolkata")

PROGRESS_FILE = "progress.json"
app = Flask(__name__)
bot = Bot(BOT_TOKEN)

# ── Progress helpers ──────────────────────────────────
def get_next_msg_id():
    if not os.path.exists(PROGRESS_FILE):
        return 1   # pehli baar: message 1 se shuru
    with open(PROGRESS_FILE, "r") as f:
        return int(json.load(f).get("next_msg_id", 1))

def save_next_msg_id(n):
    with open(PROGRESS_FILE, "w") as f:
        json.dump({"next_msg_id": n}, f)

# ── Main upload logic ─────────────────────────────────
async def upload_batch():
    msg_id   = get_next_msg_id()
    uploaded = 0
    misses   = 0   # consecutive not-found counter

    logging.info(f"Starting upload from message_id={msg_id}")

    while uploaded < EP_PER_DAY:
        try:
            # Dump channel se Main channel pe copy karo
            await bot.copy_message(
                chat_id=MAIN_CHANNEL,
                from_chat_id=DUMP_CHANNEL,
                message_id=msg_id
            )
            uploaded += 1
            misses = 0
            logging.info(f"✅ Copied msg_id={msg_id} ({uploaded}/{EP_PER_DAY})")
            await asyncio.sleep(1.0)

        except Exception as e:
            err = str(e).lower()
            if "not found" in err or "message to copy not found" in err:
                misses += 1
                logging.info(f"⏩ msg_id={msg_id} not found, skipping")
                if misses >= 30:
                    # 30 consecutive miss = dump channel me aur audio nahi
                    logging.info("No more audio in dump channel. Stopping.")
                    break
            else:
                logging.warning(f"⚠️ Error at msg_id={msg_id}: {e}")

        msg_id += 1

    # Progress save karo
    save_next_msg_id(msg_id)

    # Summary
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

# ── Flask routes ──────────────────────────────────────
@app.get("/")
def home():
    n = get_next_msg_id()
    return {
        "status"      : "✅ Bot chal raha hai",
        "next_msg_id" : n,
        "schedule"    : "Daily 9:00 PM IST"
    }

@app.get("/upload-now")
def upload_now():
    run_upload()
    return {"ok": True, "msg": "Upload trigger ho gaya!"}

@app.get("/reset")
def reset():
    save_next_msg_id(1)
    return {"ok": True, "msg": "Reset ho gaya, message 1 se shuru hoga"}

@app.get("/status")
def status():
    return {"next_msg_id": get_next_msg_id()}

# ── Scheduler ─────────────────────────────────────────
if __name__ == "__main__":
    scheduler = BackgroundScheduler(timezone=IST)
    scheduler.add_job(run_upload, "cron", hour=21, minute=0)
    scheduler.start()
    logging.info("⏰ Bot chalu! Daily 9:00 PM IST ko upload hoga.")
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
