#!/usr/bin/env python3
"""
yt-dlp Download Server
A lightweight Flask backend to fetch available formats and trigger downloads.
"""

import subprocess
import json
import re
import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder=".")
CORS(app)

DOWNLOAD_DIR = os.path.expanduser("~/Downloads")


def run_ytdlp(args: list[str]) -> tuple[str, str, int]:
    """Run a yt-dlp command and return (stdout, stderr, returncode)."""
    result = subprocess.run(
        ["yt-dlp"] + args,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result.stdout, result.stderr, result.returncode


def parse_formats(raw: str) -> dict:
    """
    Parse yt-dlp --dump-json output to extract audio and video formats.
    Falls back to --list-formats text parsing if JSON is unavailable.
    """
    try:
        info = json.loads(raw)
        formats = info.get("formats", [])

        audio_formats = []
        video_formats = []

        for f in formats:
            fmt_id = f.get("format_id", "")
            ext = f.get("ext", "")
            acodec = f.get("acodec", "none")
            vcodec = f.get("vcodec", "none")
            filesize = f.get("filesize") or f.get("filesize_approx")
            note = f.get("format_note", "")
            abr = f.get("abr")
            vbr = f.get("vbr")
            height = f.get("height")
            tbr = f.get("tbr")

            size_str = ""
            if filesize:
                mb = filesize / (1024 * 1024)
                size_str = f"{mb:.1f} MB" if mb >= 1 else f"{filesize/1024:.0f} KB"

            is_audio_only = vcodec == "none" and acodec != "none"
            is_video_only = acodec == "none" and vcodec != "none"
            is_combined = acodec != "none" and vcodec != "none"

            if is_audio_only:
                audio_formats.append({
                    "id": fmt_id,
                    "ext": ext,
                    "codec": acodec,
                    "bitrate": f"{abr:.0f}k" if abr else (f"{tbr:.0f}k" if tbr else ""),
                    "size": size_str,
                    "note": note,
                    "label": f"{ext.upper()} · {f'{abr:.0f}kbps' if abr else note or fmt_id}",
                })
            elif is_video_only or is_combined:
                res = f"{height}p" if height else note
                video_formats.append({
                    "id": fmt_id,
                    "ext": ext,
                    "vcodec": vcodec,
                    "acodec": acodec,
                    "resolution": res,
                    "bitrate": f"{vbr:.0f}k" if vbr else (f"{tbr:.0f}k" if tbr else ""),
                    "size": size_str,
                    "note": note,
                    "has_audio": is_combined,
                    "label": f"{ext.upper()} · {res or fmt_id}" + (" (video only)" if is_video_only else ""),
                })

        # Sort: audio by bitrate desc, video by resolution desc
        audio_formats.sort(key=lambda x: float(x["bitrate"].replace("k", "") or 0), reverse=True)
        video_formats.sort(key=lambda x: int(re.sub(r"\D", "", x["resolution"]) or 0), reverse=True)

        return {"audio": audio_formats, "video": video_formats}

    except (json.JSONDecodeError, KeyError):
        return {"audio": [], "video": [], "error": "Could not parse format info"}


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/api/formats", methods=["POST"])
def get_formats():
    data = request.get_json()
    url = (data or {}).get("url", "").strip()

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    stdout, stderr, code = run_ytdlp(["--dump-json", "--no-playlist", url])

    if code != 0:
        # Try to surface a readable error
        err_msg = stderr.strip().split("\n")[-1] if stderr else "Unknown error"
        return jsonify({"error": f"yt-dlp failed: {err_msg}"}), 422

    formats = parse_formats(stdout)

    # Also grab title/thumbnail from JSON
    try:
        info = json.loads(stdout)
        formats["title"] = info.get("title", "")
        formats["thumbnail"] = info.get("thumbnail", "")
        formats["duration"] = info.get("duration_string", "")
        formats["uploader"] = info.get("uploader", "")
    except Exception:
        pass

    return jsonify(formats)


@app.route("/api/download", methods=["POST"])
def download():
    data = request.get_json()
    url = (data or {}).get("url", "").strip()
    fmt_id = (data or {}).get("format_id", "").strip()
    media_type = (data or {}).get("type", "video")  # "audio" or "video"
    convert_audio = (data or {}).get("convert_mp3", False)

    if not url or not fmt_id:
        return jsonify({"error": "url and format_id are required"}), 400

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    output_template = os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s")

    args = ["-f", fmt_id, "-o", output_template, "--no-playlist"]

    if media_type == "audio" and convert_audio:
        args += ["-x", "--audio-format", "mp3"]

    # For video-only formats, merge with best audio
    if media_type == "video":
        args[1] = f"{fmt_id}+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
        args += ["--merge-output-format", "mp4"]

    args.append(url)

    stdout, stderr, code = run_ytdlp(args)

    if code != 0:
        err_msg = stderr.strip().split("\n")[-1] if stderr else "Unknown error"
        return jsonify({"error": f"Download failed: {err_msg}"}), 422

    return jsonify({"success": True, "message": f"Downloaded to {DOWNLOAD_DIR}"})


if __name__ == "__main__":
    print("🎬  yt-dlp server running at http://localhost:5000")
    app.run(debug=True, port=5000)
