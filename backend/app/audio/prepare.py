"""Immutable audio preparation and local voice activity candidates."""
import hashlib
import json
import os
import subprocess
import wave
from pathlib import Path

from app.config import Settings
from app.persistence.database import connect


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def speech_regions(wav_path: Path, aggressiveness: int = 2) -> dict:
    """WebRTC VAD yields measured candidates, not a ground-truth transcript."""
    import webrtcvad

    with wave.open(str(wav_path), "rb") as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, 16000):
            raise ValueError("prepared_wav_format_invalid")
        frames = source.readframes(source.getnframes())
    frame_bytes = 960  # 30 ms, 16 kHz, 16-bit mono
    vad = webrtcvad.Vad(aggressiveness)
    flags = [vad.is_speech(frames[i:i + frame_bytes], 16000)
             for i in range(0, len(frames) - frame_bytes + 1, frame_bytes)]
    # Two adjacent voiced frames suffice; bridge gaps shorter than 120 ms.
    segments = []
    start = None
    for i, voiced in enumerate(flags + [False]):
        if voiced and start is None:
            start = i
        elif not voiced and start is not None:
            if i - start >= 3:
                segments.append([start * 0.03, i * 0.03])
            start = None
    merged = []
    for start_s, end_s in segments:
        if merged and start_s - merged[-1][1] < 0.12:
            merged[-1][1] = end_s
        else:
            merged.append([start_s, end_s])
    duration = len(frames) / 32000
    speech = sum(end - start for start, end in merged)
    return {"regions": [{"start_s": round(start, 3), "end_s": round(end, 3)} for start, end in merged],
            "duration_s": round(duration, 3), "speech_s": round(speech, 3),
            "quality": "medium" if speech >= 0.5 and speech < duration * 0.98 and (duration < 10 or len(merged) > 1) else "low",
            "algorithm_version": "webrtcvad-2.0.14-30ms-mode2-v1",
            "limitations": ["VAD may mistake background sound or breathing for speech."]}


def prepare_audio(asset_id: str, settings: Settings) -> dict:
    with connect(settings.database_path) as db:
        row = db.execute("SELECT relative_path,sha256,duration_s FROM audio_assets WHERE id=?", (asset_id,)).fetchone()
    if not row:
        raise ValueError("audio_asset_not_found")
    original = settings.data_dir / row["relative_path"]
    if sha256(original) != row["sha256"]:
        raise ValueError("original_audio_hash_mismatch")
    relative = f"audio/derived/{asset_id}.16k.wav"
    target = settings.data_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        temp = target.with_suffix(".tmp.wav")
        try:
            command = [settings.ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(original),
                       "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(temp)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            if result.returncode:
                raise ValueError("audio_transcode_failed")
            temp.replace(target)
        finally:
            temp.unlink(missing_ok=True)
    regions = speech_regions(target)
    if sha256(original) != row["sha256"]:
        raise ValueError("original_audio_changed_during_analysis")
    return {"audio_asset_id": asset_id, "wav_path": relative, "wav_sha256": sha256(target),
            "original_sha256": row["sha256"], "duration_s": regions["duration_s"],
            "speech_regions": regions, "ffmpeg_version": _ffmpeg_version(settings.ffmpeg_bin)}


def _ffmpeg_version(binary: str) -> str:
    line = subprocess.run([binary, "-version"], capture_output=True, text=True, timeout=3).stdout.splitlines()[0]
    return line.split(" Copyright")[0]
