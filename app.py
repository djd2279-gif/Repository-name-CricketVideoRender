# =====================================================================
# VIDEO GENERATOR - RENDER VERSION (FIXED)
# Changes:
#   1. flask-cors add kiya - Android app se requests allow hongi
#   2. nest_asyncio hataya - Render par zaroorat nahi, error deta tha
#   3. asyncio loop handling fix ki - Render par event loop crash hota tha
#   4. moviepy import top-level kiya - Render par import error fix
# =====================================================================

import os
import re
import uuid
import time
import threading
import requests
import asyncio
from flask import Flask, request, jsonify, send_from_directory, abort
from flask_cors import CORS  # FIX 1: CORS add kiya

app = Flask(__name__)
CORS(app)  # FIX 1: Yeh line Android app ki requests allow karti hai

VIDEO_FOLDER = "local_videos"
if not os.path.exists(VIDEO_FOLDER):
    os.makedirs(VIDEO_FOLDER)

# =====================================================================
# KEYS
# =====================================================================
PEXELS_API_KEY = "oiBu8RSuO10ymnkgC8WnScrv7uDiMvsu483FeN19maRKAaZ3FN8TfBM8"
BASE_URL = os.getenv(
    "BASE_URL",
    "https://repository-name-cricketvideorender.onrender.com"
)
VIDEO_TTL_SECONDS = 3600

# =====================================================================
# STOPWORDS
# =====================================================================
STOPWORDS = {
    "the", "and", "for", "are", "but", "not", "you", "all", "can",
    "her", "was", "one", "our", "out", "day", "get", "has", "him",
    "his", "how", "man", "new", "now", "old", "see", "two", "way",
    "who", "boy", "did", "its", "let", "put", "say", "she", "too",
    "use", "that", "this", "with", "they", "have", "from", "been",
    "were", "said", "each", "will", "what", "your", "when", "more",
    "very", "just", "also", "into", "than", "then", "some", "them",
    "these", "would", "make", "like", "time", "look", "come", "could",
    "mein", "hai", "karo", "aur", "nahi", "yeh", "woh", "iske", "unke",
}

# =====================================================================
# OLD VIDEOS CLEANUP
# =====================================================================
def cleanup_old_videos():
    while True:
        try:
            now = time.time()
            for fname in os.listdir(VIDEO_FOLDER):
                fpath = os.path.join(VIDEO_FOLDER, fname)
                if os.path.isfile(fpath):
                    if now - os.path.getmtime(fpath) > VIDEO_TTL_SECONDS:
                        os.remove(fpath)
                        print(f"[CLEANUP] Deleted: {fname}")
        except Exception as e:
            print(f"[CLEANUP ERROR] {e}")
        time.sleep(300)

threading.Thread(target=cleanup_old_videos, daemon=True).start()

# =====================================================================
# SECURE FILENAME CHECK
# =====================================================================
def is_safe_filename(filename):
    return bool(re.match(r'^video_[a-f0-9]{8}\.mp4$', filename))

# =====================================================================
# FUNCTION 1: PEXELS SE CLIPS DOWNLOAD
# =====================================================================
def download_automatic_clips(script_text, api_key, required_count=6):
    print("\n[1/4] Videos dhoondh rahe hain...")

    if not api_key:
        raise ValueError("PEXELS_API_KEY set nahi hai!")

    clips_list = []
    words = script_text.lower().split()
    keywords = []

    for w in words:
        cleaned = w.strip(",.!?\"'()[]")
        if len(cleaned) > 4 and cleaned not in STOPWORDS and cleaned.isalpha():
            keywords.append(cleaned)
        if len(keywords) >= 6:
            break

    if not keywords:
        keywords = ["nature", "technology", "city", "sports", "music"]

    headers = {"Authorization": api_key}

    for word in keywords:
        if len(clips_list) >= required_count:
            break
        try:
            url = f"https://api.pexels.com/videos/search?query={word}&per_page=3&orientation=portrait"
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code != 200:
                continue

            data = response.json()
            for video in data.get("videos", []):
                video_files = video.get("video_files", [])
                mp4_files = [f for f in video_files if f.get("file_type") == "video/mp4"]
                mp4_files.sort(key=lambda x: x.get("width", 9999))

                if mp4_files:
                    video_url = mp4_files[0].get("link")
                    if not video_url:
                        continue

                    local_path = os.path.join(VIDEO_FOLDER, f"temp_{uuid.uuid4().hex[:6]}.mp4")
                    print(f"-> Downloading: '{word}'")

                    with requests.get(video_url, stream=True, timeout=30) as r:
                        r.raise_for_status()
                        with open(local_path, "wb") as f:
                            for chunk in r.iter_content(chunk_size=1024 * 512):
                                if chunk:
                                    f.write(chunk)

                    clips_list.append(local_path)
                    if len(clips_list) >= required_count:
                        break

        except requests.Timeout:
            print(f"-> '{word}': Timeout, skip")
            continue
        except Exception as e:
            print(f"-> '{word}' error: {e}")
            continue

    return clips_list

