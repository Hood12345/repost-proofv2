from flask import Flask, request, send_file, jsonify
import os
import uuid
import subprocess
import traceback
import time
import threading
import logging
from datetime import datetime, timedelta
from utils.ffmpeg_mods import build_ffmpeg_command

# Set up proper logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
UPLOAD_DIR = "/tmp/repostproof"
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
ALLOWED_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.webm'}
FFMPEG_TIMEOUT = 300
CLEANUP_INTERVAL = 3600
FILE_RETENTION_HOURS = 2

os.makedirs(UPLOAD_DIR, exist_ok=True)

# Ensure upload directory is writable
try:
    test_file = os.path.join(UPLOAD_DIR, "test.tmp")
    with open(test_file, "w") as f:
        f.write("test")
    os.remove(test_file)
except Exception as e:
    logger.error(f"Upload dir not writable: {e}")
    exit(1)

# Test FFmpeg availability
try:
    subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
except Exception as e:
    logger.error(f"FFmpeg not available: {e}")
    exit(1)

def validate_video_file(file):
    if not file or not file.filename:
        return False, "No file provided"
    ext = os.path.splitext(file.filename.lower())[1]
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
    return True, "Valid"

def cleanup_old_files():
    now = time.time()
    cutoff = now - (FILE_RETENTION_HOURS * 3600)
    for fname in os.listdir(UPLOAD_DIR):
        path = os.path.join(UPLOAD_DIR, fname)
        try:
            if os.path.getctime(path) < cutoff:
                os.remove(path)
                logger.info(f"Cleaned: {fname}")
        except Exception as e:
            logger.warning(f"Cleanup failed for {fname}: {e}")

def delayed_cleanup_start():
    time.sleep(5)
    while True:
        cleanup_old_files()
        time.sleep(CLEANUP_INTERVAL)

threading.Thread(target=delayed_cleanup_start, daemon=True).start()

def safe_remove_file(path):
    try:
        if os.path.exists(path):
            os.remove(path)
            logger.info(f"Deleted: {path}")
    except Exception as e:
        logger.warning(f"Failed to delete {path}: {e}")

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

@app.route("/repost-proof", methods=["POST"])
def repost_proof():
    input_path = output_path = None
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
        video = request.files['file']
        valid, msg = validate_video_file(video)
        if not valid:
            return jsonify({"error": msg}), 400

        video.seek(0, 2)
        size = video.tell()
        video.seek(0)
        if size > MAX_FILE_SIZE:
            return jsonify({"error": f"File too large. Max: {MAX_FILE_SIZE // (1024*1024)}MB"}), 400

        uid = str(uuid.uuid4())
        fname = f"{uid}.mp4"
        input_path = os.path.join(UPLOAD_DIR, f"in_{fname}")
        output_path = os.path.join(UPLOAD_DIR, f"out_{fname}")
        video.save(input_path)

        os.sync()
        time.sleep(0.2)
        if not os.path.exists(input_path) or os.path.getsize(input_path) == 0:
            raise Exception("Input file not ready")

        cmd, pitch_preserved = build_ffmpeg_command(input_path, output_path)
        logger.info("Running FFmpeg...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT)

        if result.returncode != 0:
            logger.error(result.stderr)
            return jsonify({"error": "FFmpeg processing error"}), 500
        if not os.path.exists(output_path):
            return jsonify({"error": "No output file created"}), 500

        out_size = os.path.getsize(output_path)
        too_large = out_size > 50 * 1024 * 1024
        info = {
            "success": True,
            "file_size_MB": round(out_size / (1024 * 1024), 2),
            "processing_time_seconds": round(time.time() - os.path.getctime(output_path), 2),
            "pitch_preserved": pitch_preserved
        }

        if too_large:
            link = f"https://repost-proof-production.up.railway.app/file-download/{os.path.basename(output_path)}"
            info["url"] = link
            info["message"] = "File too large for direct download, use provided URL"
            return jsonify(info)
        else:
            return send_file(output_path, as_attachment=True, download_name=f"processed_{int(time.time())}.mp4", mimetype='video/mp4')

    except subprocess.TimeoutExpired:
        logger.error("FFmpeg timeout")
        return jsonify({"error": "Processing timeout"}), 408
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.error(traceback.format_exc())
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if input_path:
            safe_remove_file(input_path)

@app.route("/file-download/<filename>")
def file_download(filename):
    if not filename.startswith("out_"):
        return jsonify({"error": "Unauthorized"}), 403
    path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(path):
        return jsonify({"error": "File not found"}), 404
    return send_file(path, as_attachment=True, mimetype='video/mp4')

@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": "File too large", "details": f"Max is {MAX_FILE_SIZE // (1024*1024)}MB"}), 413

if __name__ == "__main__":
    logger.info("Starting service...")
    app.run(debug=False, host="0.0.0.0", port=5000)
