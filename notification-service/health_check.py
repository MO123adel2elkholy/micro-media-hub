# ...existing code...
import os
import sys
import json
import logging
from pymongo import MongoClient
import pika
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

logging.basicConfig(level=logging.INFO)

def check():
    out = {"services": {}}

    mv = os.environ.get("MONGODB_VIDEOS_URI")
    mm = os.environ.get("MONGODB_MP3S_URI")
    rabbit = os.environ.get("RABBITMQ_URL", "")

    try:
        MongoClient(mv, serverSelectionTimeoutMS=2000).admin.command("ping")
        out["services"]["videos_db"] = "ok"
    except Exception as e:
        out["services"]["videos_db"] = f"error: {e}"

    try:
        MongoClient(mm, serverSelectionTimeoutMS=2000).admin.command("ping")
        out["services"]["mp3_db"] = "ok"
    except Exception as e:
        out["services"]["mp3_db"] = f"error: {e}"

    try:
        if not rabbit:
            raise RuntimeError("RABBITMQ_URL not set")
        params = pika.URLParameters(rabbit)
        conn = pika.BlockingConnection(params)
        conn.close()
        out["services"]["rabbitmq"] = "ok"
    except Exception as e:
        out["services"]["rabbitmq"] = f"error: {e}"

    ok = all(v == "ok" for v in out["services"].values())
    print(json.dumps(out))
    return 0 if ok else 2

if __name__ == "__main__":
    sys.exit(check())