# PTE Speaking Lab 配置与内网使用

**本文件对应当前可运行代码。** 项目根目录为 `/Users/alex/codex_project/PTE口语诊断分析/`。配置文件是根目录 `.env`，示例为 [`.env.example`](../.env.example)。更改 `.env` 后重启服务。不要把真实密钥、密码或录音提交到 Git。

## 1. 两种启动方式

| 模式 | 命令 | 地址 | 用途 |
|---|---|---|---|
| 本机开发 | `./scripts/dev.sh` | `http://127.0.0.1:5173` | Vite 热更新，后端在 8000；脚本强制关闭 LAN 模式。 |
| 内网使用 | `npm run build --prefix frontend`，然后 `./scripts/start.sh` | `http://192.168.5.14:8765`（当前配置） | FastAPI 同源提供网页、API 和录音；HTTP Basic 密码保护，无热更新。 |

`./scripts/start.sh` 后台启动，`./scripts/stop.sh` 停止，`./scripts/restart.sh` 重启；服务由 macOS `launchd` 托管，命令结束后仍运行。需要前台查看日志时可运行 `./scripts/serve_lan.sh`。Mac 休眠或退出服务后其他设备无法访问。浏览器会弹出登录框，用户名默认为 `pte`，密码在项目根目录 `.env` 的 `PTE_LAN_PASSWORD`。此密码已随机生成；不要发送完整 `.env` 给别人。给他人密码时应采用可信渠道。

内网启动脚本会把 Homebrew 常用目录加入后台服务的 `PATH`，并在启动前检查 `FFMPEG_BIN`、`FFPROBE_BIN`。若 FFmpeg 装在其他位置，可在 `.env` 为这两项填写可执行文件的绝对路径。打开 `/api/v1/health` 时，`ffmpeg` 与 `ffprobe` 都应为 `ok`；否则分析可能提示缺少本地音频工具。

当前 Mac 的 `en0` 地址是 `192.168.5.14/24`；该地址已用于启动服务并通过本机地址测试。**“当前地址”尚不等于永久固定地址。** 在路由器的 DHCP 地址保留/静态租约界面，将这台 Mac 的当前 Wi-Fi MAC `5a:34:e3:ba:fb:f8` 绑定到 `192.168.5.14`；若启用 macOS 私有 Wi-Fi 地址，网络重连或更换网络时 MAC 可能变化，应在目标网络确认后再绑定。路由器操作完成后重新检查 `ifconfig en0`，并用同一 Wi-Fi 中另一台设备打开内网 URL。若 IP 改变，更新 `PTE_LAN_BIND_IP` 后重启。路由器的客户端隔离、防火墙或访客网络可能阻止互访；不要做公网端口转发。

HTTP Basic 在普通 HTTP 上不加密，因此只在**可信内网**使用。若要通过不可信 Wi-Fi 或互联网访问，应先配置 HTTPS 反向代理或 VPN。当前所有知道密码的访问者共用同一数据库和文件，没有个人数据隔离。

## 2. API key 与 AI 分析开关

使用本机 CLIProxyAPI（当前监听 `http://127.0.0.1:8317/`）时，在项目根目录 `.env` 中填写：

```dotenv
LLM_PROVIDER=openai_compatible
OPENAI_BASE_URL=http://127.0.0.1:8317/v1
OPENAI_ANALYSIS_MODEL=gpt-6-sol
OPENAI_API_KEY=你的CLIProxyAPI访问密钥
```

当前本机 `.env` 已配置 Provider、地址、`gpt-6-sol` 和访问密钥；密钥值仅留在本机。新安装时，从 CLIProxyAPI 配置中取得其服务端允许的 API key，直接填入本地 `.env` 的 `OPENAI_API_KEY=` 后面；不要把密钥发到聊天里，也不要给它加 `VITE_` 前缀。本机已通过 `/v1/models` 确认该模型，并用 `Choices of Lunch` 的真实证据完成一次建议改写；这只验证当前代理配置，不保证将来模型授权持续有效。项目后端与代理在同一台 Mac 上，故应使用 `127.0.0.1`；内网浏览器无需直连 8317。

后端虚拟环境已安装 `backend/requirements-llm.lock` 中的 OpenAI SDK；更换机器时按该文件安装。填好密钥后运行 `./scripts/restart.sh`，比较页会默认勾选 **“使用 CLIProxyAPI 生成双项总结并改写训练建议”**，用户仍可取消。该选择随每次运行单独提交为 `allow_cloud=true`；未配置密钥时自动用本机规则，无需中止分析。代理只接收所需指标、规则结论和少量引用证据，不接收整段录音，也不重新打 PTE 分或生成 benchmark 音频。调用失败、密钥失效或输出校验失败时保留本机总结；报告分别标明建议改写及双项总结的来源。前端只收到“密钥是否已配置”和模型名，看不到密钥。

若改用官方 OpenAI API，把 `LLM_PROVIDER` 设为 `openai`，`OPENAI_BASE_URL` 留空，填写独立的 OpenAI Platform API key 和受支持模型，再重启服务。ChatGPT Plus 订阅不提供该 API key；OpenAI Platform 独立计费。

“新建比较”继续使用用户在项目外生成并上传、且已取得猩际资料的 AI 高分参考录音。独立的“TTS 参考”入口可把核对过的英文朗读稿发送到在线 Microsoft Edge TTS，生成练习录音；只需填写用户侧猩际资料。合成参考没有猩际分数或词色，不称作高分样本。两种入口都支持朗读稿截图 OCR 后编辑。TTS 不使用 `OPENAI_API_KEY`，需要本机能访问外部在线语音服务；不会将用户录音发送给该服务。

