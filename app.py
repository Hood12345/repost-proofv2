import os
import tempfile
import uuid
import psutil
import logging
import threading
import atexit
import signal
from pathlib import Path
from flask import Flask, request, jsonify, send_file
from werkzeug.utils import secure_filename
from utils.ffmpeg_mods import process_video_comprehensive_stable, process_video_simple_fallback
import subprocess
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'wmv', 'flv', 'webm', 'm4v'}
MAX_CONCURRENT_JOBS = 2
MEMORY_THRESHOLD = 800 * 1024 * 1024  # 800MB
DISK_THRESHOLD = 1024 * 1024 * 1024   # 1GB

# Global job tracking
active_jobs = {}
job_lock = threading.Lock()

def cleanup_old_files():
    """Clean up old temporary files."""
    try:
        temp_dir = Path(tempfile.gettempdir())
        current_time = time.time()
        
        for file_path in temp_dir.glob("processed_*"):
            try:
                if current_time - file_path.stat().st_mtime > 1800:  # 30 minutes
                    file_path.unlink()
                    logger.info(f"Cleaned up old file: {file_path}")
            except Exception as e:
                logger.warning(f"Could not clean up {file_path}: {e}")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

def cleanup_timer():
    """Run cleanup every 30 minutes."""
    cleanup_old_files()
    timer = threading.Timer(1800, cleanup_timer)
    timer.daemon = True
    timer.start()

def get_system_stats():
    """Get current system resource usage."""
    try:
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return {
            'memory_used': memory.used,
            'memory_percent': memory.percent,
            'disk_used': disk.used,
            'disk_free': disk.free,
            'active_jobs': len(active_jobs)
        }
    except Exception:
        return {'memory_used': 0, 'memory_percent': 0, 'disk_used': 0, 'disk_free': 0, 'active_jobs': 0}

def is_system_overloaded():
    """Check if system is overloaded."""
    stats = get_system_stats()
    
    if stats['memory_used'] > MEMORY_THRESHOLD:
        return True, "High memory usage"
    
    if stats['disk_free'] < DISK_THRESHOLD:
        return True, "Low disk space"
    
    if stats['active_jobs'] >= MAX_CONCURRENT_JOBS:
        return True, "Too many concurrent jobs"
    
    return False, None

def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def kill_ffmpeg_processes():
    """Kill any hanging FFmpeg processes."""
    try:
        for proc in psutil.process_iter(['pid', 'name', 'create_time']):
            if proc.info['name'] == 'ffmpeg':
                # Kill FFmpeg processes older than 10 minutes
                if time.time() - proc.info['create_time'] > 600:
                    proc.kill()
                    logger.info(f"Killed hanging FFmpeg process: {proc.info['pid']}")
    except Exception as e:
        logger.error(f"Error killing FFmpeg processes: {e}")

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    stats = get_system_stats()
    overloaded, reason = is_system_overloaded()
    
    return jsonify({
        'status': 'unhealthy' if overloaded else 'healthy',
        'reason': reason,
        'stats': stats
    })

@app.route('/stats', methods=['GET'])
def get_stats():
    """Get system statistics."""
    return jsonify(get_system_stats())

