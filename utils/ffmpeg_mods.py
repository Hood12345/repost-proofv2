import os
import random
import subprocess
import logging
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
        return "rubberband" in result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        logger.warning(f"Could not check for rubberband filter: {e}")
        return False

def get_video_info(input_path):
    """Get basic video information"""
    try:
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json', 
            '-show_format', '-show_streams', input_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            import json
            info = json.loads(result.stdout)
            return info
        else:
            logger.warning(f"Could not get video info: {result.stderr}")
            return None
    except Exception as e:
        logger.warning(f"Error getting video info: {e}")
        return None

def build_ffmpeg_command(input_path, output_path):
    """Build FFmpeg command with maximum video modifications"""
    
    # Get video info for optimization
    video_info = get_video_info(input_path)
    
    # Randomized encoding parameters (wider range)
    crf = random.choice([18, 19, 20, 21, 22, 23, 24, 25])
    gop = random.choice([12, 24, 30, 48, 60, 72])
    
    # Maximum visual modifications (more aggressive)
    brightness = round(random.uniform(0.02, 0.08), 3)
    contrast = round(random.uniform(1.02, 1.08), 3)
    saturation = round(random.uniform(1.02, 1.08), 3)
    gamma = round(random.uniform(0.95, 1.05), 3)
    hue_shift = round(random.uniform(-5, 5), 2)
    
    # Higher noise levels for more modification
    noise_lvl = random.randint(8, 15)
    
    # More aggressive audio modifications
    tempo_variation = round(random.uniform(0.98, 1.02), 4)
    pitch_shift = round(random.uniform(0.995, 1.005), 5)
    
    # Additional randomization parameters
    sharpen_amount = round(random.uniform(0.1, 0.3), 2)
    blur_amount = round(random.uniform(0.1, 0.5), 2)
    crop_pixels = random.randint(2, 8)
    rotation_angle = round(random.uniform(-0.5, 0.5), 3)
    
    # Build comprehensive audio filter chain
    audio_filters = []
    
    # Tempo and pitch modifications
    if has_rubberband():
        audio_filters.append(f"rubberband=tempo={tempo_variation}:pitch={pitch_shift}")
        pitch_preserved = True
        logger.info("Using rubberband for audio processing")
    else:
        # Multiple tempo/pitch changes for more modification
        audio_filters.extend([
            f"atempo={tempo_variation}",
            f"asetrate=44100*{pitch_shift},aresample=44100"
        ])
        pitch_preserved = False
        logger.info("Using basic audio processing with pitch shift")
    
    # Multiple EQ bands for maximum audio modification
    eq_bands = [
        f"equalizer=f=100:t=q:w=1:g={random.uniform(-2, 2):.1f}",
        f"equalizer=f=1000:t=q:w=1:g={random.uniform(-1, 1):.1f}",
        f"equalizer=f=5000:t=q:w=1:g={random.uniform(-1, 1):.1f}",
        f"equalizer=f=10000:t=q:w=1:g={random.uniform(-0.5, 0.5):.1f}"
    ]
    audio_filters.extend(eq_bands)
    
    # Additional audio effects
    audio_filters.extend([
        f"dcshift={random.uniform(0.01, 0.03):.3f}",
        f"volume={random.uniform(0.98, 1.02):.3f}",
        "aphaser=in_gain=0.4:out_gain=0.74:delay=3:decay=0.4:speed=0.5:type=t",
        "tremolo=f=5:d=0.1"
    ])
    
    afilter = ",".join(audio_filters)
    
    # Maximum video filter chain with extensive modifications
    video_filters = []
    
    # Geometric transformations (crop, pad, rotate)
    video_filters.extend([
        f"crop=iw-{crop_pixels}:ih-{crop_pixels}:{crop_pixels//2}:{crop_pixels//2}",
        f"pad=iw+{crop_pixels}:ih+{crop_pixels}:{crop_pixels//2}:{crop_pixels//2}:black",
        f"rotate={rotation_angle}*PI/180:fillcolor=black@0.5"
    ])
    
    # Multiple color/brightness adjustments
    video_filters.extend([
        f"eq=brightness={brightness}:contrast={contrast}:saturation={saturation}:gamma={gamma}",
        f"hue=h={hue_shift}:s={random.uniform(0.98, 1.02):.3f}",
        f"curves=vintage"  # Apply vintage color curve
    ])
    
    # Noise and texture modifications
    video_filters.extend([
        f"noise=alls={noise_lvl}:allf=t+u+p",
        f"unsharp=5:5:{sharpen_amount}:5:5:0.0",  # Sharpening
        f"boxblur={blur_amount}:1"  # Slight blur
    ])
    
    # Multiple invisible watermarks and modifications
    watermark_effects = [
        "drawbox=x=0:y=0:w=1:h=1:color=white@0.01:t=fill",
        "drawbox=x=iw-1:y=0:w=1:h=1:color=black@0.01:t=fill",
        "drawbox=x=0:y=ih-1:w=1:h=1:color=red@0.005:t=fill",
        f"drawtext=text='':fontsize=1:fontcolor=white@0.001:x=10:y=10"
    ]
    video_filters.extend(watermark_effects)
    
    # Frame rate and timing modifications
    fps_variation = random.choice([23.976, 24, 25, 29.97, 30])
    video_filters.append(f"fps={fps_variation}")
    
    # Color space modifications
    video_filters.extend([
        "colorspace=bt709:iall=bt601-6-625:fast=1",
        f"colorbalance=rs={random.uniform(-0.1, 0.1):.3f}:gs={random.uniform(-0.1, 0.1):.3f}:bs={random.uniform(-0.1, 0.1):.3f}"
    ])
    
    vfilter = ",".join(video_filters)
    
    # Build maximum modification FFmpeg command
    cmd = [
        "ffmpeg", 
        "-y",  # Overwrite output files
        "-i", input_path,
        
        # Video filters (maximum modifications)
        "-vf", vfilter,
        
        # Audio filters (maximum modifications)
        "-af", afilter,
        
        # Completely remove and randomize metadata
        "-map_metadata", "-1",
        "-metadata", f"title=processed_{random.randint(1000, 9999)}",
        "-metadata", f"comment=modified_{int(time.time())}",
        "-metadata", f"description=version_{random.randint(100, 999)}",
        "-metadata", f"encoder=custom_processor",
        
        # Video encoding settings (varied parameters)
        "-c:v", "libx264",
        "-crf", str(crf),
        "-preset", random.choice(["fast", "medium", "slow"]),
        "-g", str(gop),
        "-keyint_min", str(gop // 4),
        "-sc_threshold", str(random.randint(35, 45)),
        "-tune", random.choice(["film", "animation", "grain"]),
        "-profile:v", random.choice(["baseline", "main", "high"]),
        "-level", random.choice(["3.0", "3.1", "4.0"]),
        
        # Pixel format variations
        "-pix_fmt", random.choice(["yuv420p", "yuv422p", "yuv444p"]),
        
        # Audio encoding settings (varied)
        "-c:a", "aac",
        "-b:a", f"{random.choice([96, 128, 160, 192])}k",
        "-ar", str(random.choice([44100, 48000])),
        "-ac", "2",
        
        # Advanced output settings
        "-movflags", "+faststart+empty_moov",
        "-avoid_negative_ts", "make_zero",
        "-fflags", "+genpts",
        "-max_muxing_queue_size", "1024",
        
        # Timing modifications
        "-vsync", "cfr",
        "-async", "1",
        
        output_path
    ]
    
    logger.info(f"Built MAXIMUM modification FFmpeg command")
    logger.info(f"Video: CRF={crf}, GOP={gop}, FPS={fps_variation}")
    logger.info(f"Audio: {'rubberband' if pitch_preserved else 'multi-stage processing'}")
    logger.info(f"Modifications: {len(video_filters)} video filters, {len(audio_filters)} audio filters")
    
    return cmd, pitch_preserved

def optimize_for_platform(input_path, output_path, platform="instagram"):
    """Platform-specific optimizations"""
    
    # Get video info
    video_info = get_video_info(input_path)
    
    if platform.lower() == "instagram":
        # Instagram-specific optimizations
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            
            # Instagram prefers specific settings
            "-c:v", "libx264",
            "-crf", "23",
            "-preset", "fast",
            "-profile:v", "baseline",
            "-level", "3.0",
            "-pix_fmt", "yuv420p",
            
            # Audio settings
            "-c:a", "aac",
            "-b:a", "128k",
            "-ar", "44100",
            
            # Metadata removal
            "-map_metadata", "-1",
            
            output_path
        ]
        
        return cmd, True
    
    # Default to general optimization
    return build_ffmpeg_command(input_path, output_path)
