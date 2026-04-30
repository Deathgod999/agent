import os
import json
import logging
import threading
import asyncio
from flask import Flask, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from telegram import Bot
from telegram.request import HTTPXRequest
import pytz

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== ENV VARS (Render me set karna hai) =====
BOT_TOKEN    = os.environ["BOT_TOKEN"]
DUMP_CHANNEL = int(os.environ["DUMP_CHANNEL"])   # jahan tum upload karte ho
MAIN_CHANNEL = int(os.environ["MAIN_CHANNEL"])   # jahan bot post kare
EP_PER_RUN   = int(os.environ.get("EP_PER_RUN", "2"))     # 2 episodes per 2 minutes (testing)
MAX_CHECK    = int(os.environ.get("MAX_CHECK", "80"))     # itne msg ids check karke rukega
MISS_LIMIT   = int(os.environ.get("MISS_LIMIT", "30"))    # consecutive miss ke baad stop
SLEEP_SEC    = float(os.environ.get("SLEEP_SEC", "0.8"))  # 0.8 sec gap between sends

IST = pytz.timezone("Asia/Kolkata")
PROGRESS_FILE = "progress.json"

app = Flask(__name__)

# Bigger connection pool to avoid pool timeout
request_obj = HTTPXRequest(
    connection_pool_size=20,
    pool_timeout=60.0,
    read_timeout=30.0,
    write_timeout=30.0,
    connect_timeout=30.0
)
bot = Bot(token=BOT_TOKEN, request=request_obj)

# ===== Progress helpers =====
def get_next_msg_id() -> int:
    if not os.path.exists(PROGRESS_FILE):
        return 1
    try:
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return int(json.load(f).get("next_msg_id", 1))
    except Exception:
        return 1

def save_next_msg_id(n: int):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump({"next_msg_id": n}, f)

# ===== One dedicated asyncio loop (fixes event loop issues) =====
loop = asyncio.new_event_loop()

def _loop_runner():
    asyncio.set_event_loop(loop)
    loop.run_forever()

threading.Thread(target=_loop_runner, daemon=True).start()

# Prevent overlapping runs
run_lock = threading.Lock()

async def upload_batch_async():
    msg_id = get_next_msg_id()
    uploaded = 0
    checked = 0
    misses = 0

    logging.info(f"🔄 Upload start from msg_id={msg_id}")

    while uploaded < EP_PER_RUN and checked < MAX_CHECK:
        checked += 1
        try:
            # Dump -> Main copy
            await bot.copy_message(
                chat_id=MAIN_CHANNEL,
                from_chat_id=DUMP_CHANNEL,
                message_id=msg_id
            )
            uploaded += 1
            misses = 0
            logging.info(f"✅ Copied msg_id={msg_id} ({uploaded}/{EP_PER_RUN})")
            await asyncio.sleep(SLEEP_SEC)

        except Exception as e:
            err = str(e).lower()

            # Common "skip" errors
            if ("not found" in err) or ("message to copy not found" in err) or ("can't be copied" in err):
                misses += 1
            else:
                misses += 1
                logging.warning(f"⚠️ msg_id={msg_id} error: {e}")

            if misses >= MISS_LIMIT:
                logging.info("⛔ Dump me aage kuch nahi mila (miss limit hit). Stop.")
                break

        msg_id += 1

    save_next_msg_id(msg_id)

    # summary message (optional)
    if uploaded > 0:
        try:
            await bot.send_message(
                chat_id=MAIN_CHANNEL,
                text=f"✅ Uploaded {uploaded} item(s). Next msg_id: {msg_id}"
            )
        except Exception as e:
            logging.warning(f"⚠️ summary send failed: {e}")
    else:
        logging.info("⚠️ Uploaded 0 items in this run.")

def trigger_upload():
    # APScheduler + endpoint dono yahi call karenge
    if not run_lock.acquire(blocking=False):
        logging.warning("⚠️ Upload already running, skipping trigger.")
        return

    fut = asyncio.run_coroutine_threadsafe(upload_batch_async(), loop)

    def _done(_f):
        run_lock.release()
        try:
            _f.result()
        except Exception as e:
            logging.warning(f"⚠️ Upload job failed: {e}")

    fut.add_done_callback(_done)

# ===== Flask endpoints =====
@app.get("/")
def home():
    return jsonify({
        "status": "running",
        "next_msg_id": get_next_msg_id(),
        "interval": "2 minutes",
        "ep_per_run": EP_PER_RUN
    })

@app.get("/upload-now")
def upload_now():
    trigger_upload()
    return jsonify({"ok": True, "msg": "triggered"})

@app.get("/reset")
def reset():
    save_next_msg_id(1)
    return jsonify({"ok": True, "msg": "reset to 1"})

@app.get("/status")
def status():
    return jsonify({
        "next_msg_id": get_next_msg_id(),
        "running": run_lock.locked()
    })

# ===== Scheduler =====
if __name__ == "__main__":
    scheduler = BackgroundScheduler(timezone=IST)

    # ✅ TESTING: har 2 minute pe 2 items
    scheduler.add_job(
    trigger_upload,
    "cron",
    hour=19,      # 19 = 7 PM
    minute=0,
    id="daily_7pm",
    max_instances=1,
    coalesce=True,
    misfire_grace_time=600
)

    scheduler.start()
    logging.info("⏰ Started: every 2 minutes upload")

    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
