# PTE Speaking Lab 项目资产清单

更新：2026-09-27。本清单覆盖项目维护的源码、配置、脚本、文档和测试文件。`data/`、`测试数据包/`、`.env`、虚拟环境、`node_modules/`、`frontend/dist/` 属于本地运行或私人数据，目录用途见末尾，不逐项公开内部文件名。以下路径均相对项目根目录。

## 文件夹与模块

| 文件夹 | 职责 |
|---|---|
| `backend/app/api/` | FastAPI 的 HTTP 输入、输出和参数校验。 |
| `backend/app/domain/` | 双边样本、分数、词色和修订输入的数据契约。 |
| `backend/app/screenshots/` | 截图 OCR、正文区域选择、词序匹配和颜色分类。 |
| `backend/app/audio/` | 音频原件验证、转换、语音活动与逐词对齐。 |
| `backend/app/engines/` | 发音、流利度两个独立引擎及交叉维度诊断。 |
| `backend/app/comparison/` | 共同朗读稿覆盖、共享词与双边指标比较。 |
| `backend/app/analysis/` | 分析运行编排、不可变输入快照和报告持久化。 |
| `backend/app/providers/` | 可选官方 OpenAI、CLIProxyAPI 文案改写，OpenPronounce 音素候选，以及 Edge TTS 在线参考录音适配器。 |
| `backend/app/persistence/` | SQLite 连接、迁移、样本修订和删除清理。 |
| `backend/tests/` | 后端单元、API、退化行为与内网保护测试。 |
| `frontend/src/api/` | 浏览器与后端 API 的请求及 TypeScript 类型。 |
| `frontend/src/components/` | 跨页面可复用的界面组件。 |
| `frontend/src/pages/` | 新建输入、比较详情、报告和设置页面。 |
| `scripts/` | 开发、内网启动/停止/重启与本地样本导入工具。 |
| `docs/` | 当前配置、实现原理、可行性及验收记录。 |

## 项目根目录

| 文件 | 功能 |
|---|---|
| `.env.example` | 可复制的后端配置模板；实际密钥和内网密码填在被 Git 忽略的 `.env`。 |
| `.gitignore` | 排除密钥、录音、截图、数据库、测试数据、依赖和构建产物。 |
| `AGENTS.md` | 后续开发代理的产品边界、截图候选规则和验证约束。 |
| `ARCHITECTURE.md` | 项目架构蓝图、领域与数据结构、API/Provider 设计。 |
| `ASSET_INVENTORY.md` | 本文件，逐一说明项目资产。 |
| `PROJECT_SPEC.md` | 产品目标、双边输入、分析范围、验收标准与后续阶段。 |
| `README.md` | 首次安装、启动、使用、内网访问和测试入口。 |
| `TASKS.md` | 开发任务分解与实施顺序记录。 |
| `progress.md` | 已完成修改、实测结果及仍存在的限制。 |

## 后端核心文件