# =====================================================================
# FUNCTION 2: VOICEOVER
# FIX 2: nest_asyncio hataya, asyncio loop Render ke liye sahi kiya
# =====================================================================
def generate_voiceover(text, language, output_path):
    print(f"\n[2/4] Voiceover bana rahe hain ({language})...")

    from gtts import gTTS

    lang_code = "hi" if language.lower() == "hindi" else "en"

    try:
        tts = gTTS(text=text, lang=lang_code, slow=False)
        tts.save(output_path)
        print(f"-> Voiceover ready ({lang_code})")
    except Exception as e:
        raise Exception(f"Voiceover failed: {e}")

# =====================================================================
# FUNCTION 3: FINAL VIDEO
# FIX 3: moviepy import function ke andar rakha - Render par safer hai
# =====================================================================
def create_final_video(audio_path, input_clips_list, aspect_ratio, output_video_path):
    # FIX 3: Import andar isliye hai taaki server start hone mein delay na aaye
    from moviepy.editor import AudioFileClip, VideoFileClip, concatenate_videoclips

    print("\n[3/4] Video edit ho rahi hai...")

    if not input_clips_list:
        raise Exception("Koi clips download nahi hui!")

    ratio_map = {
        "9:16": (1080, 1920),
        "16:9": (1920, 1080),
        "1:1":  (1080, 1080),
        "4:5":  (1080, 1350),
    }
    target_w, target_h = ratio_map.get(aspect_ratio, (1080, 1920))
    target_ar = target_w / target_h

    audio = AudioFileClip(audio_path)
    audio_duration = audio.duration
    clip_duration = audio_duration / len(input_clips_list)
    processed_clips = []

    try:
        for c_path in input_clips_list:
            try:
                clip = VideoFileClip(c_path)
                clip_ar = clip.w / clip.h

                if clip_ar > target_ar:
                    new_w = int(clip.h * target_ar)
                    x_center = clip.w / 2
                    clip = clip.crop(x1=x_center - new_w/2, x2=x_center + new_w/2)
                elif clip_ar < target_ar:
                    new_h = int(clip.w / target_ar)
                    y_center = clip.h / 2
                    clip = clip.crop(y1=y_center - new_h/2, y2=y_center + new_h/2)

                clip = clip.resize((target_w, target_h))
                clip = clip.subclip(0, min(clip_duration, clip.duration))
                clip = clip.set_fps(24)
                clip = clip.without_audio()
                processed_clips.append(clip)

            except Exception as e:
                print(f"-> Clip error: {e}")
                continue

        if not processed_clips:
            raise Exception("Koi bhi clip process nahi hui!")

        final_video = concatenate_videoclips(processed_clips, method="compose")
        final_video = final_video.set_audio(audio)

        print("-> Rendering shuru... (1-2 min lagenge)")
        final_video.write_videofile(
            output_video_path,
            fps=24,
            codec="libx264",
            audio_codec="aac",
            verbose=False,
            logger=None
        )
        print("[4/4] Video ban gayi!")

    finally:
        audio.close()
        for c in processed_clips:
            try:
                c.close()
            except:
                pass

# =====================================================================
# FLASK ROUTES
# =====================================================================
@app.route('/generate-video', methods=['POST'])
def handle_mobile_request():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "JSON data nahi mila!"}), 400

    script_text = data.get('script', '').strip()
    ratio = data.get('ratio', '9:16')
    language = data.get('language', 'hindi')

    if not script_text:
        return jsonify({"status": "error", "message": "Script khali hai!"}), 400

    if ratio not in {"9:16", "16:9", "1:1", "4:5"}:
        ratio = "9:16"

    print(f"\n[REQUEST] '{script_text[:40]}...' | {ratio} | {language}")

    video_id = uuid.uuid4().hex[:8]
    temp_audio = os.path.join(VIDEO_FOLDER, f"temp_audio_{video_id}.mp3")
    output_video_name = f"video_{video_id}.mp4"
    final_video_path = os.path.join(VIDEO_FOLDER, output_video_name)

    clips = []
    try:
        clips = download_automatic_clips(script_text, PEXELS_API_KEY, required_count=6)
        generate_voiceover(script_text, language, temp_audio)
        create_final_video(temp_audio, clips, ratio, final_video_path)

        video_url = f"{BASE_URL}/videos/{output_video_name}"
        print(f"-> Ready: {video_url}")
        return jsonify({"status": "success", "video_url": video_url})

    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

    finally:
        for c in clips:
            if c and os.path.exists(c):
                try:
                    os.remove(c)
                except:
                    pass
        if os.path.exists(temp_audio):
            try:
                os.remove(temp_audio)
            except:
                pass

@app.route('/videos/<filename>')
def serve_video(filename):
    if not is_safe_filename(filename):
        abort(400)
    filepath = os.path.join(VIDEO_FOLDER, filename)
    if not os.path.isfile(filepath):
        abort(404)
    return send_from_directory(VIDEO_FOLDER, filename)

@app.route('/health')
def health_check():
    return jsonify({
        "status": "ok",
        "pexels_key_set": bool(PEXELS_API_KEY),
        "base_url": BASE_URL,
    })

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
