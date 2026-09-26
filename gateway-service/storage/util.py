import json
import logging
import os
import pika

logging.basicConfig(level=logging.INFO)


def upload(f, fs, channel, access):
    """
    Store uploaded file in GridFS and publish a conversion job to VIDEO_QUEUE.
    Returns None on success, otherwise a tuple (message, status_code) or error string.
    """
    try:
        if f is None:
            return ("missing file", 400)

        if channel is None or getattr(channel, "is_closed", True):
            return ("rabbitmq channel unavailable", 503)

        username = access.get("username") or access.get("user")
        if not username:
            return ("missing username in auth payload", 400)

        filename = getattr(f, "filename", "upload")
        f.stream.seek(0)
        data = f.read()

        try:
            file_id = fs.put(data, filename=filename)
        except Exception:
            logging.exception("failed to store file in GridFS")
            return ("failed to store file", 500)

        logging.info("upload: filename=%s, content_length=%s, user=%s", filename, len(data), username)
        logging.info("Stored file in GridFS with id %s", str(file_id))

        queue_name = os.environ.get("VIDEO_QUEUE", "video")

        try:
            channel.queue_declare(queue=queue_name, durable=True)
        except Exception:
            logging.exception("queue_declare failed; attempting publish anyway")

        msg = {
            "video_fid": str(file_id),
            "username": username,
        }

        try:
            channel.basic_publish(
                exchange="",
                routing_key=queue_name,
                body=json.dumps(msg),
                properties=pika.BasicProperties(delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE),
            )
        except Exception:
            logging.exception("failed to publish message to queue %s", queue_name)
            return ("failed to publish conversion job", 503)

        logging.info("Published job to queue %s: %s", queue_name, msg)
        return None

    except Exception:
        logging.exception("upload failed")
        return ("internal server error", 500)