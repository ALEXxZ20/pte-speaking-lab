"""Extract Xingji transcript drafts and provisional word colors from screenshots."""
from __future__ import annotations

import csv
import io
import re
import subprocess
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

PARSER_VERSION = "xingji-light-tesseract-v2"
COLORS = ("red", "yellow", "green")


@dataclass(frozen=True)
class OCRWord:
    text: str
    confidence: float
    bbox: tuple[int, int, int, int]


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold().replace("’", "'")
    return text.strip(".,!?;:\"'()[]{}<>—–-…，。！？：；")


def tokenize(transcript: str) -> list[dict]:
    # Whitespace spans preserve punctuation and exact source positions.
    return [{"index": i, "surface": match.group(), "normalized": normalize(match.group()),
             "char_start": match.start(), "char_end": match.end()}
            for i, match in enumerate(re.finditer(r"\S+", transcript))]


def unique_ordered_matches(tokens: list[str], words: list[str]) -> dict[int, int]:
    """Accept only correspondences present in every optimal ordered LCS alignment.

    In particular, a cropped 'the' cannot be assigned arbitrarily to one of
    several repeated transcript occurrences. No fuzzy substitutions are made.
    """
    n, m = len(tokens), len(words)
    if n * m > 2_000_000:
        raise ValueError("screenshot_mapping_too_large")
    before = [[0] * (m + 1) for _ in range(n + 1)]
    after = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n):
        for j in range(m):
            before[i + 1][j + 1] = (before[i][j] + 1 if tokens[i] and tokens[i] == words[j]
                                    else max(before[i][j + 1], before[i + 1][j]))
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            after[i][j] = (after[i + 1][j + 1] + 1 if tokens[i] and tokens[i] == words[j]
                            else max(after[i + 1][j], after[i][j + 1]))
    optimum = before[n][m]
    result = {}
    for i, token in enumerate(tokens):
        options = [j for j, word in enumerate(words) if token and token == word
                   and before[i][j] + 1 + after[i + 1][j + 1] == optimum]
        can_skip = any(before[i][j] + after[i + 1][j] == optimum for j in range(m + 1))
        if len(options) == 1 and not can_skip:
            result[i] = options[0]
    return result


def classify_color(image: Image.Image, bbox: tuple[int, int, int, int]) -> tuple[str, dict]:
    left, top, width, height = bbox
    if width <= 0 or height <= 0 or left < 0 or top < 0 or left + width > image.width or top + height > image.height:
        return "unknown", {color: 0 for color in COLORS}
    counts = dict.fromkeys(COLORS, 0)
    for r, g, b in image.crop((left, top, left + width, top + height)).convert("RGB").get_flattened_data():
        if r > 150 and g < 105 and b < 135:
            counts["red"] += 1
        elif g > 115 and r < 135 and b < 135 and g > r + 25 and g > b + 25:
            counts["green"] += 1
        elif r > 145 and 65 < g < 205 and b < 120 and r > g:
            counts["yellow"] += 1
    color = max(counts, key=counts.get)
    if counts[color] < 5 or counts[color] / max(sum(counts.values()), 1) < 0.65:
        color = "unknown"
    return color, counts


def map_ocr_words(transcript: str, words: list[OCRWord], image: Image.Image,
                  source_id: str, min_confidence: float = 40.0) -> dict:
    tokens = tokenize(transcript)
    matching = unique_ordered_matches([t["normalized"] for t in tokens], [normalize(w.text) for w in words])
    # Sparse accidental matches against unrelated screenshots are never colored.
    coverage = len(matching) / max(len(tokens), 1)
    for token in tokens:
        token.update(color="unknown", candidate_color="unknown", quality="unavailable",
                     color_review_status="unreviewed", source_type="external",
                     source_ref=source_id, bbox=None, ocr_text=None, ocr_confidence=None,
                     reason="unmatched_or_ambiguous")
        if token["index"] not in matching:
            continue
        word = words[matching[token["index"]]]
        color, pixels = classify_color(image, word.bbox)
        token.update(bbox=list(word.bbox), ocr_text=word.text, ocr_confidence=word.confidence,
                     color_pixels=pixels)
        if coverage < 0.5:
            token["reason"] = "insufficient_transcript_coverage"
        elif word.confidence < min_confidence:
            token["reason"] = "low_ocr_confidence"
        elif color == "unknown":
            token["reason"] = "uncertain_color"
        else:
            token.update(candidate_color=color, quality="low", reason="screenshot_candidate")
    candidate_count = sum(t["candidate_color"] != "unknown" for t in tokens)
    return {"parser_version": PARSER_VERSION, "transcript_raw": transcript,
            "source_ref": source_id, "image_size": list(image.size), "tokens": tokens,
            "status": "draft", "review_required": True,
            "matched_count": len(matching), "candidate_count": candidate_count,
            "unknown_count": len(tokens) - candidate_count,
            "candidate_color_counts": {c: sum(t["candidate_color"] == c for t in tokens) for c in COLORS},
            "pause_labels": [], "pause_status": "unavailable",
            "warnings": ["Screenshot colors are provisional until reviewed.",
                         "Pause symbols are not yet validated; empty labels do not mean no pauses."]
                        + (["Some transcript tokens are unmatched or ambiguous."] if len(matching) < len(tokens) else [])}