## 3. 配置项全集

| `.env` 项 | 当前默认值/示例 | 实际作用 |
|---|---|---|
| `PTE_DATA_DIR` | `./data` | 原始录音、截图、衍生音频、SQLite、模型缓存；相对项目根目录。 |
| `FFMPEG_BIN`, `FFPROBE_BIN` | `ffmpeg`, `ffprobe` | 音频探测与转换，可填可执行文件绝对路径。 |
| `MAX_AUDIO_MB` | `100` | 单个音频上传大小上限。 |
| `MAX_AUDIO_SECONDS` | `120` | 单个音频时长上限。 |
| `PAUSE_MIN_MS` | `250` | 停顿候选最短阈值。 |
| `LONG_PAUSE_MS` | `500` | 长停顿阈值。 |
| `VERY_LONG_PAUSE_MS` | `1000` | 很长停顿阈值。 |
| `CROSS_DIMENSION_WINDOW_MS` | `750` | 红词与长停顿相邻判断窗口；只表示关联假设。 |
| `ALIGNMENT_PROVIDER` | `whisperx` 或 `none` | WhisperX CPU 词级对齐，或禁用。禁用/失败会降级时间相关结论。需先安装 `requirements-alignment.lock`。 |
| `PRONUNCIATION_PROVIDER` | `none` | 保留的全局配置字段；安装 `requirements-pronunciation.lock` 后运行页默认勾选本地 OpenPronounce，可在单次运行中关闭。其音素候选未经校准，首次运行会下载本地模型，可能明显变慢。 |
| `ASR_PROVIDER` | `none` | 预留字段；当前主流程从猩际截图 OCR 实际转写，不运行音频 ASR。 |
| `TTS_ENABLED` | `true` | 开启/关闭独立的 Edge TTS 练习入口；关闭不影响上传参考比较。 |
| `TTS_VOICE` | `en-US-AriaNeural` | TTS 入口默认音色；当前允许 `en-US-AriaNeural`、`en-US-EmmaMultilingualNeural`、`en-GB-RyanNeural`。 |
| `TTS_RATE` | `+0%` | 默认语速；页面可选 -20% 到 +20%，服务端限制 ±50%。 |
| `TTS_GAP_MS` | `300` | 分段接缝的目标最短安静区，已有自然静音足够时不再补零；不是语义停顿评分。 |
| `TTS_TIMEOUT_S` | `90` | 每段在线合成最长等待秒数；失败限次重试后返回可重试错误。 |
| `LLM_PROVIDER` | `openai`；本机为 `openai_compatible` | 选择官方 OpenAI Responses API 或兼容 Chat Completions 服务；每次运行仍需勾选。 |
| `OPENAI_API_KEY` | 空 | 所选服务的后端访问密钥；本机代理使用 CLIProxyAPI 认可的密钥。空值时 AI 勾选不可用。 |
| `OPENAI_ANALYSIS_MODEL` | 空；本机为 `gpt-6-sol` | 所选服务可用的模型 ID；需与 key 一同设置。 |
| `OPENAI_BASE_URL` | 空；本机为 `http://127.0.0.1:8317/v1` | 仅兼容服务使用；允许本机 HTTP 或 HTTPS，自动补 `/v1`。不填时兼容 Provider 不可用。 |
| `PTE_LAN_MODE` | `false` | `true` 时内网服务要求密码并提供构建后的网页；开发脚本强制关闭。 |
| `PTE_LAN_BIND_IP` | `127.0.0.1`；本机配置 `192.168.5.14` | 监听的本机私有 IPv4；不允许公网地址或 `0.0.0.0`。 |
| `PTE_LAN_PORT` | `8765` | 内网服务端口。 |
| `PTE_LAN_USERNAME` | `pte` | 浏览器内网登录用户名。 |
| `PTE_LAN_PASSWORD` | 空；本机已生成 | 内网密码，至少 16 字符；空或过短时内网服务拒绝启动。 |

Anthropic、Gemini、Ollama/LM Studio 的专用适配器及本地 ASR/LLM 仍未实现；仅通用 OpenAI-compatible Chat Completions 路径可用于 CLIProxyAPI 等兼容服务。

音高与能量曲线当前默认生成，无额外 `.env` 开关：依赖基础环境中的 `numpy`，每侧最多 2400 点、子进程限时 20 秒。它是可折叠的回听辅助，不参与评分；处理失败会在曲线区显示原因，其余分析继续。流利度表格里的“无法判断”取决于录音的 VAD、词级对齐或是否有逐字口误数据，**配置 API key 不会补出缺失测量**。

## 4. 数据与安全操作

- SQLite：`data/db/pte.sqlite3`；原始录音和截图在 `data/audio/original/`、`data/screenshots/`，衍生 WAV 在 `data/audio/derived/`。路径在库中保持相对形式。
- 两侧截图原图、OCR 草稿、可选复制转写、最终编辑稿、分数和词色状态分别保存；`candidate` 颜色默认参与首次分析并标低可信度，人工修正后变为 `confirmed`。编辑样本产生新 revision，旧分析报告仍引用旧 revision。共同朗读原文及其可选截图、OCR 草稿保存在 Exercise 中。
- 内网访问者可查看和删除同一项目的比较记录。开始让其他人使用前，应备份 `data/`。当前没有细粒度权限或审计账号。
- 修改阈值只影响**之后**的新分析运行；旧报告保留运行时配置。修改共同朗读原文的编辑界面尚未提供，新比较时请确认输入。
- 要验证当前服务：打开 `http://192.168.5.14:8765`，输入 `.env` 中的用户名/密码。API 健康页是 `/api/v1/health`，不会展示密钥值。
