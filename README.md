# PTE Speaking Lab

PTE 口语练习对比工具。输入共同朗读原文、用户真人录音和已生成的 AI 高分参考录音；两侧各自提供猩际逐词颜色截图及 Pronunciation、Fluency、Content 分数。截图优先识别实际转写和词色，复制的猩际转写可选。项目独立分析发音与流利度；Content 只保存并展示猩际分数。AI benchmark 是参考样本，不是标准答案。可在本机开发或通过带密码的可信内网访问。

## 首次安装（Apple Silicon Mac）

系统工具优先通过 Homebrew 安装：

```bash
brew install python@3.11 node ffmpeg tesseract
```

在项目根目录安装 Python 与前端依赖：

```bash
/opt/homebrew/bin/python3.11 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.lock
backend/.venv/bin/python -m pip install -r backend/requirements-alignment.lock
npm ci --prefix frontend
cp .env.example .env
```

`WhisperX` 对齐模型首次使用时需要下载；后续模型缓存位于 `data/models/`。CPU 对齐已在 MacBook Air M2 24 GB 上用真实双边录音验证。若暂不安装对齐依赖，在 `.env` 设 `ALIGNMENT_PROVIDER=none`，应用仍能运行，依赖词时间戳的分析会降级。

以下依赖按需安装。OpenPronounce 只提供未经校准的本地音素候选，不会调用其默认 gTTS 参考语音路径；OpenAI 用于可选的训练建议改写：

```bash
backend/.venv/bin/python -m pip install -r backend/requirements-pronunciation.lock
backend/.venv/bin/python -m pip install -r backend/requirements-llm.lock
```

## 启动与使用

```bash
./scripts/dev.sh
```

打开 <http://127.0.0.1:5173>。健康检查为 <http://127.0.0.1:8000/api/v1/health>。按 `Ctrl+C` 停止前后端。启动器使用本机端口 5173 和 8000，检测端口冲突；开发服务器会自动重载代码。

1. 在“新建比较”粘贴完整共同朗读稿，或上传/粘贴其英文朗读稿截图并修改识别文字；DI 图表不能代替朗读稿。上传两侧录音，上传或粘贴两侧猩际逐词颜色截图，系统分别识别实际转写和词色，填写三项分数。复制的猩际转写可选，提供时用来对照差异。
2. 提交前检查并可编辑三处 OCR 文字。两侧截图候选颜色默认参与第一次分析，并显示较低可信度；未知词用红色感叹号提示。可在原图旁逐词修正或确认。当前已验证浅色整页猩际截图；截图中的停顿标签尚未得到可靠映射。
3. 运行分析，查看独立的发音和流利度证据、共享词 A/B、双边波形与训练建议。可重复运行并切换历史报告。比较可预览后删除；共享文件会保留。

分析缺失可靠时间戳、语音活动区间或逐词颜色时会标记为部分完成。词速、停顿等指标会显示测量质量；重复、false starts、fillers 在猩际转写可能省略口误时显示“无法判断”。发音模型候选不能当作猩际或官方 PTE 评分。

## 可选 AI 文案改写

官方 OpenAI 和本机 CLIProxyAPI 都可改写有证据约束的训练建议。在项目根目录 `.env` 填写 Provider、`OPENAI_API_KEY`、`OPENAI_ANALYSIS_MODEL`；CLIProxyAPI 还需 `OPENAI_BASE_URL=http://127.0.0.1:8317/v1`。安装 `backend/requirements-llm.lock`，重启服务后，在具体分析前显式勾选 AI 改写。未勾选或未配置时仍运行本机测量与规则建议。密钥只由后端读取，不进入网页或报告；详细步骤见 [CONFIGURATION.md](docs/CONFIGURATION.md)。

## 内网访问

先运行 `npm run build --prefix frontend`，再使用 `./scripts/start.sh` 后台启动；`./scripts/stop.sh` 停止，`./scripts/restart.sh` 重启。三个脚本都管理 `.env` 中配置的内网地址与端口，服务日志在 `data/logs/lan.log`。`./scripts/serve_lan.sh` 仍可用于前台运行。当前入口为 <http://192.168.5.14:8765>，浏览器会要求用户名和密码；用户名为 `pte`，随机生成的密码位于项目根目录 `.env` 的 `PTE_LAN_PASSWORD`。要长期固定地址，需要在路由器中保留 DHCP 地址。详细配置、安全边界及排查步骤见 [CONFIGURATION.md](docs/CONFIGURATION.md)。

## 本地数据、迁移与测试

`.env`、`data/`、`测试数据包/`、依赖目录和构建产物被 Git 忽略。原始录音与截图完整保存；SQLite 在 `data/db/pte.sqlite3`。分析运行锁定双边不可变样本版本。迁移至 M5 Pro 时复制项目和 `data/`，在新机器重装同版依赖并配置 `.env`；数据库使用相对文件路径，不依赖原机器位置。

```bash
backend/.venv/bin/python -m pytest backend/tests -q
npm run build --prefix frontend
```

真实样本验证、耗时、内存与已知限制见 [MVP_ACCEPTANCE.md](docs/MVP_ACCEPTANCE.md) 和 [progress.md](progress.md)。完整文件说明见 [ASSET_INVENTORY.md](ASSET_INVENTORY.md)。产品范围见 [PROJECT_SPEC.md](PROJECT_SPEC.md)，当前具体实现见 [TECHNICAL_ARCHITECTURE.md](docs/TECHNICAL_ARCHITECTURE.md)，设计蓝图见 [ARCHITECTURE.md](ARCHITECTURE.md)。
