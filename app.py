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
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB limit
ALLOWED_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.webm'}
FFMPEG_TIMEOUT = 300  # 5 minutes timeout
CLEANUP_INTERVAL = 3600  # Clean up files every hour
FILE_RETENTION_HOURS = 2  # Keep files for 2 hours

os.makedirs(UPLOAD_DIR, exist_ok=True)

def validate_video_file(file):
    """Validate uploaded file"""
    if not file:
        return False, "No file provided"
    
    if not file.filename:
        return False, "No filename provided"
    
    # Check file extension
    file_ext = os.path.splitext(file.filename.lower())[1]
    if file_ext not in ALLOWED_EXTENSIONS:
        return False, f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
    
    return True, "Valid"

def cleanup_old_files():
    """Remove files older than FILE_RETENTION_HOURS"""
    try:
        current_time = time.time()
        cutoff_time = current_time - (FILE_RETENTION_HOURS * 3600)
        
        for filename in os.listdir(UPLOAD_DIR):
            file_path = os.path.join(UPLOAD_DIR, filename)
            try:
                if os.path.getctime(file_path) < cutoff_time:
                    os.remove(file_path)
                    logger.info(f"Cleaned up old file: {filename}")
            except OSError as e:
                logger.warning(f"Could not remove file {filename}: {e}")
                
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")

def periodic_cleanup():
    """Run cleanup periodically"""
    while True:
        time.sleep(CLEANUP_INTERVAL)
        cleanup_old_files()

# Start cleanup thread
cleanup_thread = threading.Thread(target=periodic_cleanup, daemon=True)
cleanup_thread.start()

def safe_remove_file(file_path):
    """Safely remove a file"""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Removed file: {file_path}")
    except OSError as e:
        logger.warning(f"Could not remove file {file_path}: {e}")

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

@app.route("/repost-proof", methods=["POST"])
def repost_proof():
    input_path = None
    output_path = None
    
    try:
        # Validate request
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
        
        video = request.files['file']
        
        # Validate file
        is_valid, validation_message = validate_video_file(video)
        if not is_valid:
            return jsonify({"error": validation_message}), 400
        
        # Check file size (Flask doesn't automatically limit this)
        video.seek(0, 2)  # Seek to end
        file_size = video.tell()
        video.seek(0)  # Seek back to beginning
        
        if file_size > MAX_FILE_SIZE:
            return jsonify({
                "error": f"File too large. Max size: {MAX_FILE_SIZE // (1024*1024)}MB"
            }), 400
        
        # Generate unique filenames
        unique_id = str(uuid.uuid4())
        filename = f"{unique_id}.mp4"
        input_path = os.path.join(UPLOAD_DIR, f"in_{filename}")
        output_path = os.path.join(UPLOAD_DIR, f"out_{filename}")
        
        # Save uploaded file
        video.save(input_path)
        logger.info(f"File saved to {input_path}, size: {file_size} bytes")
        
        # Build FFmpeg command
        ffmpeg_cmd, pitch_preserved = build_ffmpeg_command(input_path, output_path)
        
        logger.info("Starting FFmpeg processing")
        logger.debug(f"FFmpeg command: {' '.join(ffmpeg_cmd)}")
        
        # Run FFmpeg with timeout
        start_time = time.time()
        result = subprocess.run(
            ffmpeg_cmd, 
            capture_output=True, 
            text=True,
            timeout=FFMPEG_TIMEOUT
        )
        
        processing_time = time.time() - start_time
        logger.info(f"FFmpeg processing completed in {processing_time:.2f} seconds")
        
        if result.returncode != 0:
            logger.error(f"FFmpeg failed with return code {result.returncode}")
            logger.error(f"FFmpeg stderr: {result.stderr}")
            return jsonify({
                "error": "Video processing failed",
                "details": "FFmpeg processing error"
            }), 500
        
        # Check if output file was created
        if not os.path.exists(output_path):
            logger.error("Output file was not created")
            return jsonify({
                "error": "Processing failed - no output file generated"
            }), 500
        
        # Get output file size
        output_size = os.path.getsize(output_path)
        file_too_large = output_size > 50 * 1024 * 1024
        
        result_json = {
            "success": True,
            "file_size_MB": round(output_size / (1024 * 1024), 2),
            "processing_time_seconds": round(processing_time, 2),
            "pitch_preserved": pitch_preserved
        }
        
        if file_too_large:
            # For large files, provide download link
            public_link = f"https://repost-proof-production.up.railway.app/file-download/{os.path.basename(output_path)}"
            result_json["url"] = public_link
            result_json["message"] = "File too large for direct download, use provided URL"
            return jsonify(result_json)
        else:
            # For smaller files, send directly
            download_name = f"processed_{int(time.time())}.mp4"
            return send_file(
                output_path, 
                as_attachment=True, 
                download_name=download_name,
                mimetype='video/mp4'
            )
    
    except subprocess.TimeoutExpired:
        logger.error(f"FFmpeg processing timed out after {FFMPEG_TIMEOUT} seconds")
        return jsonify({
            "error": "Processing timeout",
            "details": f"Processing took longer than {FFMPEG_TIMEOUT} seconds"
        }), 408
    
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        return jsonify({
            "error": "File processing error",
            "details": "Required file not found during processing"
        }), 500
    
    except PermissionError as e:
        logger.error(f"Permission error: {e}")
        return jsonify({
            "error": "File access error",
            "details": "Permission denied during file processing"
        }), 500
    
    except Exception as e:
        logger.error(f"Unexpected error during processing: {e}")
        logger.error(traceback.format_exc())
        return jsonify({
            "error": "Internal server error",
            "details": "An unexpected error occurred during processing"
        }), 500
    
    finally:
        # Clean up input file immediately
        if input_path:
            safe_remove_file(input_path)

@app.route("/file-download/<filename>")
def download_file(filename):
    """Download processed file"""
    try:
        # Security: only allow files that start with "out_"
        if not filename.startswith("out_"):
            logger.warning(f"Unauthorized download attempt: {filename}")
            return jsonify({"error": "Unauthorized"}), 403
        
        file_path = os.path.join(UPLOAD_DIR, filename)
        
        if not os.path.exists(file_path):
            logger.warning(f"File not found for download: {filename}")
            return jsonify({"error": "File not found"}), 404
        
        logger.info(f"Serving file for download: {filename}")
        return send_file(
            file_path, 
            as_attachment=True,
            mimetype='video/mp4'
        )
    
    except Exception as e:
        logger.error(f"Error serving file {filename}: {e}")
        return jsonify({"error": "File serving error"}), 500

@app.errorhandler(413)
def too_large(e):
    return jsonify({
        "error": "File too large",
        "details": f"Maximum file size is {MAX_FILE_SIZE // (1024*1024)}MB"
    }), 413

if __name__ == "__main__":
    logger.info("Starting repost-proof service")
    logger.info(f"Upload directory: {UPLOAD_DIR}")
    logger.info(f"Max file size: {MAX_FILE_SIZE // (1024*1024)}MB")
    app.run(debug=False, host="0.0.0.0", port=5000)