def extract_words(path: Path, executable: str = "tesseract") -> list[OCRWord]:
    try:
        result = subprocess.run([executable, str(path), "stdout", "-l", "eng", "--psm", "3", "tsv"],
                                capture_output=True, text=True, check=True, timeout=45)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("screenshot_ocr_unavailable") from exc
    words = []
    for row in csv.DictReader(io.StringIO(result.stdout), delimiter="\t"):
        if row.get("level") == "5" and re.search(r"[A-Za-z0-9]", row.get("text", "")):
            words.append(OCRWord(row["text"], float(row["conf"]),
                                 tuple(int(row[k]) for k in ("left", "top", "width", "height"))))
    return words


def extract_transcript_words(words: list[OCRWord], image: Image.Image) -> list[OCRWord]:
    """Keep the largest contiguous block of colored English word lines."""
    colored = [word for word in words if re.search(r"[A-Za-z]", word.text)
               and classify_color(image, word.bbox)[0] != "unknown" and word.confidence >= 20]
    if not colored:
        return []
    heights = sorted(word.bbox[3] for word in colored)
    height = max(12, heights[len(heights) // 2])
    lines: list[list[OCRWord]] = []
    for word in sorted(colored, key=lambda item: item.bbox[1]):
        if not lines or word.bbox[1] - lines[-1][-1].bbox[1] > height * 0.8:
            lines.append([])
        lines[-1].append(word)
    substantial = [line for line in lines if len(line) >= 3]
    groups: list[list[OCRWord]] = []
    for line in substantial:
        if not groups or line[0].bbox[1] - groups[-1][-1].bbox[1] > height * 4:
            groups.append([])
        groups[-1].extend(line)
    if not groups:
        return []
    block = max(groups, key=len)
    top = min(word.bbox[1] for word in block) - height
    bottom = max(word.bbox[1] + word.bbox[3] for word in block) + height
    return [word for word in words if top <= word.bbox[1] <= bottom and re.search(r"[A-Za-z0-9]", word.text)]


def preview_screenshot(image_path: Path | str, source_id: str, kind: str = "xingji",
                       executable: str = "tesseract", transcript_override: str | None = None) -> dict:
    path = Path(image_path)
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("screenshot_too_large")
    with Image.open(path) as original:
        if original.width * original.height > 20_000_000:
            raise ValueError("screenshot_too_many_pixels")
        image = original.convert("RGB")
    words = extract_words(path, executable)
    if kind == "xingji":
        words = extract_transcript_words(words, image)
    elif kind != "reading_script":
        raise ValueError("invalid_screenshot_kind")
    transcript = " ".join(word.text for word in words)
    if not transcript.strip():
        raise ValueError("screenshot_text_not_found")
    draft = map_ocr_words(transcript_override or transcript, words, image, source_id) if kind == "xingji" else None
    return {"source_ref": source_id, "kind": kind, "text": transcript,
            "word_count": len(words), "draft": draft, "parser_version": PARSER_VERSION}


def map_screenshot(transcript: str, image_path: Path | str, source_id: str,
                   executable: str = "tesseract") -> dict:
    """Map one light-theme screenshot; does not modify or persist source files."""
    path = Path(image_path)
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("screenshot_too_large")
    with Image.open(path) as original:
        if original.width * original.height > 20_000_000:
            raise ValueError("screenshot_too_many_pixels")
        image = original.convert("RGB")
    return map_ocr_words(transcript, extract_words(path, executable), image, source_id)