@app.route('/process', methods=['POST'])
def process_video():
    """Process uploaded video."""
    job_id = str(uuid.uuid4())
    
    try:
        # System checks
        overloaded, reason = is_system_overloaded()
        if overloaded:
            return jsonify({
                'error': 'Service temporarily unavailable',
                'details': reason,
                'job_id': job_id
            }), 503
        
        # File validation
        if 'video' not in request.files:
            return jsonify({
                'error': 'No video file provided',
                'job_id': job_id
            }), 400
        
        file = request.files['video']
        if file.filename == '':
            return jsonify({
                'error': 'No file selected',
                'job_id': job_id
            }), 400
        
        if not allowed_file(file.filename):
            return jsonify({
                'error': 'File type not supported',
                'supported_types': list(ALLOWED_EXTENSIONS),
                'job_id': job_id
            }), 400
        
        # Check file size
        file_content = file.read()
        if len(file_content) > MAX_FILE_SIZE:
            return jsonify({
                'error': 'File too large',
                'max_size_mb': MAX_FILE_SIZE // (1024 * 1024),
                'job_id': job_id
            }), 413
        
        # Create temporary files
        input_filename = secure_filename(file.filename)
        input_path = Path(tempfile.gettempdir()) / f"input_{job_id}_{input_filename}"
        output_path = Path(tempfile.gettempdir()) / f"processed_{job_id}_{input_filename}"
        
        # Save input file
        with open(input_path, 'wb') as f:
            f.write(file_content)
        
        logger.info(f"Job {job_id}: Processing {input_filename} ({len(file_content)} bytes)")
        
        # Add to active jobs
        with job_lock:
            active_jobs[job_id] = {
                'start_time': time.time(),
                'input_file': input_filename,
                'input_path': input_path,
                'output_path': output_path
            }
        
        try:
            # Try comprehensive processing first
            logger.info(f"Job {job_id}: Starting comprehensive processing")
            success = process_video_comprehensive_stable(input_path, output_path)
            
        except Exception as e:
            logger.warning(f"Job {job_id}: Comprehensive processing failed: {str(e)}")
            
            # Check for specific type error
            if "expected str instance" in str(e) or "sequence item" in str(e):
                logger.info(f"Job {job_id}: Type error detected, using fallback")
                success = process_video_simple_fallback(input_path, output_path)
            else:
                # Try fallback processing
                logger.info(f"Job {job_id}: Trying fallback processing")
                success = process_video_simple_fallback(input_path, output_path)
        
        # Check if output file was created
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise Exception("Output file was not created or is empty")
        
        # Cleanup input file
        try:
            input_path.unlink()
        except Exception as e:
            logger.warning(f"Could not delete input file: {e}")
        
        # Remove from active jobs
        with job_lock:
            if job_id in active_jobs:
                processing_time = time.time() - active_jobs[job_id]['start_time']
                del active_jobs[job_id]
                logger.info(f"Job {job_id}: Completed in {processing_time:.1f}s")
        
        # Schedule output file cleanup
        def cleanup_output():
            time.sleep(300)  # 5 minutes
            try:
                if output_path.exists():
                    output_path.unlink()
                    logger.info(f"Cleaned up output file: {output_path}")
            except Exception as e:
                logger.warning(f"Could not clean up output file: {e}")
        
        cleanup_thread = threading.Thread(target=cleanup_output)
        cleanup_thread.daemon = True
        cleanup_thread.start()
        
        # Return processed file
        return send_file(
            str(output_path),
            as_attachment=True,
            download_name=f"processed_{input_filename}",
            mimetype='video/mp4'
        )
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Job {job_id}: Processing failed: {error_msg}")
        
        # Cleanup on error
        with job_lock:
            if job_id in active_jobs:
                job_info = active_jobs[job_id]
                try:
                    if job_info['input_path'].exists():
                        job_info['input_path'].unlink()
                except Exception:
                    pass
                try:
                    if job_info['output_path'].exists():
                        job_info['output_path'].unlink()
                except Exception:
                    pass
                del active_jobs[job_id]
        
        # Return appropriate error response
        if "timed out" in error_msg.lower():
            return jsonify({
                'error': 'Processing timeout',
                'details': 'Video processing took too long',
                'job_id': job_id
            }), 408
        elif "memory" in error_msg.lower() or "space" in error_msg.lower():
            return jsonify({
                'error': 'Resource limitation',
                'details': 'Insufficient system resources',
                'job_id': job_id
            }), 507
        elif "expected str instance" in error_msg or "sequence item" in error_msg:
            return jsonify({
                'error': 'Processing failed',
                'details': 'Internal processing error - please try again',
                'job_id': job_id
            }), 500
        else:
            return jsonify({
                'error': 'Processing failed',
                'details': 'Video processing failed',
                'job_id': job_id
            }), 500

@app.route('/', methods=['GET'])
def index():
    """Basic info endpoint."""
    return jsonify({
        'service': 'Video Processing Service',
        'status': 'running',
        'endpoints': {
            'POST /process': 'Upload and process video',
            'GET /health': 'Health check',
            'GET /stats': 'System statistics'
        }
    })

def cleanup_on_exit():
    """Cleanup function called on exit."""
    logger.info("Shutting down, cleaning up...")
    kill_ffmpeg_processes()
    cleanup_old_files()

# Register cleanup function
atexit.register(cleanup_on_exit)
signal.signal(signal.SIGTERM, lambda signum, frame: exit(0))

# Start cleanup timer
cleanup_timer()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
