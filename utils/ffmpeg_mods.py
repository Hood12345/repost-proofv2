import os
import random
import subprocess
import logging
import json
import time

logger = logging.getLogger(__name__)

def has_rubberband():
    """Check if FFmpeg has rubberband filter available"""
    try:
        result = subprocess.run(
            ['ffmpeg', '-filters'],
            capture_output=True,
            text=True,
            timeout=10
        )
        return 'rubberband' in result.stdout
    except Exception as e:
        logger.warning(f"Could not check for rubberband: {e}")
        return False

def get_video_info(input_path):
    """Get basic video information safely"""
    try:
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_format', '-show_streams', input_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            logger.warning(f"ffprobe failed: {result.stderr}")
            return None
            
        data = json.loads(result.stdout)
        
        # Find video stream
        video_stream = None
        for stream in data.get('streams', []):
            if stream.get('codec_type') == 'video':
                video_stream = stream
                break
        
        if not video_stream:
            return None
            
        return {
            'duration': float(data.get('format', {}).get('duration', 0)),
            'width': int(video_stream.get('width', 0)),
            'height': int(video_stream.get('height', 0)),
            'fps': eval(video_stream.get('r_frame_rate', '25/1')),
            'codec': video_stream.get('codec_name', 'unknown')
        }
    except Exception as e:
        logger.warning(f"Could not get video info: {e}")
        return None

