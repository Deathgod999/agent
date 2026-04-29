import os, json, asyncio, logging
from flask import Flask
from telegram import Bot
from apscheduler.schedulers.background import BackgroundScheduler
import pytz

logging.basicConfig(level=logging.INFO)

BOT_TOKEN   = os.environ["BOT_TOKEN"]
CHANNEL_ID  = int(os.environ["CHANNEL_ID"])   # -1003918280410
IST         = pytz.timezone("Asia/Kolkata")

FILE_IDS_FILE = "file_ids.txt"
PROGRESS_FILE = "progress.json"
EP_PER_DAY    = int(os.environ.get("EP_PER_DAY", "10"))
SLEEP_SEC     = float(os.environ.get("SLEEP_SEC", "1.2"))

app = Flask(__name__)
bot = Bot(BOT_TOKEN)

def load_file_ids():
    with open(FILE_IDS_FILE, "r", encoding="utf-8") as f:
        return [x.strip() for x in f if x.strip()]

def load_next_index():
    if not os.path.exists(PROGRESS_FILE):
        return 0
    with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
        return int(json.load(f).get("next_index", 0))

def save_next_index(i: int):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump({"next_index": i}, f)

async def upload_batch():
    file_ids = load_file_ids()
    total = len(file_ids)
    i = load_next_index()

    if total == 0:
        logging.error("file_ids.txt empty!")
        return

    if i >= total:
        await bot.send_message(CHANNEL_ID, "🎉 All episodes already uploaded.")
        return

    end = min(i + EP_PER_DAY, total)
    ok = 0

    for k in range(i, end):
        ep_no = k + 1
        try:
            await bot.send_audio(
                chat_id=CHANNEL_ID,
                audio=file_ids[k],
                caption=f"🎧 Episode {ep_no}"
            )
            ok += 1
            await asyncio.sleep(SLEEP_SEC)
        except Exception as e:
            logging.exception("Failed ep=%s err=%s", ep_no, e)

    save_next_index(end)
    await bot.send_message(CHANNEL_ID, f"✅ Uploaded {ok} today. Progress: {end}/{total}")

def run_upload():
    asyncio.run(upload_batch())

@app.get("/")
def home():
    total = len(load_file_ids())
    i = load_next_index()
    return {"status": "running", "total": total, "uploaded": i, "next": i+1}

@app.get("/upload-now")
def upload_now():
    run_upload()
    return {"ok": True, "message": "Triggered upload-now"}

@app.get("/reset")
def reset():
    save_next_index(0)
    return {"ok": True, "message": "Progress reset to 0"}

if __name__ == "__main__":
    scheduler = BackgroundScheduler(timezone=IST)
    scheduler.add_job(run_upload, "cron", hour=21, minute=0, id="daily_9pm_ist")
    scheduler.start()
    logging.info("Scheduler started: daily 9:00 PM IST")

    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
