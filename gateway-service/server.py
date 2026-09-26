import io
import json
import os
import atexit
import logging
from urllib.parse import urlparse
import gridfs
import pika
from bson.objectid import ObjectId
from flask import Flask, Response, request, send_file
from flask_pymongo import PyMongo
from pymongo import MongoClient
from auth import validate
from auth_svc import access
from storage import util
import time
from dotenv import load_dotenv

load_dotenv('.env')


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

server = Flask(__name__)

RABBITMQ_URL = os.environ.get(
    "RABBITMQ_URL",
)

# videos DB (used for uploads) - default to 'bolg' if that's your DB
mongo_video = PyMongo(server, uri=os.environ.get("MONGODB_VIDEOS_URI", "mongodb://localhost:27017/bolg"))
fs_videos = gridfs.GridFS(mongo_video.db)

# explicit MongoClient for mp3 DB: prefer MONGODB_MP3S_URI + optional MONGODB_MP3S_DB override
mongo_mp3_uri = os.environ.get("MONGODB_MP3S_URI", "mongodb://localhost:27017/mp3s")
mongo_mp3_client = MongoClient(mongo_mp3_uri)

# determine mp3 DB name (env override -> URI path -> default 'mp3s')
mp3_db_name = os.environ.get("MONGODB_MP3S_DB")
if not mp3_db_name:
    parsed = urlparse(mongo_mp3_uri)
    path = parsed.path.lstrip("/") if parsed.path else ""
    mp3_db_name = path if path else "mp3s"

mongo_mp3_db = mongo_mp3_client[mp3_db_name]
fs_mp3s = gridfs.GridFS(mongo_mp3_db)
logging.info("mp3 DB name: %s (uri=%s)", mongo_mp3_db.name, mongo_mp3_uri)

_rabbit_connection = None
_rabbit_channel = None


def get_rabbit_channel():
    global _rabbit_connection, _rabbit_channel

    try:
        if (
            _rabbit_connection is None
            or getattr(_rabbit_connection, "is_closed", True)
            or _rabbit_channel is None
            or getattr(_rabbit_channel, "is_closed", True)
        ):
            _rabbit_connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
            _rabbit_channel = _rabbit_connection.channel()
            _rabbit_channel.queue_declare(queue=os.environ.get("VIDEO_QUEUE", "video"), durable=True)
            _rabbit_channel.queue_declare(queue=os.environ.get("NOTIFICATION_QUEUE", "mp3"), durable=True)
    except Exception:
        _rabbit_connection = None
        _rabbit_channel = None
        raise

    return _rabbit_channel






@atexit.register
def close_rabbit():
    global _rabbit_connection
    try:
        if _rabbit_connection is not None and not getattr(_rabbit_connection, "is_closed", True):
            _rabbit_connection.close()
    except Exception:
        logging.exception("error closing rabbit connection")


@server.route("/login", methods=["POST"])
def login():
    token, err = access.login(request)
    if not err:
        return token
    return err





@server.route("/health", methods=["GET"])
def health():
    status = {"uptime": time.time(), "services": {}}

    # Mongo (videos)
    try:
        # flask_pymongo PyMongo instance exposes .cx (MongoClient)
        mongo_video.cx.admin.command("ping")
        status["services"]["videos_db"] = "ok"
    except Exception as e:
        logging.exception("videos DB health check failed")
        status["services"]["videos_db"] = f"error: {e}"

    # Mongo (mp3s)
    try:
        mongo_mp3_client.admin.command("ping")
        status["services"]["mp3_db"] = "ok"
    except Exception as e:
        logging.exception("mp3 DB health check failed")
        status["services"]["mp3_db"] = f"error: {e}"

    # RabbitMQ
    try:
        ch = get_rabbit_channel()
        if ch is not None and not getattr(ch, "is_closed", True):
            status["services"]["rabbitmq"] = "ok"
        else:
            status["services"]["rabbitmq"] = "error: channel closed"
    except Exception as e:
        logging.exception("rabbitmq health check failed")
        status["services"]["rabbitmq"] = f"error: {e}"

    unhealthy = any(v.startswith("error") for v in status["services"].values() if isinstance(v, str))
    return (status, 200) if not unhealthy else (status, 503)
# ...existing code...



if __name__ == "__main__":
    server.run(host="0.0.0.0", port=8080)