import os
import random
import subprocess
import tempfile
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def get_video_info(input_path):
    """Get video information using ffprobe."""
    try:
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', str(input_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            video_stream = next((s for s in data['streams'] if s['codec_type'] == 'video'), None)
            audio_stream = next((s for s in data['streams'] if s['codec_type'] == 'audio'), None)
            
            duration = float(data['format'].get('duration', 0))
            width = int(video_stream.get('width', 1920)) if video_stream else 1920
            height = int(video_stream.get('height', 1080)) if video_stream else 1080
            
            return {
                'duration': duration,
                'width': width,
                'height': height,
                'has_audio': audio_stream is not None
            }
    except Exception as e:
        logger.error(f"Error getting video info: {e}")
    
    return {'duration': 30, 'width': 1920, 'height': 1080, 'has_audio': True}

def create_invisible_watermark(width, height, position="topleft"):
    """Create an invisible watermark filter."""
    positions = {
        'topleft': (10, 10),
        'topright': (width - 60, 10),
        'bottomleft': (10, height - 30),
        'bottomright': (width - 60, height - 30),
        'center': (width // 2 - 25, height // 2 - 10)
    }
    
    x, y = positions.get(position, (10, 10))
    
    # Create invisible text with very low opacity
    return f"drawtext=text='ID{random.randint(1000,9999)}':x={x}:y={y}:fontsize=12:fontcolor=white@0.01"

def process_video_comprehensive_stable(input_path, output_path):
    """Process video with maximum modifications while maintaining stability."""
    try:
        # Get video info
        info = get_video_info(input_path)
        duration = info['duration']
        width = info['width']
        height = info['height']
        has_audio = info['has_audio']
        
        # Determine processing level based on video length
        is_long_video = duration > 180  # 3 minutes
        
        logger.info(f"Processing video: {duration:.1f}s, {width}x{height}, audio: {has_audio}")
        
        # Build command with proper string conversion
        cmd = ['ffmpeg', '-y', '-i', str(input_path)]
        
        # Video filters - all values converted to strings
        video_filters = []
        
        # 1. Geometric transformations (subtle for stability)
        crop_x = random.randint(2, 4)
        crop_y = random.randint(2, 4)
        video_filters.append(f"crop=iw-{crop_x}:ih-{crop_y}:{crop_x//2}:{crop_y//2}")
        
        pad_x = random.randint(1, 2)
        pad_y = random.randint(1, 2)
        video_filters.append(f"pad=iw+{pad_x}:ih+{pad_y}:{pad_x//2}:{pad_y//2}:black")
        
        # Rotation (very subtle)
        rotation = random.uniform(-1.0, 1.0)
        video_filters.append(f"rotate={rotation}*PI/180:fillcolor=black")
        
        # 2. Color modifications
        brightness = random.uniform(-0.05, 0.05)
        contrast = random.uniform(0.95, 1.05)
        saturation = random.uniform(0.9, 1.1)
        gamma = random.uniform(0.9, 1.1)
        hue_shift = random.uniform(-5, 5)
        
        video_filters.append(f"eq=brightness={brightness:.3f}:contrast={contrast:.3f}:saturation={saturation:.3f}:gamma={gamma:.3f}")
        video_filters.append(f"hue=h={hue_shift:.1f}")
        
        # 3. Individual RGB gamma (advanced color modification)
        gamma_r = random.uniform(0.95, 1.05)
        gamma_g = random.uniform(0.95, 1.05)
        gamma_b = random.uniform(0.95, 1.05)
        video_filters.append(f"eq=gamma_r={gamma_r:.3f}:gamma_g={gamma_g:.3f}:gamma_b={gamma_b:.3f}")
        
        # 4. Noise and sharpening
        noise_strength = random.randint(3, 8) if not is_long_video else random.randint(2, 5)
        video_filters.append(f"noise=alls={noise_strength}:allf=t")
        
        sharpen_amount = random.uniform(0.1, 0.2)
        video_filters.append(f"unsharp=5:5:{sharpen_amount:.2f}")
        
        # 5. Invisible watermarks (5 different positions)
        watermark_positions = ['topleft', 'topright', 'bottomleft', 'bottomright', 'center']
        for pos in watermark_positions:
            video_filters.append(create_invisible_watermark(width, height, pos))
        
        # 6. Timestamp watermark (invisible)
        import time
        timestamp = int(time.time())
        video_filters.append(f"drawtext=text='T{timestamp}':x=5:y=5:fontsize=8:fontcolor=white@0.005")
        
        # Apply video filters
        cmd.extend(['-vf', ','.join(video_filters)])
        
        # Audio processing (if audio exists)
        if has_audio:
            audio_filters = []
            
            # Tempo and pitch modifications
            tempo_change = random.uniform(0.98, 1.02)
            pitch_shift = random.uniform(-20, 20)  # cents
            
            audio_filters.append(f"atempo={tempo_change:.4f}")
            if abs(pitch_shift) > 5:  # Only apply if significant
                audio_filters.append(f"asetrate=44100*{1 + pitch_shift/1200:.6f},aresample=44100")
            
            # Volume adjustment
            volume_db = random.uniform(-0.5, 0.5)
            audio_filters.append(f"volume={volume_db:.2f}dB")
            
            # Multi-band EQ
            eq_200 = random.uniform(-0.8, 0.8)
            eq_1k = random.uniform(-0.3, 0.3)
            eq_5k = random.uniform(-0.8, 0.8)
            eq_10k = random.uniform(-0.3, 0.3)
            
            audio_filters.append(f"equalizer=f=200:t=o:w=100:g={eq_200:.1f}")
            audio_filters.append(f"equalizer=f=1000:t=o:w=100:g={eq_1k:.1f}")
            audio_filters.append(f"equalizer=f=5000:t=o:w=100:g={eq_5k:.1f}")
            audio_filters.append(f"equalizer=f=10000:t=o:w=100:g={eq_10k:.1f}")
            
            # High/low pass filters (subtle)
            audio_filters.append("highpass=f=20")
            audio_filters.append("lowpass=f=18000")
            
            cmd.extend(['-af', ','.join(audio_filters)])
            
            # Audio codec settings
            audio_bitrate = random.choice(['96k', '128k', '160k', '192k'])
            cmd.extend(['-c:a', 'aac', '-b:a', audio_bitrate])
        else:
            cmd.extend(['-an'])  # No audio
        
        # Video encoding settings (extensive variations)
        crf = str(random.randint(20, 25))
        preset = random.choice(['fast', 'medium', 'slow'])
        profile = random.choice(['baseline', 'main', 'high'])
        pixel_format = random.choice(['yuv420p', 'yuv422p'])
        
        cmd.extend([
            '-c:v', 'libx264',
            '-crf', crf,
            '-preset', preset,
            '-profile:v', profile,
            '-pix_fmt', pixel_format
        ])
        
        # GOP and frame settings
        gop_size = str(random.randint(15, 60))
        b_frames = str(random.randint(1, 3))
        ref_frames = str(random.randint(2, 4))
        
        cmd.extend([
            '-g', gop_size,
            '-bf', b_frames,
            '-refs', ref_frames
        ])
        
        # Frame rate modification
        fps_options = ['23.976', '24', '25', '29.97', '30']
        target_fps = random.choice(fps_options)
        cmd.extend(['-r', target_fps])
        
        # Color space and range
        colorspace = random.choice(['bt709', 'bt470bg', 'smpte170m'])
        cmd.extend([
            '-colorspace', colorspace,
            '-color_range', 'tv'
        ])
        
        # Metadata removal and addition
        cmd.extend([
            '-map_metadata', '-1',
            '-metadata', f'title=Processed_{random.randint(1000, 9999)}',
            '-metadata', f'comment=Optimized_{random.randint(100, 999)}',
            '-metadata', f'description=Enhanced_Video_{timestamp}',
            '-metadata', f'encoder=CustomProcessor_v{random.randint(1, 5)}.{random.randint(0, 9)}'
        ])
        
        # Output file
        cmd.append(str(output_path))
        
        # Convert all arguments to strings to prevent type errors
        cmd = [str(arg) for arg in cmd]
        
        # Log command for debugging (truncated)
        logger.info(f"FFmpeg command length: {len(cmd)} arguments")
        logger.info(f"Processing settings: CRF={crf}, Preset={preset}, FPS={target_fps}")
        
        # Execute command with timeout
        timeout = 600 if is_long_video else 300  # 10 min for long videos, 5 min for short
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=tempfile.gettempdir()
        )
        
        if result.returncode != 0:
            logger.error(f"FFmpeg failed with return code {result.returncode}")
            logger.error(f"FFmpeg stderr: {result.stderr}")
            raise Exception(f"FFmpeg processing failed: {result.stderr}")
        
        logger.info("Video processing completed successfully")
        return True
        
    except subprocess.TimeoutExpired:
        logger.error("FFmpeg processing timed out")
        raise Exception("Video processing timed out")
    except Exception as e:
        logger.error(f"Video processing error: {str(e)}")
        raise Exception(f"Processing failed: {str(e)}")

def process_video_simple_fallback(input_path, output_path):
    """Simple fallback processing for problematic videos."""
    try:
        cmd = [
            'ffmpeg', '-y', '-i', str(input_path),
            '-vf', 'scale=iw-2:ih-2,eq=brightness=0.02:contrast=1.02',
            '-c:v', 'libx264', '-crf', '23',
            '-c:a', 'aac', '-b:a', '128k',
            '-preset', 'fast',
            '-map_metadata', '-1',
            str(output_path)
        ]
        
        # Convert all to strings
        cmd = [str(arg) for arg in cmd]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        
        if result.returncode != 0:
            raise Exception(f"Simple processing failed: {result.stderr}")
        
        return True
        
    except Exception as e:
        logger.error(f"Simple fallback failed: {str(e)}")
        raise