def build_ffmpeg_command(input_path, output_path):
    """Build FFmpeg command with MAXIMUM modifications but stable execution"""
    
    # Get video info for optimization
    video_info = get_video_info(input_path)
    
    # Use conservative settings if we can't get video info
    if video_info is None:
        logger.warning("Using fallback settings - no video info available")
        video_info = {'duration': 60, 'width': 1920, 'height': 1080, 'fps': 30}
    
    # For very long videos, use simpler processing to prevent crashes
    is_long_video = video_info['duration'] > 180  # 3 minutes
    if is_long_video:
        logger.info(f"Long video detected ({video_info['duration']}s) - using optimized settings")
    
    # ENCODING PARAMETERS (varied but stable)
    crf = random.choice([18, 19, 20, 21, 22, 23, 24, 25])  # Wide quality range
    gop = random.choice([12, 24, 48, 60]) if not is_long_video else random.choice([24, 48])
    preset = random.choice(['fast', 'medium', 'slow']) if not is_long_video else 'fast'
    profile = random.choice(['baseline', 'main', 'high'])
    
    # MAXIMUM VISUAL MODIFICATIONS (but stable)
    # Geometric transformations
    crop_pixels = random.randint(2, 6)  # Significant cropping
    pad_pixels = crop_pixels + random.randint(1, 3)
    rotation = round(random.uniform(-1.5, 1.5), 2)  # ±1.5 degrees
    
    # Color adjustments - MAXIMUM but stable ranges
    brightness = round(random.uniform(-0.08, 0.08), 3)     # ±8%
    contrast = round(random.uniform(0.92, 1.08), 3)        # ±8%
    saturation = round(random.uniform(0.85, 1.15), 3)      # ±15%
    gamma = round(random.uniform(0.85, 1.15), 3)           # ±15%
    gamma_r = round(random.uniform(0.95, 1.05), 3)         # Red gamma
    gamma_g = round(random.uniform(0.95, 1.05), 3)         # Green gamma
    gamma_b = round(random.uniform(0.95, 1.05), 3)         # Blue gamma
    hue_shift = round(random.uniform(-8, 8), 1)             # ±8 degrees
    
    # Advanced color grading
    shadows = round(random.uniform(0.9, 1.1), 3)
    midtones = round(random.uniform(0.95, 1.05), 3)
    highlights = round(random.uniform(0.9, 1.1), 3)
    
    # Noise and texture
    noise_level = random.randint(8, 15) if not is_long_video else random.randint(5, 10)
    sharpen_amount = round(random.uniform(0.1, 0.3), 2)
    blur_amount = round(random.uniform(0.1, 0.5), 2)
    
    # Frame rate variations
    fps_options = [23.976, 24, 25, 29.97, 30]
    target_fps = random.choice(fps_options)
    
    # MAXIMUM AUDIO MODIFICATIONS
    tempo_variation = round(random.uniform(0.97, 1.03), 3)  # ±3%
    pitch_shift = round(random.uniform(0.995, 1.005), 4)    # Subtle pitch
    volume_change = round(random.uniform(0.9, 1.1), 3)      # ±10%
    
    # EQ settings for multiple bands
    eq_200 = round(random.uniform(-1, 1), 1)    # Bass
    eq_1000 = round(random.uniform(-0.5, 0.5), 1)  # Mid
    eq_5000 = round(random.uniform(-1, 1), 1)   # High mid
    eq_10000 = round(random.uniform(-0.5, 0.5), 1) # Treble
    
    # Build COMPREHENSIVE audio filter chain
    audio_filters = []
    
    # Tempo and pitch (try rubberband first)
    if has_rubberband() and not is_long_video:
        audio_filters.append(f"rubberband=tempo={tempo_variation}:pitch={pitch_shift}")
        pitch_preserved = True
    else:
        audio_filters.append(f"atempo={tempo_variation}")
        if abs(pitch_shift - 1.0) > 0.001:  # Only add if significant
            audio_filters.append(f"asetrate=44100*{pitch_shift},aresample=44100")
        pitch_preserved = False
    
    # Multi-band EQ
    audio_filters.extend([
        f"equalizer=f=200:t=q:w=1:g={eq_200}",
        f"equalizer=f=1000:t=q:w=1:g={eq_1000}",
        f"equalizer=f=5000:t=q:w=1:g={eq_5000}",
        f"equalizer=f=10000:t=q:w=1:g={eq_10000}"
    ])
    
    # Volume and effects
    audio_filters.extend([
        f"volume={volume_change}",
        f"dcshift={round(random.uniform(-0.01, 0.01), 3)}",
        "highpass=f=20",  # Remove very low frequencies
        "lowpass=f=20000"  # Remove very high frequencies
    ])
    
    # Build MAXIMUM video filter chain
    video_filters = []
    
    # Geometric transformations (applied in order)
    video_filters.extend([
        f"crop=iw-{crop_pixels*2}:ih-{crop_pixels*2}:{crop_pixels}:{crop_pixels}",
        f"pad=iw+{pad_pixels*2}:ih+{pad_pixels*2}:{pad_pixels}:{pad_pixels}:color=black",
        f"rotate={rotation}*PI/180:fillcolor=black:bilinear=0"
    ])
    
    # Color corrections (major modifications)
    video_filters.extend([
        f"eq=brightness={brightness}:contrast={contrast}:saturation={saturation}:gamma={gamma}:gamma_r={gamma_r}:gamma_g={gamma_g}:gamma_b={gamma_b}",
        f"hue=h={hue_shift}:s={round(random.uniform(0.9, 1.1), 2)}",
        f"curves=r='0/0 0.5/{midtones} 1/1':g='0/0 0.5/{midtones} 1/1':b='0/0 0.5/{midtones} 1/1'"
    ])
    
    # Texture and noise modifications
    if not is_long_video:
        video_filters.extend([
            f"noise=alls={noise_level}:allf=t+u",
            f"unsharp=5:5:{sharpen_amount}:5:5:0.0",
            f"boxblur={blur_amount}:1"
        ])
    else:
        # Simpler for long videos
        video_filters.append(f"noise=alls={noise_level//2}:allf=t")
    
    # Frame rate conversion
    if abs(target_fps - video_info.get('fps', 30)) > 0.1:
        video_filters.append(f"fps={target_fps}")
    
    # Multiple invisible watermarks (hash-changing)
    timestamp = int(time.time())
    video_filters.extend([
        f"drawbox=x=0:y=0:w=1:h=1:color=white@0.004:t=fill",  # TL
        f"drawbox=x=iw-1:y=0:w=1:h=1:color=red@0.003:t=fill",  # TR
        f"drawbox=x=0:y=ih-1:w=1:h=1:color=blue@0.005:t=fill", # BL
        f"drawbox=x=iw-1:y=ih-1:w=1:h=1:color=green@0.002:t=fill", # BR
        f"drawbox=x=iw/2:y=ih/2:w=1:h=1:color=yellow@0.001:t=fill", # Center
    ])
    
    # Invisible text watermark (changes hash significantly)
    video_filters.append(f"drawtext=text='{timestamp}':x=10:y=10:fontsize=1:fontcolor=white@0.001")
    
    # Join all filters
    vfilter = ",".join(video_filters)
    afilter = ",".join(audio_filters)
    
    # Build final command with MAXIMUM modifications but stability focus
    cmd = [
        "ffmpeg",
        "-y",  # Overwrite output
        "-i", input_path,
        
        # Input options for stability
        "-avoid_negative_ts", "make_zero",
        "-fflags", "+genpts",
        "-thread_queue_size", "512",
        
        # Video encoding with variations
        "-c:v", "libx264",
        "-preset", preset,
        "-profile:v", profile,
        "-crf", str(crf),
        "-g", str(gop),
        "-keyint_min", str(gop // 4),
        "-sc_threshold", "0",
        "-bf", str(random.choice([0, 1, 2, 3])),  # B-frames
        "-refs", str(random.choice([1, 2, 3, 4])),  # Reference frames
        
        # Video filters (MAXIMUM modifications)
        "-vf", vfilter,
        
        # Audio encoding variations
        "-c:a", "aac",
        "-b:a", random.choice(["96k", "128k", "160k", "192k"]),
        "-ar", random.choice([44100, 48000]),
        "-ac", "2",
        
        # Audio filters (MAXIMUM modifications)
        "-af", afilter,
        
        # Format options with variations
        "-f", "mp4",
        "-movflags", "+faststart+write_colr",
        
        # Color space variations (major hash changes)
        "-colorspace", random.choice(["bt709", "bt470bg", "smpte170m"]),
        "-color_primaries", random.choice(["bt709", "bt470bg", "smpte170m"]),
        "-color_trc", random.choice(["bt709", "gamma22", "smpte170m"]),
        
        # Pixel format variations
        "-pix_fmt", random.choice(["yuv420p", "yuv422p", "yuv444p"]),
        
        # Remove ALL metadata (complete anonymization)
        "-map_metadata", "-1",
        "-map_chapters", "-1",
        "-fflags", "+bitexact",
        
        # Add custom metadata (randomized)
        "-metadata", f"title=Processed_{timestamp}",
        "-metadata", f"comment=Hash_{random.randint(10000, 99999)}",
        "-metadata", f"description=Modified_{random.choice(['A', 'B', 'C', 'D'])}",
        "-metadata", f"encoder=Custom_{random.choice(['X', 'Y', 'Z'])}",
        
        # Stability options
        "-max_muxing_queue_size", "1024",
        "-avoid_negative_ts", "make_zero",
        "-err_detect", "ignore_err",  # Ignore minor errors
        
        output_path
    ]
    
    # Log comprehensive info
    logger.info(f"MAXIMUM FFmpeg command built:")
    logger.info(f"  Video: CRF={crf}, GOP={gop}, Preset={preset}, Profile={profile}")
    logger.info(f"  Filters: {len(video_filters)} video filters, {len(audio_filters)} audio filters")
    logger.info(f"  Color: Brightness={brightness}, Contrast={contrast}, Saturation={saturation}")
    logger.info(f"  Audio: Tempo={tempo_variation}, Volume={volume_change}, Pitch_preserved={pitch_preserved}")
    logger.info(f"  Geometric: Crop={crop_pixels}px, Pad={pad_pixels}px, Rotation={rotation}°")
    
    return cmd, pitch_preserved

def build_simple_command(input_path, output_path):
    """Fallback simple command for problematic videos"""
    logger.info("Using simple fallback command")
    
    # Minimal modifications for maximum stability
    brightness = round(random.uniform(-0.01, 0.01), 3)
    contrast = round(random.uniform(0.99, 1.01), 3)
    tempo = round(random.uniform(0.99, 1.01), 3)
    
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-vf", f"eq=brightness={brightness}:contrast={contrast},noise=alls=3:allf=t",
        "-c:a", "aac", "-b:a", "128k",
        "-af", f"atempo={tempo}",
        "-map_metadata", "-1",
        "-movflags", "+faststart",
        output_path
    ]
    
    return cmd, False