| 文件 | 功能 |
|---|---|
| `backend/pyproject.toml` | Python 包元数据、基础依赖和 pytest 设置。 |
| `backend/requirements.lock` | 基础后端依赖锁定版本。 |
| `backend/requirements-alignment.lock` | 可选 WhisperX 词级对齐依赖版本。 |
| `backend/requirements-pronunciation.lock` | 可选 OpenPronounce 依赖版本。 |
| `backend/requirements-llm.lock` | 可选 OpenAI API 客户端依赖版本。 |
| `backend/app/main.py` | 创建 FastAPI 应用、注册路由、迁移数据库、提供带密码的内网网页。 |
| `backend/app/config.py` | 读取 `.env`，验证内网绑定地址并提供数据路径与运行阈值。 |
| `backend/app/api/assets.py` | 上传、校验和读取音频与截图，计算文件哈希并保存相对路径。 |
| `backend/app/api/comparisons.py` | 新建/读取/删除比较、样本修订、截图 OCR 预览与导入草稿。 |
| `backend/app/api/health.py` | 服务健康检查。 |
| `backend/app/api/runs.py` | 启动分析、读取状态/报告、回听音频及查询 Provider 可用性。 |
| `backend/app/api/tts.py` | TTS 设置、朗读稿断句预览、在线生成接口。 |
| `backend/app/domain/schemas.py` | Pydantic 输入模型；验证双边角色、分数、词序与候选来源。 |
| `backend/app/screenshots/mapper.py` | Tesseract OCR、彩色正文提取、逐词颜色检测及保守顺序映射。 |
| `backend/app/audio/prepare.py` | 音频哈希验证、FFmpeg 标准化和语音活动区间提取。 |
| `backend/app/audio/acoustics.py` | 从衍生 WAV 限时提取音高估计与 RMS 能量展示曲线；失败不阻断主分析。 |
| `backend/app/audio/alignment.py` | 对齐 Provider、WhisperX 适配、时间戳质量及无对齐退化。 |
| `backend/app/engines/common.py` | 指标、证据对象及可序列化结果的共同构造函数。 |
| `backend/app/engines/pronunciation.py` | 发音词色统计、红黄词优先级、截图候选证据与可选音素线索。 |
| `backend/app/engines/fluency.py` | 独立计算词速、停顿、短语、语音占比和语速稳定性。 |
| `backend/app/engines/diagnosis.py` | 在两个引擎完成后生成有证据引用的训练建议。 |
| `backend/app/engines/report_summaries.py` | 用本次指标、红黄词和停顿生成双项中文总结，并校验可选 AI 改写。 |
| `backend/app/comparison/service.py` | 共同原文词位覆盖、共享词 A/B、双边流利度差值。 |
| `backend/app/analysis/runner.py` | 锁定样本版本，运行音频/双引擎/比较/诊断并保存不可变报告。 |
| `backend/app/providers/openai_llm.py` | 可选官方 OpenAI 和 CLIProxyAPI 兼容接口文案改写；解析返回结构，证据 ID 在诊断层校验。 |
| `backend/app/providers/openpronounce.py` | 本地音素候选；只处理可定位的目标词，不生成评分。 |
| `backend/app/providers/edge_tts.py` | 分段请求在线 Edge TTS、保留词边界、解码拼接 WAV、记录接缝及缓存。 |
| `backend/app/persistence/database.py` | SQLite 连接及按版本执行迁移。 |
| `backend/app/persistence/samples.py` | 创建双边样本、验证资产、保存可编辑视图和不可变修订。 |
| `backend/app/persistence/deletion.py` | 删除比较及专属文件，保留仍被其他比较引用的资产。 |
| `backend/app/analysis/__init__.py` | 标记分析编排包。 |
| `backend/app/audio/__init__.py` | 标记音频处理包。 |
| `backend/app/comparison/__init__.py` | 标记双边比较包。 |
| `backend/app/domain/__init__.py` | 标记领域模型包。 |
| `backend/app/engines/__init__.py` | 标记分析引擎包。 |
| `backend/app/persistence/__init__.py` | 标记持久化包。 |
| `backend/app/providers/__init__.py` | 标记可选 Provider 包。 |
| `backend/app/screenshots/__init__.py` | 标记截图处理包。 |

## 数据库迁移

| 文件 | 功能 |
|---|---|
| `backend/app/persistence/migrations/0001_foundation.sql` | 建立应用元信息与迁移基础。 |
| `backend/app/persistence/migrations/0002_samples.sql` | 建立题目、音频/截图资产、双边样本、词与修订表。 |
| `backend/app/persistence/migrations/0003_analysis.sql` | 建立分析运行、指标、证据、发现与报告表。 |
| `backend/app/persistence/migrations/0004_shared_reading_text.sql` | 给 Exercise 增加共同朗读原文。 |
| `backend/app/persistence/migrations/0005_screenshot_reading.sql` | 关联朗读稿截图/OCR 来源，并使词色支持 `candidate` 状态。 |
| `backend/app/persistence/migrations/0006_repair_candidate_colors.sql` | 修复旧数据库未真正更新的词色约束，保留已有词记录。 |
| `backend/app/persistence/migrations/0007_tts_generations.sql` | 保存 TTS 生成脚本、词时间、接缝、版本与音频资产关联。 |

## 后端测试

| 文件 | 覆盖内容 |
|---|---|
| `backend/tests/test_audio.py` | 音频校验、标准化、VAD 与对齐退化。 |
| `backend/tests/test_acoustics.py` | 已知音高信号、静音和超时的曲线降级。 |
| `backend/tests/test_comparison_diagnosis.py` | 共享词比较、原文位置与跨维度诊断证据。 |
| `backend/tests/test_engines.py` | 独立发音/流利度指标和不可用情形。 |
| `backend/tests/test_health.py` | 启动、健康检查与配置。 |
| `backend/tests/test_lan.py` | 内网页面和 API 的密码保护。 |
| `backend/tests/test_runs.py` | 分析运行、候选词色、云端配置与历史报告不可变。 |
| `backend/tests/test_report_summaries.py` | 本次数据专属总结及 AI 数字越界/调用失败回退。 |
| `backend/tests/test_llm_provider.py` | CLIProxyAPI 兼容请求路径、JSON 解析与地址校验。 |
| `backend/tests/test_samples.py` | 双边资产、样本修订、数据校验、旧词色表迁移与共享文件删除。 |
| `backend/tests/test_screenshot_mapping.py` | OCR 词序、重复词、低置信度与页眉排除。 |
| `backend/tests/test_tts.py` | TTS 断句、接缝时间偏移、缓存、停顿排除及不可信词边界。 |

