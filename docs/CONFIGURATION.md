# PTE Speaking Lab 配置与内网使用

**本文件对应当前可运行代码。** 项目根目录为 `/Users/alex/codex_project/PTE口语诊断分析/`。配置文件是根目录 `.env`，示例为 [`.env.example`](../.env.example)。更改 `.env` 后重启服务。不要把真实密钥、密码或录音提交到 Git。

## 1. 两种启动方式

| 模式 | 命令 | 地址 | 用途 |
|---|---|---|---|
| 本机开发 | `./scripts/dev.sh` | `http://127.0.0.1:5173` | Vite 热更新，后端在 8000；脚本强制关闭 LAN 模式。 |
| 内网使用 | `npm run build --prefix frontend`，然后 `./scripts/start.sh` | `http://192.168.5.14:8765`（当前配置） | FastAPI 同源提供网页、API 和录音；HTTP Basic 密码保护，无热更新。 |

`./scripts/start.sh` 后台启动，`./scripts/stop.sh` 停止，`./scripts/restart.sh` 重启；服务由 macOS `launchd` 托管，命令结束后仍运行。需要前台查看日志时可运行 `./scripts/serve_lan.sh`。Mac 休眠或退出服务后其他设备无法访问。浏览器会弹出登录框，用户名默认为 `pte`，密码在项目根目录 `.env` 的 `PTE_LAN_PASSWORD`。此密码已随机生成；不要发送完整 `.env` 给别人。给他人密码时应采用可信渠道。

当前 Mac 的 `en0` 地址是 `192.168.5.14/24`；该地址已用于启动服务并通过本机地址测试。**“当前地址”尚不等于永久固定地址。** 在路由器的 DHCP 地址保留/静态租约界面，将这台 Mac 的当前 Wi-Fi MAC `5a:34:e3:ba:fb:f8` 绑定到 `192.168.5.14`；若启用 macOS 私有 Wi-Fi 地址，网络重连或更换网络时 MAC 可能变化，应在目标网络确认后再绑定。路由器操作完成后重新检查 `ifconfig en0`，并用同一 Wi-Fi 中另一台设备打开内网 URL。若 IP 改变，更新 `PTE_LAN_BIND_IP` 后重启。路由器的客户端隔离、防火墙或访客网络可能阻止互访；不要做公网端口转发。

HTTP Basic 在普通 HTTP 上不加密，因此只在**可信内网**使用。若要通过不可信 Wi-Fi 或互联网访问，应先配置 HTTPS 反向代理或 VPN。当前所有知道密码的访问者共用同一数据库和文件，没有个人数据隔离。

## 2. API key 与 AI 分析开关

在项目根目录 `.env` 中填写：

```dotenv
OPENAI_API_KEY=你的独立OpenAI_API密钥
OPENAI_ANALYSIS_MODEL=你有权限使用的模型名
```

然后按需安装 `backend/requirements-llm.lock`，重启服务，在具体比较页面勾选 **“允许 OpenAI 改写训练建议”** 再点击“开始分析”。这项选择随每次运行单独提交为 `allow_cloud=true`；默认不调用 OpenAI。OpenAI 仅接收规则诊断所需的证据和结论，用于文字改写，不重新打 PTE 分，也不生成 benchmark 音频。云端调用失败会回退本机规则建议。ChatGPT Plus 订阅不提供 OpenAI API key；API 按 OpenAI Platform 独立计费。前端只能读取“是否已配置”和模型名，看不到 key。不要给 key 添加 `VITE_` 前缀。

当前 AI 高分录音必须**由用户在项目外先生成并上传**，随后分别填写其猩际 PTE 三项分数和逐词截图。截图自动识别实际转写，复制文本可选；提交前可编辑 OCR 结果。共同朗读稿可直接输入，或上传/粘贴完整英文朗读稿截图后编辑文字。项目没有内置语音合成。

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
| `LLM_PROVIDER` | `openai` | 预留 provider 名；当前真正的云端调用由每次运行的勾选决定，仅实现 OpenAI。 |
| `OPENAI_API_KEY` | 空 | 后端 OpenAI API 密钥；空值时云端勾选不可用。 |
| `OPENAI_ANALYSIS_MODEL` | 空 | API 模型名；与 key 同时设置后才可勾选。 |
| `PTE_LAN_MODE` | `false` | `true` 时内网服务要求密码并提供构建后的网页；开发脚本强制关闭。 |
| `PTE_LAN_BIND_IP` | `127.0.0.1`；本机配置 `192.168.5.14` | 监听的本机私有 IPv4；不允许公网地址或 `0.0.0.0`。 |
| `PTE_LAN_PORT` | `8765` | 内网服务端口。 |
| `PTE_LAN_USERNAME` | `pte` | 浏览器内网登录用户名。 |
| `PTE_LAN_PASSWORD` | 空；本机已生成 | 内网密码，至少 16 字符；空或过短时内网服务拒绝启动。 |

Anthropic、Gemini、OpenAI-compatible、Ollama/LM Studio、本地 ASR/本地 LLM 目前是扩展方向，**当前代码未实现这些 provider**，不要把名称写入 `.env` 期待生效。

## 4. 数据与安全操作

- SQLite：`data/db/pte.sqlite3`；原始录音和截图在 `data/audio/original/`、`data/screenshots/`，衍生 WAV 在 `data/audio/derived/`。路径在库中保持相对形式。
- 两侧截图原图、OCR 草稿、可选复制转写、最终编辑稿、分数和词色状态分别保存；`candidate` 颜色默认参与首次分析并标低可信度，人工修正后变为 `confirmed`。编辑样本产生新 revision，旧分析报告仍引用旧 revision。共同朗读原文及其可选截图、OCR 草稿保存在 Exercise 中。
- 内网访问者可查看和删除同一项目的比较记录。开始让其他人使用前，应备份 `data/`。当前没有细粒度权限或审计账号。
- 修改阈值只影响**之后**的新分析运行；旧报告保留运行时配置。修改共同朗读原文的编辑界面尚未提供，新比较时请确认输入。
- 要验证当前服务：打开 `http://192.168.5.14:8765`，输入 `.env` 中的用户名/密码。API 健康页是 `/api/v1/health`，不会展示密钥值。
