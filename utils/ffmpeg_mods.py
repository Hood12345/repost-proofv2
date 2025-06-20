import os
import random
import subprocess
import logging
import time
import json

logger = logging.getLogger(__name__)
_rubberband_cached = None

def has_rubberband():
    global _rubberband_cached
    if _rubberband_cached is not None:
        return _rubberband_cached
    try:
        result = subprocess.run(['ffmpeg', '-filters'], capture_output=True, text=True, timeout=10)
        _rubberband_cached = "rubberband" in result.stdout
        return _rubberband_cached
    except Exception as e:
        logger.warning(f"Rubberband check failed: {e}")
        _rubberband_cached = False
        return False

def get_video_info(input_path):
    try:
        cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', input_path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return json.loads(result.stdout) if result.returncode == 0 else None
    except Exception as e:
        logger.warning(f"Video info error: {e}")
        return None

def build_ffmpeg_command(input_path, output_path):
    info = get_video_info(input_path)
    crf = random.choice(range(18, 26))
    gop = random.choice([12, 24, 30, 48, 60])
    brightness = round(random.uniform(0.02, 0.08), 3)
    contrast = round(random.uniform(1.02, 1.08), 3)
    saturation = round(random.uniform(1.02, 1.08), 3)
    gamma = round(random.uniform(0.95, 1.05), 3)
    hue_shift = round(random.uniform(-5, 5), 2)
    noise_lvl = random.randint(8, 15)
    tempo = round(random.uniform(0.98, 1.02), 4)
    pitch = round(random.uniform(0.995, 1.005), 5)

    audio_filters = []
    if has_rubberband():
        audio_filters.append(f"rubberband=tempo={tempo}:pitch={pitch}")
        pitch_preserved = True
    else:
        audio_filters += [f"atempo={tempo}", f"asetrate=44100*{pitch},aresample=44100"]
        pitch_preserved = False

    audio_filters += [
        "aphaser=in_gain=0.4:out_gain=0.74:delay=3:decay=0.4:speed=0.5:type=t",
        "tremolo=f=5:d=0.1",
        f"volume={random.uniform(0.98, 1.02):.3f}"
    ]

    afilter = ",".join(audio_filters)
    video_filters = [
        f"eq=brightness={brightness}:contrast={contrast}:saturation={saturation}:gamma={gamma}",
        f"hue=h={hue_shift}",
        f"noise=alls={noise_lvl}:allf=t+u+p",
        f"fps={random.choice([23.976, 24, 25, 30])}"
    ]

    vfilter = ",".join(video_filters)

    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", vfilter,
        "-af", afilter,
        "-map_metadata", "-1",
        "-c:v", "libx264",
        "-crf", str(crf),
        "-preset", "medium",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        "-ac", "2",
        "-movflags", "+faststart",
        output_path
    ]

    return cmd, pitch_preserved
