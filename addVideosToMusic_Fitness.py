"""
Video Concatenation with Music - Clean Code Edition
Combines video clips, adds background music, and applies fade effects.
"""
import subprocess
import threading
from pathlib import Path
from typing import Optional

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

# =============================================================================
# CONFIGURATION
# =============================================================================
VIDEO_DIR = Path(r"C:\Users\Ryzen 5500\Desktop\Tryhard songs\Training")
MUSIC_DIR = VIDEO_DIR / "Music"
OUTPUT_PATH = VIDEO_DIR / "final_video_fast.mp4"
TRANSCODED_DIR = VIDEO_DIR / "transcoded"

# Settings
VIDEO_EXTENSIONS = (".mp4", ".mov", ".mkv", ".avi", ".m4a", ".3gp", ".3g2")
AUDIO_EXTENSIONS = (".mp3", ".wav", ".m4a", ".aac")
FADE_IN_SECONDS = 0.5
FADE_OUT_SECONDS = 1.0

TRANSCODED_DIR.mkdir(exist_ok=True)


# =============================================================================
# COMMAND EXECUTION
# =============================================================================
def run_ffmpeg(commands: list[str], total_duration: float = 0) -> None:
    """Execute FFmpeg command with optional tqdm progress bar."""
    print(f"[RUN] {' '.join(commands[:4])}...")
    
    use_tqdm_bar = tqdm is not None and total_duration > 0
    progress = None
    
    if use_tqdm_bar:
        progress = tqdm(total=total_duration, unit="s", desc="Encoding", unit_scale=True)
    
    try:
        process = subprocess.Popen(
            commands,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            universal_newlines=True
        )
        
        while True:
            retcode = process.poll()
            if retcode is not None:
                break
            
            try:
                line = process.stderr.readline()
                if line and 'time=' in line:
                    time_str = line.split('time=')[1].split()[0]
                    parts = time_str.split(':')
                    if len(parts) == 3:
                        current_time = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                        if progress:
                            progress.n = int(current_time)
                            progress.refresh()
            except:
                pass
        
        process.wait()
        
    except Exception as error:
        raise RuntimeError(f"Command failed: {error}")
    finally:
        if progress:
            progress.close()
    
    if process.returncode != 0:
        try:
            _, stderr = process.communicate()
            if stderr:
                print(stderr[:500])
        except:
            pass
        raise RuntimeError("FFmpeg command failed")


# =============================================================================
# MEDIA ANALYSIS
# =============================================================================
def get_media_info(file_path: Path) -> dict:
    """Retrieve media file properties using ffprobe."""
    command = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(file_path)
    ]
    
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    except Exception:
        return {}
    
    if result.returncode != 0 or not result.stdout:
        return {}
    
    try:
        import json
        data = json.loads(result.stdout)
    except Exception:
        return {}
    
    info = {"duration": 0.0}
    for stream in data.get("streams", []):
        codec = stream.get("codec_type")
        if codec == "video":
            info.update({
                "video_codec": stream.get("codec_name"),
                "width": stream.get("width"),
                "height": stream.get("height"),
                "fps": eval(stream.get("r_frame_rate", "0/1"))
            })
        elif codec == "audio":
            info["audio_codec"] = stream.get("codec_name")
    
    try:
        info["duration"] = float(data.get("format", {}).get("duration", 0))
    except:
        pass
    
    return info


def get_duration(media_file: Path) -> float:
    """Get the duration of a media file in seconds."""
    return get_media_info(media_file).get("duration", 0.0)


# =============================================================================
# VIDEO PROCESSING
# =============================================================================
def find_majority_frame_rate(video_files: list[Path]) -> tuple[bool, float]:
    """Determine if all videos share the same frame rate and find the majority."""
    if len(video_files) < 2:
        return True, get_media_info(video_files[0]).get("fps", 0) if video_files else 0
    
    frame_rate_counts = {}
    for video in video_files:
        fps = get_media_info(video).get("fps", 0)
        frame_rate_counts[fps] = frame_rate_counts.get(fps, 0) + 1
    
    if not frame_rate_counts:
        return True, 0
    
    majority = max(frame_rate_counts, key=frame_rate_counts.get)
    is_compatible = len(frame_rate_counts) == 1
    
    if not is_compatible:
        print(f"[INFO] Frame rates: {frame_rate_counts}, Using: {majority}")
    
    return is_compatible, majority


def transcode_video(input_file: Path, target_fps: Optional[float] = None) -> Path:
    """Convert video to H.264 format with optional frame rate adjustment."""
    fps_label = f"_fps{target_fps}" if target_fps else ""
    output_file = TRANSCODED_DIR / f"{input_file.stem}_h264{fps_label}.mp4"
    
    if output_file.exists():
        print(f"[SKIP] {input_file.name} already transcoded")
        return output_file
    
    command = ["ffmpeg", "-y", "-i", str(input_file), "-c:v", "h264_nvenc"]
    
    if target_fps:
        command.extend(["-r", str(target_fps)])
    
    command.extend(["-c:a", "aac", "-b:a", "128k", str(output_file)])
    
    fps_message = f" @ {target_fps}fps" if target_fps else ""
    print(f"[INFO] Converting {input_file.name} to H.264{fps_message}...")
    run_ffmpeg(command)
    return output_file


