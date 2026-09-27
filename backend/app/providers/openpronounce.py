"""Optional local phone signal; never invokes OpenPronounce's default gTTS path."""
import os
import wave
from pathlib import Path


class OpenPronouncePhones:
    name = "openpronounce-0.3.0-phones"

    def assess(self, wav_path: Path, tokens: list[dict], timed_tokens: list[dict], target_index: int) -> dict:
        import numpy as np
        from openpronounce import phones

        # 镜像内预装固定版本模型时，直接从本地路径加载，避免运行时联网拉取。
        local_model = os.environ.get("PTE_OPENPRONOUNCE_MODEL_PATH")
        if local_model:
            phones.PHONE_MODEL_NAME = local_model

        by_index = {token["index"]: token for token in timed_tokens if token.get("quality") == "medium"}
        included = [i for i in range(max(0, target_index - 1), min(len(tokens), target_index + 2)) if i in by_index]
        if target_index not in included:
            raise ValueError("target_timestamp_unreliable")
        first, last = included[0], included[-1]
        start = max(0, by_index[first]["start_s"] - 0.1)
        end = by_index[last]["end_s"] + 0.1
        with wave.open(str(wav_path), "rb") as source:
            if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, 16000):
                raise ValueError("wav_format_invalid")
            source.setpos(int(start * 16000))
            pcm = source.readframes(int((end - start) * 16000))
        waveform = np.frombuffer(pcm, dtype="<i2").astype("float32") / 32768
        if len(waveform) < 3200:
            raise ValueError("target_clip_too_short")
        phrase = " ".join(tokens[i]["surface"] for i in included)
        recognition = phones.recognize_phones(waveform, 16000)
        comparison = phones.compare_phones(recognition, phrase)
        target_position = included.index(target_index)
        candidates = [error for error in comparison["errors"] if error.get("position") == target_position]
        return {"target_index": target_index, "clip_start_s": round(start, 3), "clip_end_s": round(end, 3),
                "phone_error_rate": comparison.get("phone_error_rate"), "candidate_errors": candidates,
                "heard_phone_count": len(recognition.phones),
                "limitation": "Uncalibrated model candidate; not Xingji or official PTE scoring."}
