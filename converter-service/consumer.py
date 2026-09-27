import os
import json
import time
import logging
import pika
import gridfs
from pymongo import MongoClient
from bson.objectid import ObjectId
from convert import to_mp3
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Mongo setup (from env)
mongo_videos_uri = os.environ.get("MONGODB_VIDEOS_URI")
mongo_mp3s_uri = os.environ.get("MONGODB_MP3S_URI")
client_videos = MongoClient(mongo_videos_uri)
client_mp3s = MongoClient(mongo_mp3s_uri)
db_videos = client_videos.get_default_database()
db_mp3s = client_mp3s.get_default_database()
fs_videos = gridfs.GridFS(db_videos)
fs_mp3s = gridfs.GridFS(db_mp3s)

VIDEO_QUEUE = os.environ.get("VIDEO_QUEUE")
NOTIFICATION_QUEUE = os.environ.get("NOTIFICATION_QUEUE")
RABBIT_URL = os.environ.get("RABBITMQ_URL")

def publish_notification(channel, queue_name, event_type, status, video_fid=None, error=None, username=None, mp3_fid=None):
    payload = {"event": event_type, "status": status}
    if video_fid is not None: payload["video_fid"] = str(video_fid)
    if username is not None: payload["username"] = username
    if mp3_fid is not None: payload["mp3_fid"] = str(mp3_fid)
    if error is not None: payload["error"] = str(error)
    channel.basic_publish(exchange="", routing_key=queue_name, body=json.dumps(payload).encode("utf-8"),
                          properties=pika.BasicProperties(delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE))
    logging.info("Published notification to queue '%s': %s", queue_name, payload)

def process_message(ch, method, properties, body):
    logging.info("Received message on queue '%s': %s", VIDEO_QUEUE, body)
    try:
        msg = json.loads(body.decode("utf-8"))
    except Exception as exc:
        logging.exception("Invalid JSON")
        publish_notification(ch, NOTIFICATION_QUEUE, "video_converted", "failed", error=f"invalid json: {exc}")
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return

    video_fid = msg.get("video_fid")
    username = msg.get("username")
    if not video_fid:
        logging.error("Missing video_fid")
        publish_notification(ch, NOTIFICATION_QUEUE, "video_converted", "failed", video_fid=None, error="missing video_fid", username=username)
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return

    try:
        result = to_mp3.start(msg, fs_videos, fs_mp3s, ch)
        if isinstance(result, str) and len(result) == 24:
            logging.info("Conversion succeeded, mp3_fid=%s", result)
            publish_notification(ch, NOTIFICATION_QUEUE, "video_converted", "success", video_fid=video_fid, username=username, mp3_fid=result)
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        fatal = {"invalid objectid", "invalid json", "missing video_fid", "invalid message encoding", "file not found"}
        if isinstance(result, str) and result in fatal:
            logging.error("Conversion failed (fatal): %s", result)
            publish_notification(ch, NOTIFICATION_QUEUE, "video_converted", "failed", video_fid=video_fid, username=username, error=result)
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        logging.error("Conversion failed/transient: %s", result)
        publish_notification(ch, NOTIFICATION_QUEUE, "video_converted", "failed", video_fid=video_fid, username=username, error=str(result))
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    except Exception as exc:
        logging.exception("Unhandled error processing message")
        publish_notification(ch, NOTIFICATION_QUEUE, "video_converted", "failed", video_fid=video_fid, username=username, error=str(exc))
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

def run_consumer():
    backoff = 1
    while True:
        try:
            params = pika.URLParameters(RABBIT_URL)
            print(f"RABBIT_URL => {RABBIT_URL}")
            params.heartbeat = 60
            params.blocked_connection_timeout = 300
            params.socket_timeout = 10
            conn = pika.BlockingConnection(params)
            ch = conn.channel()
            ch.queue_declare(queue=VIDEO_QUEUE, durable=True)
            ch.queue_declare(queue=NOTIFICATION_QUEUE, durable=True)
            ch.basic_qos(prefetch_count=1)
            ch.basic_consume(queue=VIDEO_QUEUE, on_message_callback=process_message)
            logging.info("Connected to RabbitMQ, consuming from %s", VIDEO_QUEUE)
            backoff = 1
            ch.start_consuming()
        except KeyboardInterrupt:
            try:
                conn.close()
            except Exception:
                pass
            break
        except Exception:
            logging.exception("AMQP connection lost, reconnecting in %s seconds", backoff)
            try:
                conn.close()
            except Exception:
                pass
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)

if __name__ == "__main__":
    run_consumer()