def create_concatenation_list(video_files: list[Path]) -> Path:
    """Generate a text file listing videos for FFmpeg concatenation."""
    list_file = TRANSCODED_DIR / "concat_list.txt"
    with open(list_file, "w", encoding="utf-8") as file:
        for video in video_files:
            file.write(f"file '{video.as_posix()}'\n")
    return list_file


def calculate_total_duration(concatenation_list: Path) -> float:
    """Calculate the combined duration of all videos in the concatenation list."""
    total = 0.0
    with open(concatenation_list, "r", encoding="utf-8") as file:
        for line in file:
            if line.startswith("file '"):
                path = line.replace("file '", "").replace("'", "").strip()
                total += get_duration(Path(path))
    return total


# =============================================================================
# VIDEO MERGING
# =============================================================================
def merge_videos_with_music(
    concatenation_list: Path,
    music_file: Optional[Path],
    output_file: Path,
    use_hardware_encoding: bool = False
) -> None:
    """Merge video clips with music, applying trim and fade effects."""
    has_music = music_file and music_file.exists()
    music_duration = get_duration(music_file) if has_music else 0.0
    
    command = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concatenation_list)]
    
    if has_music and music_duration > 0:
        command.extend(["-i", str(music_file)])
        
        fade_out_start = max(0, music_duration - FADE_OUT_SECONDS)
        
        filter_chain = (
            f"[0:v]trim=duration={music_duration},"
            f"fade=t=in:st=0:d={FADE_IN_SECONDS},"
            f"fade=t=out:st={fade_out_start}:d={FADE_OUT_SECONDS}[v]"
        )
        
        if use_hardware_encoding:
            command.extend([
                "-filter_complex", filter_chain,
                "-map", "[v]", "-map", "1:a",
                "-t", str(music_duration),
                "-c:v", "h264_nvenc", "-c:a", "aac", "-preset", "p5"
            ])
        else:
            command.extend([
                "-filter_complex", filter_chain,
                "-map", "[v]", "-map", "1:a",
                "-t", str(music_duration),
                "-c:v", "copy", "-c:a", "aac"
            ])
        
        print(f"[INFO] Processing: {music_duration:.1f}s with fade in/out")
    else:
        if has_music:
            command.extend(["-i", str(music_file), "-map", "0:v", "-map", "1:a", "-shortest"])
        
        if use_hardware_encoding:
            command.extend(["-c:v", "h264_nvenc", "-c:a", "aac", "-preset", "p5"])
        else:
            command.extend(["-c:v", "copy", "-c:a", "aac"])
    
    command.append(str(output_file))
    
    mode = "NVENC" if use_hardware_encoding else "stream copy"
    print(f"[INFO] Merging videos ({mode}) -> {output_file.name}")
    run_ffmpeg(command, total_duration=music_duration if has_music else 0)
    print(f"[DONE] Saved: {output_file}")


# =============================================================================
# MAIN EXECUTION
# =============================================================================
def main() -> None:
    """Main workflow for video concatenation."""
    # Discover videos
    videos = [
        f for f in VIDEO_DIR.iterdir()
        if f.suffix.lower() in VIDEO_EXTENSIONS
        and f.name not in ("music.mp3", "final_video_fast.mp4", "final_video.mp4")
    ]
    videos = sorted(videos)
    
    if not videos:
        print("[ERROR] No videos found in directory")
        return
    
    print(f"[INFO] Found {len(videos)} videos")
    
    # Discover music
    music_files = [f for f in MUSIC_DIR.iterdir() if f.suffix.lower() in AUDIO_EXTENSIONS]
    if not music_files:
        print("[ERROR] No music files found")
        return
    
    music_file = music_files[0]
    print(f"[INFO] Music: {music_file.name}")
    
    # Check frame rate compatibility
    is_compatible, majority_fps = find_majority_frame_rate(videos)
    
    if is_compatible:
        print("[INFO] Using fast stream copy mode")
        concat_list = create_concatenation_list(videos)
        try:
            merge_videos_with_music(concat_list, music_file, OUTPUT_PATH, use_hardware_encoding=False)
        except RuntimeError:
            print("[WARNING] Stream copy failed, falling back to transcoding")
            is_compatible = False
    
    if not is_compatible:
        print(f"[INFO] Transcoding with frame rate {majority_fps}")
        transcoded = []
        for video in videos:
            current_fps = get_media_info(video).get("fps", 0)
            target = majority_fps if current_fps != majority_fps else None
            try:
                transcoded.append(transcode_video(video, target))
            except RuntimeError:
                print(f"[ERROR] Failed: {video.name}")
        
        if not transcoded:
            print("[ERROR] No videos available to merge")
            return
        
        concat_list = create_concatenation_list(transcoded)
        merge_videos_with_music(concat_list, music_file, OUTPUT_PATH, use_hardware_encoding=True)


if __name__ == "__main__":
    main()
