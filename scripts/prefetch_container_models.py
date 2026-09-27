#!/usr/bin/env python3
"""构建时预装当前两条本地模型路径，并在断网构建层重新加载。"""

import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import zipfile

# 使用当前项目已经验证过的模型提交，而不是随时间变化的 main。
OPENPRONOUNCE_REPO = "facebook/wav2vec2-lv-60-espeak-cv-ft"
OPENPRONOUNCE_REVISION = "ae45363bf3413b374fecd9dc8bc1df0e24c3b7f4"
PUNKT_URL = "https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/tokenizers/punkt_tab.zip"
PUNKT_SHA256 = "e57f64187974277726a3417ca6f181ec5403676c717672eef6a748a7b20e0106"


def sha256(path: Path) -> str:
    """记录镜像内实际权重的哈希，方便迁移后核对。"""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) == 2 else ""
    if mode not in {"prefetch", "verify"}:
        raise SystemExit("usage: prefetch_container_models.py prefetch|verify")
    root = Path(os.environ["PTE_MODELS_DIR"])
    phone_dir = root / "openpronounce"
    if mode == "prefetch":
        from huggingface_hub import snapshot_download

        # local_dir 形成独立、可复制的模型目录；运行时不会依赖 HF 缓存引用。
        snapshot_download(repo_id=OPENPRONOUNCE_REPO,
                          revision=OPENPRONOUNCE_REVISION,
                          local_dir=phone_dir)
        # NLTK 下载器在代理环境中可能拒绝代理 IP；固定来源和哈希后用 curl 获取。
        tokenizers = root / "nltk/tokenizers"
        tokenizers.mkdir(parents=True, exist_ok=True)
        archive = tokenizers / "punkt_tab.zip"
        subprocess.run(["curl", "--fail", "--location", "--retry", "3", "--silent",
                        "--show-error", "--output", str(archive), PUNKT_URL], check=True)
        if sha256(archive) != PUNKT_SHA256:
            raise RuntimeError("punkt_tab_checksum_mismatch")
        with zipfile.ZipFile(archive) as package:
            package.extractall(tokenizers)
    if not phone_dir.is_dir():
        raise RuntimeError("openpronounce_model_missing")
    if sha256(root / "nltk/tokenizers/punkt_tab.zip") != PUNKT_SHA256:
        raise RuntimeError("punkt_tab_missing_or_changed")

    from openpronounce import phones
    import whisperx

    phones.PHONE_MODEL_NAME = str(phone_dir)
    phones._load_model()
    # WhisperX 英文默认使用 torchaudio 的固定 bundle，预热相同的 CPU 代码路径。
    model, metadata = whisperx.load_align_model(language_code="en", device="cpu")
    if metadata.get("type") != "torchaudio" or model is None:
        raise RuntimeError("whisperx_align_model_invalid")
    del model
    phone_weights = phone_dir / "pytorch_model.bin"
    align_weights = root / "torch/hub/checkpoints/wav2vec2_fairseq_base_ls960_asr_ls960.pth"
    if not phone_weights.is_file() or not align_weights.is_file():
        raise RuntimeError("model_weights_missing")
    manifest = {
        "openpronounce_repo": OPENPRONOUNCE_REPO,
        "openpronounce_revision": OPENPRONOUNCE_REVISION,
        "alignment_bundle": "WAV2VEC2_ASR_BASE_960H",
        "openpronounce_sha256": sha256(phone_weights),
        "alignment_sha256": sha256(align_weights),
        "mode": "cpu",
    }
    if mode == "prefetch":
        (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    elif json.loads((root / "manifest.json").read_text()) != manifest:
        raise RuntimeError("model_manifest_mismatch")
    print(f"model {mode} ok: {manifest['openpronounce_revision']}")


if __name__ == "__main__":
    main()
