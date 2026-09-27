import os
import json
import time
import logging
from pathlib import Path

import pika
from dotenv import load_dotenv

from send import email

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

RABBIT_URL = os.environ.get("RABBITMQ_URL")
NOTIFICATION_QUEUE = os.environ.get("NOTIFICATION_QUEUE", os.environ.get("MP3_QUEUE", "mp3"))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

RABBIT_URL = os.environ.get("RABBITMQ_URL")
NOTIFICATION_QUEUE = os.environ.get("NOTIFICATION_QUEUE", os.environ.get("MP3_QUEUE", "mp3"))

def handle_notification(ch, method, properties, body):
    logging.info("Received notification message on queue '%s': %s", NOTIFICATION_QUEUE, body)
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        payload = {"raw": body.decode("utf-8", errors="replace")}

    result = email.notification(payload)
    if result is False:
        logging.error("Notification failed")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    else:
        logging.info("Notification sent successfully")
        ch.basic_ack(delivery_tag=method.delivery_tag)

def run_consumer():
    backoff = 1
    while True:
        try:
            params = pika.URLParameters(RABBIT_URL)
            params.heartbeat = 60
            params.blocked_connection_timeout = 300
            params.socket_timeout = 10
            conn = pika.BlockingConnection(params)
            ch = conn.channel()
            ch.queue_declare(queue=NOTIFICATION_QUEUE, durable=True)
            ch.basic_qos(prefetch_count=1)
            ch.basic_consume(queue=NOTIFICATION_QUEUE, on_message_callback=handle_notification)
            logging.info("Connected to RabbitMQ, consuming from %s", NOTIFICATION_QUEUE)
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