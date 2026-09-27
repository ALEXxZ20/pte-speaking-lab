# M5 镜像中的第三方模型与依赖

此清单记录镜像**计划**预装的来源；首次镜像构建成功后，需用 `/opt/pte-models/manifest.json`、`pip list`、镜像 digest 再核对实际内容。镜像仅供本项目私有内网使用。若将来分发镜像，应随镜像提供相应完整许可文本和源代码/再链接信息，不只保留此摘要。

| 组件 | 固定版本或来源 | 已核对许可/限制 |
|---|---|---|
| OpenPronounce Python 包 | `0.3.0` | [项目 MIT 许可](https://github.com/Halleck45/OpenPronounce/blob/main/LICENSE)。本项目只调用 `phones`，不使用其默认 gTTS 参考路径。 |
| OpenPronounce 音素模型 | [`facebook/wav2vec2-lv-60-espeak-cv-ft` 提交 `ae45363b…`](https://huggingface.co/facebook/wav2vec2-lv-60-espeak-cv-ft/tree/ae45363bf3413b374fecd9dc8bc1df0e24c3b7f4) | 模型页标记 Apache-2.0。镜像内下载固定提交，并从本地目录读取。 |
| WhisperX Python 包 | `3.8.6` | [项目 BSD-2-Clause 许可](https://github.com/m-bain/whisperX/blob/main/LICENSE)。仅使用英文强制对齐，不调用其 ASR/说话人分离模型。 |
| WhisperX 英文对齐权重 | torchaudio 2.8.0 `WAV2VEC2_ASR_BASE_960H` / `wav2vec2_fairseq_base_ls960_asr_ls960.pth` | [torchaudio 的该 bundle 文档](https://github.com/pytorch/audio/blob/main/src/torchaudio/pipelines/_wav2vec2/impl.py)标注原模型 MIT 并指向 fairseq 许可。构建时下载，离线重载验证。 |
| Edge TTS 客户端 | `edge-tts==7.2.8` | [项目许可](https://github.com/rany2/edge-tts/blob/master/LICENSE)说明主体为 LGPLv3，个别文件 MIT；在线服务的使用条款另行适用，镜像不包含微软语音模型。 |
| 系统工具 | Debian bookworm 的 FFmpeg、Tesseract、eSpeak NG | 由发行包管理器安装，具体版本及随附许可需以构建产物核对。 |

Python 转移依赖与 npm 依赖在镜像构建时由锁定的顶层依赖解析安装；若对外分发镜像，还需生成完整 SBOM/许可证清单并处理 LGPL 等再分发要求。第三方模型结果不等同于猩际或官方 PTE 评分。
