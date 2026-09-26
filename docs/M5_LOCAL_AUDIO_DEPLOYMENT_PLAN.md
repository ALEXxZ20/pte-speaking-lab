# PTE Speaking Lab：M5 Pro 内网音频计算改造与人工部署手册

**版本：**方案草案，2026-09-27<br>
**适用设备：**当前运行项目的 Mac（下称「主机」）与同一家庭内网的 MacBook M5 Pro 48GB（下称「计算机」）。<br>
**文档状态：**这是改造方案和人工操作手册。文中的「独立试运行」现在可以手动执行；「项目接入」所列接口和按钮尚未开发，不能把安装模型等同于网页已经接入模型。

## 1. 目标、边界与推荐结果

主机继续提供网页、截图 OCR、SQLite、原始文件和历史报告；计算机按任务处理录音并返回带来源的结果。目标是让用户在不调用付费 API 的条件下，取得独立转写、词时间定位、发音候选、完整的中文流利度解释，以及可生成的英语示例录音。主机离线或计算机不可达时，现有本机规则分析仍可运行。

猩际分数、转写和词色仍是外部原始数据；模型结果不能覆盖它们。Pronunciation 与 Fluency 保持独立，最后才做跨维度推断。生成的语音先标记为「待检验示例」；只有用户把它送到猩际并提供分数及截图后，才可作为高分 benchmark。Content 仍仅保存猩际分数。本项目不预测 Pearson/PTE 官方分数。

```text
浏览器 → 主机 FastAPI → 主机 SQLite / 原始资产
                       │
                       └─ SSH 加密隧道 → 计算机任务接口（仅监听 127.0.0.1）
                                            ├─ ASR / 对齐 / 发音候选
                                            ├─ 文本大模型写证据约束报告
                                            └─ TTS 生成待检验示例
```

计算机不直接访问主机数据库，也不对浏览器开放模型端口；主机负责保存最终结果。用户单人使用，任务队列并发数设为 **1**。每个重模型在单独进程运行，结果写入临时文件后退出，再启动下一个模型，避免多个模型常驻争用统一内存。

## 2. 模型选择与验证门槛

