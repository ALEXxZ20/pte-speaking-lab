"""从已标准化的 WAV 提取有界的展示曲线；不参与 PTE 评分或诊断推断。"""
import json
import math
import subprocess
import sys
import wave
from pathlib import Path

VERSION = "acoustic-display-v1"
HOP_S = 0.05
WINDOW_S = 0.06
MAX_POINTS = 2400


def extract(wav_path: Path) -> dict:
    """按 50 毫秒取样：RMS 表示能量，自相关峰只作粗略音高线索。"""
    import numpy as np

    with wave.open(str(wav_path), "rb") as source:
        if source.getnchannels() != 1 or source.getsampwidth() != 2 or source.getframerate() != 16000:
            raise ValueError("prepared_wav_format_required")
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
    hop = int(16000 * HOP_S)
    window = int(16000 * WINDOW_S)
    if len(samples) < window:
        return {"status": "unavailable", "reason": "audio_too_short", "version": VERSION, "points": []}
    starts = range(0, len(samples) - window + 1, hop)
    if len(starts) > MAX_POINTS:
        raise ValueError("audio_exceeds_acoustic_display_limit")
    energy = np.array([float(np.sqrt(np.mean(samples[start:start + window] ** 2))) for start in starts])
    peak = float(energy.max())
    if peak < 0.002:
        return {"status": "unavailable", "reason": "no_audible_signal", "version": VERSION, "points": []}
    # 相对本次录音峰值设门槛，静音/微弱噪声处不输出音高。
    gate = max(0.002, peak * 0.04)
    points = []
    voiced = 0
    for index, start in enumerate(starts):
        frame = samples[start:start + window]
        rms = float(energy[index])
        pitch = None
        if rms >= gate:
            centered = (frame - frame.mean()) * np.hanning(window)
            spectrum = np.fft.rfft(centered, n=2048)
            correlation = np.fft.irfft(spectrum * spectrum.conjugate(), n=2048)
            low, high = math.ceil(16000 / 450), math.floor(16000 / 75)
            lags = np.arange(low, high + 1)
            # 不同延迟的有效重叠长度不同；归一化后的峰值只是周期性线索。
            normalized = correlation[lags] / (correlation[0] * (window - lags) / window + 1e-12)
            best = int(np.argmax(normalized))
            if normalized[best] >= 0.55:
                pitch = round(16000 / int(lags[best]), 1)
                voiced += 1
        points.append({"time_s": round((start + window / 2) / 16000, 3),
                       "pitch_hz": pitch,
                       "energy_dbfs": round(20 * math.log10(max(rms, 1e-8)), 1)})
    return {"status": "complete" if voiced >= 5 else "unavailable",
            "reason": None if voiced >= 5 else "no_reliable_pitch",
            "version": VERSION, "points": points if voiced >= 5 else [],
            "limitations": ["Pitch is an uncalibrated periodicity estimate, not a pronunciation or PTE score.",
                            "Energy depends on recording gain; do not compare loudness across devices."]}


def extract_bounded(wav_path: Path, timeout_s: int = 20) -> dict:
    """在独立进程限时运行，失败只返回曲线不可用，不中断双引擎分析。"""
    try:
        result = subprocess.run([sys.executable, "-m", "app.audio.acoustics", str(wav_path)],
                                capture_output=True, text=True, timeout=timeout_s, check=True)
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        reason = "processing_timeout"
    except (OSError, subprocess.CalledProcessError, ValueError, json.JSONDecodeError):
        reason = "processing_failed"
    return {"status": "unavailable", "reason": reason, "version": VERSION, "points": []}


if __name__ == "__main__":
    print(json.dumps(extract(Path(sys.argv[1])), separators=(",", ":")))
