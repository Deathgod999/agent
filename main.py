import os, json, asyncio, logging
from flask import Flask
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot
import pytz

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BOT_TOKEN    = os.environ["BOT_TOKEN"]
DUMP_CHANNEL = int(os.environ["DUMP_CHANNEL"])
MAIN_CHANNEL = int(os.environ["MAIN_CHANNEL"])
EP_PER_RUN   = int(os.environ.get("EP_PER_RUN", "2"))   # Har run me 2

PROGRESS_FILE = "progress.json"
IST = pytz.timezone("Asia/Kolkata")

app = Flask(__name__)
bot = Bot(token=BOT_TOKEN)

def get_next_msg_id():
    if not os.path.exists(PROGRESS_FILE):
        return 1
    with open(PROGRESS_FILE, "r") as f:
        return int(json.load(f).get("next_msg_id", 1))

def save_next_msg_id(n):
    with open(PROGRESS_FILE, "w") as f:
        json.dump({"next_msg_id": n}, f)

async def upload_batch():
    msg_id = get_next_msg_id()
    uploaded = 0
    misses = 0

    logging.info(f"Upload shuru from msg_id = {msg_id}")

    while uploaded < EP_PER_RUN and misses < 40:
        try:
            await bot.copy_message(
                chat_id=MAIN_CHANNEL,
                from_chat_id=DUMP_CHANNEL,
                message_id=msg_id
            )
            uploaded += 1
            misses = 0
            logging.info(f"✅ Successfully copied msg_id={msg_id} ({uploaded}/{EP_PER_RUN})")
            await asyncio.sleep(1.0)   # Rate limit safe

        except Exception as e:
            err = str(e).lower()
            if "not found" in err or "can't be copied" in err:
                misses += 1
                logging.info(f"⏭ Skipped msg_id={msg_id} (not found)")
            else:
                logging.error(f"❌ Error at msg_id={msg_id}: {e}")
                await asyncio.sleep(2)

        msg_id += 1

    save_next_msg_id(msg_id)

    if uploaded > 0:
        try:
            await bot.send_message(
                MAIN_CHANNEL,
                f"✅ {uploaded} episodes upload ho gaye!\nNext start: {msg_id}"
            )
        except:
            pass
        logging.info(f"🎉 Batch complete - {uploaded} episodes sent")
    else:
        logging.warning("No episodes found in this batch")

@app.get("/")
def home():
    return {
        "status": "✅ Bot Running",
        "next_msg_id": get_next_msg_id(),
        "running_every": "2 minutes",
        "ep_per_run": EP_PER_RUN
    }

@app.get("/upload-now")
async def upload_now():
    asyncio.create_task(upload_batch())
    return {"ok": True, "message": "Upload started!"}

@app.get("/reset")
def reset():
    save_next_msg_id(1)
    return {"ok": True, "message": "Reset to msg_id 1"}

if __name__ == "__main__":
    scheduler = AsyncIOScheduler(timezone=IST)
    
    # Har 2 minute me 2 episodes
    scheduler.add_job(upload_batch, 'interval', minutes=2)
    
    scheduler.start()
    logging.info("🚀 Bot Started - Har 2 minute me 2 episodes upload honge")

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
