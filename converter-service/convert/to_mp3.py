# ...existing code...
import logging
import json
import gridfs
from bson.objectid import ObjectId
from bson.errors import InvalidId
from gridfs.errors import NoFile
import tempfile
import os
import moviepy.editor as mpy
# ...existing code...

def start(message, fs_videos, fs_mp3s, channel):
    """
    Convert a video (referenced by video_fid in message) to mp3, store in fs_mp3s,
    and return the mp3 ObjectId string on success.
    On error return a short error string (e.g. "missing video_fid", "file not found", "conversion failed").
    If message already contains mp3_fid, return it immediately.
    """
    # normalize message (bytes/str/dict)
    if isinstance(message, (bytes, bytearray)):
        try:
            message = message.decode("utf-8")
        except Exception:
            logging.exception("Failed to decode message")
            return "invalid message encoding"

    try:
        msg = json.loads(message) if isinstance(message, str) else message
    except Exception:
        logging.exception("Invalid JSON message")
        return "invalid json"

    # avoid re-processing messages that already contain an mp3_fid
    if msg.get("mp3_fid"):
        logging.info("Skipping already-converted message mp3_fid=%s", msg.get("mp3_fid"))
        return str(msg.get("mp3_fid"))

    video_fid = msg.get("video_fid")
    if not video_fid:
        logging.error("Missing video_fid in message: %s", msg)
        return "missing video_fid"

    try:
        oid = ObjectId(video_fid)
    except InvalidId:
        logging.error("Invalid ObjectId for video_fid: %s", video_fid)
        return "invalid objectid"

    try:
        grid_out = fs_videos.get(oid)
    except NoFile:
        logging.error("GridFS file not found: %s", video_fid)
        return "file not found"
    except Exception:
        logging.exception("Failed to retrieve video from GridFS")
        return "gridfs get failed"

    tmp_video_path = None
    tmp_mp3_path = None
    mp3_fid = None

    try:
        # write video to temp file in memory 
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as vf:
            vf.write(grid_out.read())
            tmp_video_path = vf.name

        # load clip and extract audio
        clip = mpy.VideoFileClip(tmp_video_path)
        audio = clip.audio
        if audio is None:
            logging.error("No audio track found in video: %s", video_fid)
            try:
                clip.close()
            except Exception:
                pass
            return "no audio"

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as af:
            tmp_mp3_path = af.name

        audio.write_audiofile(tmp_mp3_path)

        # tidy up moviepy objects
        try:
            audio.close()
        except Exception:
            pass
        try:
            clip.close()
        except Exception:
            pass

        # store mp3 in GridFS
        with open(tmp_mp3_path, "rb") as f:
            mp3_bytes = f.read()
        mp3_fid = fs_mp3s.put(
            mp3_bytes,
            filename=f"{video_fid}.mp3",
            contentType="audio/mpeg",
            metadata={"source": video_fid},
        )
        logging.info("Stored mp3 in GridFS: %s", mp3_fid)

        # return the mp3 ObjectId string and let the consumer publish notifications
        return str(mp3_fid)

    except Exception:
        logging.exception("Conversion failed")
        try:
            if mp3_fid:
                fs_mp3s.delete(mp3_fid)
        except Exception:
            logging.exception("Failed to delete mp3 after conversion failure")
        return "conversion failed"
    finally:
        for p in (tmp_video_path, tmp_mp3_path):
            try:
                if p and os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass
# ...existing code...