## 前端文件

| 文件 | 功能 |
|---|---|
| `frontend/index.html` | Vite 页面入口 HTML。 |
| `frontend/package.json` | 前端依赖及开发、构建命令。 |
| `frontend/package-lock.json` | 前端依赖锁定版本。 |
| `frontend/tsconfig.json` | TypeScript 编译与类型校验设置。 |
| `frontend/vite.config.ts` | Vite 构建和本机开发 API 代理。 |
| `frontend/src/main.tsx` | 挂载 React 根组件与全局样式。 |
| `frontend/src/App.tsx` | 应用外壳、导航及页面路由。 |
| `frontend/src/style.css` | Tailwind 样式入口和共享表单/按钮样式。 |
| `frontend/src/api/client.ts` | API 请求、错误处理和前后端数据类型。 |
| `frontend/src/components/Waveform.tsx` | 音频波形、播放、证据位置跳转，以及同一页面内的互斥播放。 |
| `frontend/src/components/AcousticPlot.tsx` | 可折叠的双边音高/能量曲线与相邻位置回听。 |
| `frontend/src/pages/NewComparison.tsx` | 截图粘贴/选择、OCR 预览编辑、双边表单和词色复核。 |
| `frontend/src/pages/NewTTSComparison.tsx` | 独立 TTS 入口：朗读稿、断句和音色选择、用户侧资料、生成并保存比较。 |
| `frontend/src/pages/ComparisonDetail.tsx` | 比较运行选项、Provider 状态、历史报告、删除与复核入口。 |
| `frontend/src/pages/ReportView.tsx` | 双边报告、紧邻时间轴的播放器、实际方法与缺失原因说明、数据专属总结、共享词、红黄词上下文和整段 WAV 定位回听。 |
| `frontend/src/pages/Settings.tsx` | 配置状态和用户可见的设置说明。 |

## 脚本和文档

| 文件 | 功能 |
|---|---|
| `scripts/dev.py` | 同时启动本机开发后端与 Vite，并处理退出。 |
| `scripts/dev.sh` | 本机开发启动快捷入口。 |
| `scripts/serve_lan.py` | 根据 `.env` 在私有内网地址提供单端口网页和 API。 |
| `scripts/serve_lan.sh` | 前台运行内网服务的兼容入口。 |
| `scripts/start.sh` | 后台启动并检查内网服务，记录 PID 和本地日志。 |
| `scripts/stop.sh` | 停止 launchd 内网服务并等待注销；兼容验证 PID 后停止旧式前台服务。 |
| `scripts/restart.sh` | 顺序停止、启动内网服务。 |
| `scripts/import_test_bundle.py` | 把私人的双边测试数据导入本机数据库。 |
| `scripts/t00_screenshot_probe.py` | T00 阶段的截图识别可行性探针。 |
| `docs/CONFIGURATION.md` | API key、开关、阈值、内网地址与数据目录说明。 |
| `docs/TECHNICAL_ARCHITECTURE.md` | 当前代码的数据流、模块实现和降级机制。 |
| `docs/T00_FEASIBILITY.md` | 原始真实截图 OCR 和本机模型验证记录。 |
| `docs/MVP_ACCEPTANCE.md` | MVP 双边真实样本验收记录。 |
| `docs/RELEASE_1.0_TO_v1.99.md` | 从 `1.0` 基线到 `v1.99` 的功能、迁移、验证和限制汇总。 |
| `docs/M5_LOCAL_AUDIO_DEPLOYMENT_PLAN.md` | M5 Pro 内网音频计算节点的分阶段部署方案。 |
| `docs/EXTERNAL_SPEECH_DIAGNOSIS_REVIEW.md` | 外部口语诊断源码的功能审查、Edge TTS 路径及与本项目的技术选型对比。 |
| `docs/TTS_COMPARISON.md` | TTS 参考模式的数据流、边界、实测与维护说明。 |

## 本地运行目录

| 路径 | 用途 |
|---|---|
| `.env` | 本机 API key、内网密码和运行配置；不提交。 |
| `data/db/` | SQLite 数据库。 |
| `data/audio/original/`、`data/audio/derived/` | 原始录音与可重建的标准化 WAV。 |
| `data/screenshots/original/` | 上传或粘贴的原始截图。 |
| `data/models/` | 本地对齐模型缓存。 |
| `data/run/`、`data/logs/` | 内网启动 PID 与服务日志。 |
| `测试数据包/` | 私人的真实双边录音、截图和参考文本。 |
| `backend/.venv/`、`frontend/node_modules/` | Python/JavaScript 安装依赖。 |
| `frontend/dist/` | 生产前端构建，由内网服务提供。 |
