import json
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any, Dict

logging.basicConfig(level=logging.INFO)

def notification(message: Any) -> bool:
    payload: Dict

    if isinstance(message, (bytes, bytearray)):
        message = message.decode("utf-8")

    if isinstance(message, dict):
        payload = message
    else:
        try:
            payload = json.loads(message)
        except Exception:
            logging.exception("Invalid message payload")
            return False

    mp3_fid = payload.get("mp3_fid")
    receiver_address = payload.get("username")

    if not receiver_address or mp3_fid or mp3_fid=='none' :
        logging.error("Missing mp3_fid or username in payload: %s", payload)
        return False

    sender_address = os.environ.get("GMAIL_ADDRESS")
    sender_password = os.environ.get("GMAIL_PASSWORD")

    if not sender_address or not sender_password:
        logging.error("GMAIL_ADDRESS or GMAIL_PASSWORD not set in environment")
        return False

    subject = os.environ.get("MP3_EMAIL_SUBJECT", "Your MP3 is ready")
    body = (
        f"Your MP3 is ready.\n\n"
        f"MP3 file_id: {mp3_fid}\n\n"
        "You can download it from the service."
    )

    msg = EmailMessage()
    msg.set_content(body)
    msg["Subject"] = subject
    msg["From"] = sender_address
    msg["To"] = sender_address

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as session:
            session.ehlo()
            session.starttls(context=context)
            session.ehlo()
            session.login(sender_address, sender_password)
            session.send_message(msg)
        logging.info("Mail sent to %s", receiver_address)
        return True
    except Exception:
        logging.exception("Failed to send email")
        return False