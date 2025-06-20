from flask import Flask, request, send_file, jsonify
import os
import uuid
import subprocess
import traceback
import time
import threading
import logging
import signal
import psutil
from datetime import datetime, timedelta
from utils.ffmpeg_mods import build_ffmpeg_command

app = Flask(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
UPLOAD_DIR = "/tmp/repostproof"
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
ALLOWED_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v'}
PROCESSING_TIMEOUT = 600  # 10 minutes for complex processing
MAX_CONCURRENT_JOBS = 2  # Limit concurrent processing

# Global tracking
active_jobs = 0
active_processes = {}

# Ensure upload directory exists
os.makedirs(UPLOAD_DIR, exist_ok=True)

def cleanup_old_files():
    """Clean up files older than 1 hour"""
    try:
        cutoff_time = time.time() - 3600  # 1 hour ago
        for filename in os.listdir(UPLOAD_DIR):
            filepath = os.path.join(UPLOAD_DIR, filename)
            if os.path.isfile(filepath) and os.path.getmtime(filepath) < cutoff_time:
                try:
                    os.remove(filepath)
                    logger.info(f"Cleaned up old file: {filename}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup {filename}: {e}")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

def cleanup_worker():
    """Background worker for file cleanup"""
    while True:
        try:
            cleanup_old_files()
            time.sleep(1800)  # Run every 30 minutes
        except Exception as e:
            logger.error(f"Cleanup worker error: {e}")
            time.sleep(60)

# Start cleanup worker
cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
cleanup_thread.start()

def kill_process_tree(pid):
    """Kill a process and all its children"""
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        for child in children:
            try:
                child.kill()
            except:
                pass
        try:
            parent.kill()
        except:
            pass
    except:
        pass

def validate_video_file(file):
    """Validate uploaded file"""
    if not file.filename:
        return False, "No filename provided"
    
    # Check file extension
    file_ext = os.path.splitext(file.filename.lower())[1]
    if file_ext not in ALLOWED_EXTENSIONS:
        return False, f"File type {file_ext} not supported. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
    
    return True, "Valid"

def get_memory_usage():
    """Get current memory usage"""
    try:
        process = psutil.Process()
        return process.memory_info().rss / 1024 / 1024  # MB
    except:
        return 0

@app.route("/health")
def health_check():
    """Health check endpoint"""
    memory_mb = get_memory_usage()
    disk_free = psutil.disk_usage(UPLOAD_DIR).free / 1024 / 1024 / 1024  # GB
    
    status = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "memory_mb": round(memory_mb, 2),
        "disk_free_gb": round(disk_free, 2),
        "active_jobs": active_jobs,
        "upload_dir": UPLOAD_DIR
    }
    
    # Check if we're in a bad state
    if memory_mb > 1000:  # > 1GB RAM usage
        status["status"] = "warning"
        status["warning"] = "High memory usage"
    
    if disk_free < 1:  # < 1GB free space
        status["status"] = "warning" 
        status["warning"] = "Low disk space"
        
    if active_jobs >= MAX_CONCURRENT_JOBS:
        status["status"] = "busy"
        
    return jsonify(status)