| 工作 | 第一候选 | 用法与边界 |
|---|---|---|
| 独立转写 | `mlx-community/whisper-large-v3-turbo` + `mlx-whisper` | 与猩际转写并列；检查实际朗读词、重复和尾部。词时间戳先作候选，最终定位仍需质量校验。[Apple MLX Whisper](https://github.com/ml-explore/mlx-examples/blob/main/whisper/README.md)、[模型卡](https://huggingface.co/mlx-community/whisper-large-v3-turbo) |
| 对齐与发音 | 现有 WhisperX / OpenPronounce | 先迁移耗时计算，沿用项目已有质量降级规则。OpenPronounce 音素输出仍是未经本项目校准的候选。[OpenPronounce](https://github.com/Halleck45/OpenPronounce) |
| 证据综合 | `Qwen3-32B-Q4_K_M.gguf` + `llama.cpp` | 读取两侧完整指标及所引用的证据，写独立的中文训练报告；先试 Q4，再按实测决定 Q5。Q4 文件约 19.8GB、Q5 约 23.2GB，**文件大小不是运行内存**。[Qwen 模型文件](https://huggingface.co/Qwen/Qwen3-32B-GGUF/tree/main)、[llama.cpp 运行说明](https://github.com/QwenLM/Qwen3/blob/main/docs/source/run_locally/llama.cpp.md) |
| 示例语音 | `mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-bf16` | 先选英语预置音色 `Ryan` 或 `Aiden`；合成后回转写和人工听检。CustomVoice 与需要参考录音的 Base 变体不可混淆。[MLX-Audio 模型说明](https://github.com/Blaizzy/mlx-audio/blob/main/docs/models/tts/qwen3-tts.md) |
| 可选第二意见 | `Qwen2-Audio-7B-Instruct-4bit` | 仅在可疑短片段上试验音频理解；不得直接生成已证实的错音、病因或 PTE 分。[MLX-Audio 实现](https://github.com/Blaizzy/mlx-audio/blob/main/mlx_audio/stt/models/qwen2_audio/README.md) |

不先以 Qwen3-Omni 30B 搭建主流程。它的不同精度、运行框架及音频长度对应不同内存要求；需单独在这台机器上验证，不能把官方视频场景的 BF16 数字直接套到纯音频或 4-bit。[官方说明](https://github.com/QwenLM/Qwen3-Omni)、[MLX 音频问题记录](https://github.com/Blaizzy/mlx-vlm/issues/1620)

**模型选型验收：**使用项目已有的真实双边录音以及 `Choices of Lunch`，记录转写与人工听到的差异、尾词是否保留、词定位偏差、建议是否引用真实证据、TTS 是否读全原文、单次耗时、内存压力和交换内存。没有这些实测结果，不宣称 32B 一定优于 8B，也不宣称 M5 Pro 上的 Q5 可以稳定运行。

## 3. 人工部署：连接两台 Mac

以下步骤不要求使用 Codex。终端命令旁注明在哪台机器执行。**不要把账户密码、SSH 私钥或模型接口令牌贴进聊天、Git 或项目文档。**

### 3.1 在计算机上完成一次图形界面设置

1. 两台 Mac 接入同一个可信家庭网络，不使用访客网络；计算机接电源，并在系统设置中避免执行任务期间自动睡眠。路由器为计算机做 DHCP 地址保留。记录它的内网 IP，例如 `192.168.5.20`；此地址仅是示例。
2. 在计算机打开 **系统设置 → 通用 → 共享 → 远程登录**，开启远程登录，选「仅这些用户」，加入将要运行模型的账户。无需为了本项目勾选「允许远程用户访问完整磁盘」。Apple 会在此页面显示 SSH 登录格式。[Apple 远程登录指南](https://support.apple.com/guide/mac-help/allow-a-remote-computer-to-access-your-mac-mchlp1066/mac)
3. 在计算机终端运行 `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`，记下主机指纹，供首次连接时核对。

### 3.2 配置 SSH 密钥

在**主机**终端运行：

```sh
ssh-keygen -t ed25519 -f ~/.ssh/pte_m5 -C pte-m5
cat ~/.ssh/pte_m5.pub
```

把第二条命令输出的**公钥整行**复制到计算机。在**计算机**终端运行：

```sh
mkdir -p ~/.ssh
chmod 700 ~/.ssh
nano ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

在 `nano` 中将公钥粘贴成独立一行并保存；已有其他公钥时保留原行。`~/.ssh/pte_m5` 私钥只留在主机，不发送给任何人。密钥与 `authorized_keys` 的用途见 [OpenSSH 手册](https://man.openbsd.org/ssh-keygen)。

把下例中的 `m5user` 和 `192.168.5.20` 换成实际用户名和内网 IP，在**主机**终端连接：

```sh
ssh -o IdentitiesOnly=yes -i ~/.ssh/pte_m5 m5user@192.168.5.20
```

首次连接前，将提示的主机指纹与步骤 3.1 在计算机上读到的指纹核对；不相同就停止。连接后运行 `uname -m`，预期输出 `arm64`。重新连接、断开网络和唤醒计算机后各试一次。连接不了时依次检查同网段、访客网络隔离、计算机睡眠、远程登录用户权限与路由器保留地址；**不要通过公网转发 SSH 端口**。

## 4. 人工部署：在 M5 上独立试运行模型

本节均在**计算机**终端执行。建议有至少 80GB 可用磁盘空间再下载模型；这是部署余量建议，实际下载量取决于所选模型和缓存。若已安装同类软件，先核对版本，不必重复安装。

### 4.1 系统软件

按 [Homebrew 官方安装指南](https://docs.brew.sh/Installation) 安装 Homebrew；Apple Silicon 默认位置是 `/opt/homebrew`。安装器给出 shell 初始化步骤，应照其终端提示完成。随后运行：

```sh
brew install ffmpeg python@3.12 llama.cpp
brew --version
ffmpeg -version
python3.12 --version
llama-server --help
```

系统工具优先使用 Homebrew；Python 模型库分别放到虚拟环境中。Homebrew 的 [Python 3.12](https://formulae.brew.sh/formula/python@3.12) 和 [llama.cpp](https://formulae.brew.sh/formula/llama.cpp) 均提供 Apple Silicon 安装方式。若 Homebrew 安装提示缺少 Xcode Command Line Tools，按提示或运行 `xcode-select --install`。

### 4.2 先跑文本大模型

先在终端前台运行；首次会下载约 20GB 的 Q4 模型。保持该窗口打开：

```sh
llama-server -hf Qwen/Qwen3-32B-GGUF:Q4_K_M --alias pte-qwen3-32b --jinja -ngl 99 -c 8192 --host 127.0.0.1 --port 8080
```

另开**计算机**终端运行 `curl http://127.0.0.1:8080/health`；返回 `{"status":"ok"}` 表示已加载。随后用一条短请求确认模型真正能生成文字：

```sh
curl -sS http://127.0.0.1:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"pte-qwen3-32b","messages":[{"role":"user","content":"用一句中文解释 WPM 是什么。"}],"max_tokens":120}'
```

返回 JSON 中应有 `choices` 和生成的文字；`--alias` 将接口模型名固定为 `pte-qwen3-32b`。若请求失败，先读 `curl http://127.0.0.1:8080/v1/models` 和模型终端日志。`-c 8192` 是第一轮测试使用的上下文上限，不是模型质量要求。终端输入 `Ctrl-C` 停止模型，确认退出后再试其他重模型。`llama-server` 的接口和健康检查见 [官方文档](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)。

### 4.3 试跑录音转写

在计算机创建单独的 ASR 环境：

```sh
mkdir -p ~/pte-worker/input ~/pte-worker/output
python3.12 -m venv ~/pte-worker/asr-venv
~/pte-worker/asr-venv/bin/python -m pip install -U pip mlx-whisper
```

把一份**自己有权处理的**测试录音放到 `~/pte-worker/input/sample.m4a`。若使用项目现有测试数据包，先在**主机**终端进入项目目录，再复制录音；替换示例中的 M5 用户名和 IP：

```sh
cd /Users/alex/codex_project/PTE口语诊断分析
scp -i ~/.ssh/pte_m5 "测试数据包/用户数据/用户口语音频.m4a" m5user@192.168.5.20:pte-worker/input/sample.m4a
```

然后在计算机运行：

```sh
~/pte-worker/asr-venv/bin/python - ~/pte-worker/input/sample.m4a <<'PY'
import sys
import mlx_whisper

result = mlx_whisper.transcribe(
    sys.argv[1],
    path_or_hf_repo="mlx-community/whisper-large-v3-turbo",
    language="en",
    word_timestamps=True,
)
print(result["text"])
for segment in result["segments"]:
    for word in segment.get("words", [])[-3:]:
        print(word)
PY
```

首次运行会下载权重；核对输出的末尾词与原录音，别只看转写开头。词时间戳由模型生成，实际项目仍要做独立质量检查。[MLX Whisper 用法](https://github.com/ml-explore/mlx-examples/blob/main/whisper/README.md)

### 4.4 试跑示例语音

在计算机创建单独的 TTS 环境：

```sh
python3.12 -m venv ~/pte-worker/tts-venv
~/pte-worker/tts-venv/bin/python -m pip install -U pip mlx-audio
~/pte-worker/tts-venv/bin/mlx_audio.tts.generate --help
```

先用**一条短的、自拟的英语句子**验证。若当前安装版本的帮助中有 `--voice`、`--lang_code` 与 `--output_path`，运行：

```sh
~/pte-worker/tts-venv/bin/mlx_audio.tts.generate \
  --model mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-bf16 \
  --text "The chart shows the choices of lunch." \
  --voice Ryan --lang_code English --output_path ~/pte-worker/output
```

到输出目录播放生成文件。通过后再用完整共同原文，检查遗漏、发音与不自然停顿；回转写可查词是否读全，但不能证明这份录音会在猩际得高分。不同 MLX-Audio 版本的命令选项可能变化，以实际 `--help` 和[官方 CLI 文档](https://github.com/Blaizzy/mlx-audio/blob/main/docs/getting-started/quickstart-cli.md)为准。`1.7B-CustomVoice` 的能力和英语音色见[模型文档](https://github.com/Blaizzy/mlx-audio/blob/main/docs/models/tts/qwen3-tts.md)。

### 4.5 记录可运行性，而不猜机器余量

每跑一个模型，在计算机打开**活动监视器 → 内存**，记录绿色/黄色/红色内存压力、交换内存、模型加载时间、单份录音耗时与浏览器是否顺畅。先完成 Q4 与两侧录音实测；只有在内存压力和时延可接受时才试 Q5。不要同时启动文本 32B、音频理解模型和 TTS。试验失败可退出该模型进程，不会影响主机上的旧报告。[Apple 内存压力说明](https://support.apple.com/guide/activity-monitor/view-memory-usage-actmntr1004/mac)

### 4.6 从主机验证内网隧道

保持步骤 4.2 的 `llama-server` 在计算机运行。另在**主机**终端打开一个窗口，替换示例用户名/IP 后运行：

```sh
ssh -o IdentitiesOnly=yes -i ~/.ssh/pte_m5 -N -L 18080:127.0.0.1:8080 m5user@192.168.5.20
```

再开一个主机终端运行 `curl http://127.0.0.1:18080/health`。看到 `{"status":"ok"}` 即证明主机能通过 SSH 隧道访问 M5 上的模型；外部设备仍不能直接打开 M5 的 8080 端口。按 `Ctrl-C` 停止隧道。未来项目的任务接口将使用同样的连接方式和**另一组专用端口**；不要把 18080 误填进现在的项目 `.env` 并期待完整报告自动出现。

## 5. 项目接入：开发者或人工维护者的实施清单

**以下尚未实现。**人工维护者可以按顺序开发，每步通过验收后再接下一步。保留现有 `1.0`、`v1.99` 标签和历史报告；新增代码以新版本记录算法和模型来源。

1. **备份与基线。**备份主机项目 `data/` 与数据库，记录当前提交和 `.env` 中的配置名（不复制密钥值），用 `Choices of Lunch` 导出一份当前报告。历史报告绑定的两侧样本修订不可改写。
2. **新增远端计算模块。**计算机只监听 `127.0.0.1`；主机通过 SSH 隧道连接。计算机提供 `POST /v1/assets` 上传音频并返回 SHA-256、`POST /v1/jobs` 创建分析/报告/TTS 任务、`GET /v1/jobs/{id}` 查询状态、`GET /v1/jobs/{id}/result` 取结果与衍生资产。任务包含类型、两侧不可变 revision ID、输入资产 ID、原文与实际转写、目标词序号、模型配置；响应包含输入哈希、模型 ID/版本、时间基准、质量等级、错误原因和证据引用。限制任务并发为 1；相同输入与配置可按哈希复用结果。任务临时音频设清理期限，主机保留原始文件。
3. **让主机调度任务。**主机接收分析请求后先返回 `run_id`，网页轮询进度。重计算交给远端；主机继续做截图 OCR、数据校验、Fluency/Pronunciation 独立结果的持久化、Comparison 与 Diagnosis。先只接入 ASR/对齐，再接发音候选和报告，最后接 TTS。计算机或模型不可达时，保留本机可用结果并标明具体降级原因；不填虚构时间戳或 0 次停顿。
4. **新增完整的本地 AI 报告。**当前文本模型只改写最多三条既有结论，且同步请求超时为 20 秒；不能只替换模型名。另建「证据约束综合报告」步骤，输入两侧全部有效流利度指标、质量等级、共享词和被选中的时间位置；输出有证据 ID 的观察、局限和练习步骤。数值由主机核验；模型不能改变外部分数或提出无证据的具体音素结论。原规则报告与新报告并列保存。
5. **新增示例录音入口。**前端从共同原文请求 TTS，预览可回听录音、所用音色和文字核查结果；用户决定保存为「待检验示例」。猩际分数和逐词截图仍需用户自行提供；此前不得自动标成高分 benchmark。保留原始上传 benchmark 的既有流程。
6. **密钥与设置。**增加远端计算开关、内网连接状态、各模型 ID、超时及本地降级选项。SSH 私钥仅在主机用户账户，任务令牌仅在后端环境文件；浏览器不能收到密钥。原 CLIProxyAPI 配置可保留为手动回退，关闭时不得发生外部模型请求。
7. **后台启动。**开发完成后，计算机任务程序可由 macOS `launchd` 启动。用户登录期间运行用 `~/Library/LaunchAgents`；若要求重启后、无人登录也持续可用，需要另设计系统级 LaunchDaemon。SSH 隧道也要随服务重连，并有健康检查。不要在独立试运行阶段就把不成熟的模型服务设成开机常驻。[Apple launchd 文档](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)

**为人工运维交付的脚本与步骤：**实施第 2、3、7 项时，须同时提供计算机上的 `worker-start.sh`、`worker-stop.sh`、`worker-status.sh`，主机上的 `worker-tunnel-start.sh`、`worker-tunnel-stop.sh`、`worker-tunnel-status.sh`；脚本放在各自项目的 `scripts/`，给出可读状态及日志位置，并先手动通过 `--help` 或文档说明。完成后，人工操作顺序固定为：①在计算机运行 `worker-start.sh` 并确认 `worker-status.sh` 正常；②在主机运行 `worker-tunnel-start.sh` 并确认隧道状态；③在主机重启 PTE 应用并检查设置页的远端健康状态；④运行一份真实样本。停止顺序相反。模型更新前先停任务、备份当前版本与配置，再更新和做回归测试。这些脚本**现在不存在**，属于改造交付物。

**接口设计原则：**主机只依赖一个「提交任务／查状态／取带证据结果」的远端计算接口；模型装载、单进程顺序调度、缓存与临时文件清理由计算机内部完成。计算机不拥有 Comparison 或外部分数，避免两台机器争写 SQLite。

## 6. 联调、故障排查与回退

完成接入后，以同一份真实双边样本逐项验收：

- 两侧音频传输 SHA-256 一致；断网和计算机睡眠时能给出可读错误、重试后不重复写报告；删除比较记录时清理主机衍生资产与过期远端临时文件。
- 独立转写完整保留录音尾部；它与猩际转写不同只提示人工核查，不直接判为发音错误。时间戳错位或无法定位时质量降级，回听按钮不跳错词。
- Pronunciation、Fluency 可各自运行；完整中文报告的每条关键结论能点到证据和时间，低质量指标不被描述成已证实事实。模型退出或超时仍保留本机规则结果。
- TTS 文件能播放，回转写与原文差异会提示；没有猩际分数/截图时不能变成高分 benchmark。旧上传方式、旧报告和内网浏览器访问仍正常。
- 分别在 M5 可用、断开、模型崩溃、内存压力过高时运行；记录质量、耗时、内存压力与交换内存。模型版本或量化方式变化后重新测试，不以模型参数量代替结果评价。

**人工回退：**在主机设置中关闭远端计算开关，重启主机应用；停止计算机任务程序和 SSH 隧道。不要回滚或覆盖 `data/`、样本修订与历史报告。旧运行配置仍留在每份历史报告中；需要比较新旧算法时创建**新分析运行**。若曾新增数据库迁移，回退应用前先使用变更时制作的数据库备份，而不是手工删除表。

## 7. 当前状态与下一步

截至本方案日期，项目**没有**远端计算任务接口、内置 ASR、内置 TTS 或完整的本地大模型报告。第 3–4 节可由人现在独立执行，用于验证 M5 环境和模型；第 5–6 节是后续改造与验收清单。先做两侧真实录音的 ASR、Q4 文本报告和短句 TTS 试验，再根据实测决定 Q5、Qwen2-Audio 或 Qwen3-Omni 是否值得加入。