@app.route("/repost-proof", methods=["POST"])
def repost_proof():
    global active_jobs
    
    # Check if we're overloaded
    if active_jobs >= MAX_CONCURRENT_JOBS:
        return jsonify({
            "error": "Server busy", 
            "message": "Too many concurrent requests. Try again later."
        }), 503
    
    # Check memory before processing
    memory_mb = get_memory_usage()
    if memory_mb > 800:  # > 800MB
        return jsonify({
            "error": "Server overloaded",
            "message": "High memory usage. Try again later."
        }), 503
    
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    video = request.files['file']
    if video.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    # Validate file
    is_valid, message = validate_video_file(video)
    if not is_valid:
        return jsonify({"error": message}), 400
    
    # Generate unique filenames
    file_id = str(uuid.uuid4())
    filename = f"{file_id}.mp4"
    input_path = os.path.join(UPLOAD_DIR, f"in_{filename}")
    output_path = os.path.join(UPLOAD_DIR, f"out_{filename}")
    
    process = None
    active_jobs += 1
    
    try:
        logger.info(f"Starting processing job {file_id}")
        
        # Save uploaded file
        video.save(input_path)
        
        # Check file size after saving
        file_size = os.path.getsize(input_path)
        if file_size > MAX_FILE_SIZE:
            return jsonify({
                "error": "File too large",
                "max_size_mb": MAX_FILE_SIZE // (1024 * 1024)
            }), 413
        
        logger.info(f"File saved: {input_path} ({file_size} bytes)")
        
        # Build FFmpeg command (simplified for stability)
        ffmpeg_cmd, pitch_preserved = build_ffmpeg_command(input_path, output_path)
        
        logger.info(f"Running FFmpeg command for job {file_id}")
        logger.debug(f"Command: {' '.join(ffmpeg_cmd)}")
        
        # Run FFmpeg with timeout and monitoring
        start_time = time.time()
        process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            preexec_fn=os.setsid  # Create new process group
        )
        
        active_processes[file_id] = process
        
        try:
            stdout, stderr = process.communicate(timeout=PROCESSING_TIMEOUT)
        except subprocess.TimeoutExpired:
            logger.warning(f"FFmpeg timeout for job {file_id}")
            # Kill the entire process tree
            kill_process_tree(process.pid)
            process.kill()
            process.wait()
            raise RuntimeError("Processing timeout - video too complex or large")
        
        processing_time = time.time() - start_time
        
        if process.returncode != 0:
            logger.error(f"FFmpeg failed for job {file_id}: {stderr}")
            raise RuntimeError(f"Video processing failed: {stderr[:200]}...")
        
        # Check if output file was created
        if not os.path.exists(output_path):
            raise RuntimeError("Output file was not created")
        
        output_size = os.path.getsize(output_path)
        if output_size == 0:
            raise RuntimeError("Output file is empty")
        
        logger.info(f"Processing completed for job {file_id} in {processing_time:.2f}s")
        
        # Prepare response
        file_too_large = output_size > 50 * 1024 * 1024  # 50MB
        
        result_json = {
            "success": True,
            "file_size_mb": round(output_size / (1024 * 1024), 2),
            "processing_time_seconds": round(processing_time, 2),
            "pitch_preserved": pitch_preserved,
            "job_id": file_id
        }
        
        if file_too_large:
            # For large files, provide download link
            public_link = f"{request.host_url}file-download/{os.path.basename(output_path)}"
            result_json["url"] = public_link
            result_json["message"] = "File too large for direct download, use provided URL"
            return jsonify(result_json)
        else:
            # For small files, return directly
            download_name = f"processed_{int(time.time())}.mp4"
            return send_file(
                output_path, 
                as_attachment=True, 
                download_name=download_name,
                mimetype='video/mp4'
            )
            
    except Exception as e:
        logger.error(f"Processing error for job {file_id}: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        error_message = str(e)
        if "timeout" in error_message.lower():
            error_code = 408
        elif "memory" in error_message.lower():
            error_code = 507
        else:
            error_code = 500
            
        return jsonify({
            "error": "Processing failed",
            "details": error_message[:200],  # Limit error message length
            "job_id": file_id
        }), error_code
        
    finally:
        # Cleanup
        active_jobs -= 1
        
        if file_id in active_processes:
            del active_processes[file_id]
        
        # Always cleanup input file
        try:
            if os.path.exists(input_path):
                os.remove(input_path)
                logger.debug(f"Cleaned up input file: {input_path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup input file {input_path}: {e}")
        
        # Cleanup output file after a delay (if it was served directly)
        if 'output_path' in locals() and os.path.exists(output_path):
            def delayed_cleanup():
                time.sleep(300)  # Wait 5 minutes
                try:
                    if os.path.exists(output_path):
                        os.remove(output_path)
                        logger.debug(f"Cleaned up output file: {output_path}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup output file {output_path}: {e}")
            
            threading.Thread(target=delayed_cleanup, daemon=True).start()

@app.route("/file-download/<filename>")
def download_file(filename):
    """Download processed file"""
    # Validate filename to prevent directory traversal
    if '..' in filename or '/' in filename or '\\' in filename:
        return jsonify({"error": "Invalid filename"}), 400
    
    file_path = os.path.join(UPLOAD_DIR, filename)
    
    if not os.path.exists(file_path):
        return jsonify({"error": "File not found or expired"}), 404
    
    try:
        return send_file(
            file_path, 
            as_attachment=True, 
            download_name=f"processed_{filename}",
            mimetype='video/mp4'
        )
    except Exception as e:
        logger.error(f"Download error for {filename}: {e}")
        return jsonify({"error": "Download failed"}), 500

@app.route("/stats")
def stats():
    """Get server statistics"""
    memory_mb = get_memory_usage()
    disk_usage = psutil.disk_usage(UPLOAD_DIR)
    
    return jsonify({
        "active_jobs": active_jobs,
        "memory_usage_mb": round(memory_mb, 2),
        "disk_total_gb": round(disk_usage.total / 1024 / 1024 / 1024, 2),
        "disk_free_gb": round(disk_usage.free / 1024 / 1024 / 1024, 2),
        "disk_used_percent": round((disk_usage.used / disk_usage.total) * 100, 1),
        "upload_dir_files": len(os.listdir(UPLOAD_DIR)) if os.path.exists(UPLOAD_DIR) else 0
    })

# Graceful shutdown handler
def signal_handler(sig, frame):
    logger.info("Shutting down gracefully...")
    # Kill all active processes
    for job_id, process in active_processes.items():
        try:
            kill_process_tree(process.pid)
            logger.info(f"Killed process for job {job_id}")
        except:
            pass
    exit(0)

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
