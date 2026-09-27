# PTE Speaking Lab：当前实现的技术架构与处理原理

此文描述**现在的代码行为**。产品目标与后续扩展见 [PROJECT_SPEC.md](../PROJECT_SPEC.md) 和 [ARCHITECTURE.md](../ARCHITECTURE.md)；运行与配置见 [CONFIGURATION.md](CONFIGURATION.md)。

## 1. 系统边界与实际输入

前端为 React + Vite + Tailwind + WaveSurfer；后端为 FastAPI；SQLite 保存结构化记录，filesystem 保存音频和截图；FFmpeg 做音频转换。本机开发是 Vite 5173 代理 API 8000。内网部署先构建前端，FastAPI 在单一 8765 端口同源提供网页/API/录音，并用 HTTP Basic 覆盖所有路径。`scripts/start.sh`、`stop.sh`、`restart.sh` 通过 macOS `launchd` 管理服务；plist、PID 与日志位于 Git 忽略的 `data/`。

`Comparison` 由一个 `Exercise` 与两个 `ResponseSample` 组成。Exercise 的 `reading_text_raw` 是**共同计划朗读的原文**；可从完整英文朗读稿截图 OCR 后编辑，原图与 OCR 草稿分别保存。user 样本是人的录音；benchmark 样本可以是用户上传且附带猩际资料的**已生成 AI 高分参考录音**，也可以是从核对后朗读稿在线生成的 **Edge TTS 练习参考**。上传模式两侧分别保存猩际截图、OCR/编辑稿、可选复制稿、三项分数和词色。TTS 参考侧没有这些猩际数据，只保存生成脚本、WAV、词时间与接缝。两种参考都不是标准发音，Content 只存外部分数。

## 2. 一次比较的具体处理过程

### TTS 参考支路

`frontend/src/pages/NewTTSComparison.tsx` 复用上传模式的朗读稿截图输入和用户样本表单，调用 `GET /api/v1/tts/settings` 查询可用音色、`POST /api/v1/tts/segments` 预览可编辑断句，最后调用 `POST /api/v1/tts/generations`。后端 `providers/edge_tts.py` 对每段请求在线音频和 WordBoundary，FFmpeg 解码至 24 kHz 单声道 PCM，按实际采样长度累积全局时间。分段接缝若已有自然安静区达到 `TTS_GAP_MS`，就不补零；每处接缝都记录以便流利度排除。脚本、分段、音色、语速、词事件、接缝、provider 版本及生成 WAV 由迁移 0007 的 `tts_generations` 和 `audio_assets` 保存，缓存键含所有生成参数。

`analysis/runner.py` 在 TTS 侧调用 `audio/alignment.py::tts_word_boundaries`：只对与最终脚本同词、同顺序的 WordBoundary 提供可回听位置，识别不符或缺失的词降级。**这不是独立 ASR，也没有 TTS 侧猩际逐词色或分数。**用户侧仍走现有对齐流程。`engines/fluency.py` 排除接缝附近的停顿，保留整体 WPM 并标示其含合成段间时间、质量较低。上传模式的分析路径与旧报告 JSON 均不改写。生成接口为同步请求，页面有等待/可重试状态；当前没有后台队列或中断续传。

```text
浏览器上传两侧音频/截图 → 资产 ID + SHA-256 + 相对路径
填写共同原文、两侧猩际转写和分数 → Exercise + 两个 ResponseSample
截图 OCR 识别正文词序与像素颜色 → 提交前编辑文字、必要时按顺序重新映射 → `candidate` 进入首轮分析
用户对照原图人工修改或确认 → `confirmed` 写入新的不可变 revision
开始分析 → 锁定两侧 revision + 运行配置
两侧各自：原始文件校验 → FFmpeg 16 kHz 单声道 PCM → WebRTC VAD
                    ↘ WhisperX 词时间对齐（可降级）
                    ↘ Pronunciation Engine
                    ↘ Fluency Engine
双边 Comparison → Diagnosis Engine → 证据/指标/报告持久化 → 网页展示
```

### 2.1 导入与截图映射

`backend/app/api/assets.py` 接收上传；`persistence/samples.py` 持久化两侧输入和分数。截图经 Tesseract 提取词框，选择最大连续彩色英文正文区域以剔除页眉/分数，再按像素分类红、黄、绿。`POST /screenshots/{id}/preview` 返回 OCR 转写草稿及词色候选；文字经用户编辑后可按顺序重新映射，重复词歧义保持 `unknown`。截图原图、OCR 草稿、可选复制稿、最终稿及来源均保存；`candidate` 词色以低可信度参与首轮分析，`confirmed` 为人工复核后状态。截图停顿符号目前不能可靠读取，因此停顿标签为空时表示“不可用”，不能当作 0 次停顿。

### 2.2 音频与共享测量

`audio/prepare.py` 先复核原始音频 SHA-256，再用 FFmpeg 生成 16 kHz/单声道/16-bit PCM WAV；衍生文件可重建。WebRTC VAD 使用 30 ms 帧得到发声区间候选，桥接小于 120 ms 的间隔，质量不足则降级。WhisperX 可按**每侧自己的猩际转写**在 CPU 上做词时间对齐；词数/顺序不一致、分数或时间边界不可信时，不把位置标成可靠。关闭对齐时词时间戳为空。

预处理后的 WAV、发声区间、转写 token、词时间戳是两个诊断引擎的共同输入；Pronunciation 与 Fluency 之间不交换评分或推断结果。

### 2.3 Pronunciation Engine

`engines/pronunciation.py` 分别保留 `candidate`、`confirmed` 来源，统计两种状态的红/黄/绿词并单列未知数；截图候选证据质量为低。按红词优先、黄词其次选至多 12 个重点词；有可靠词时间戳时提供回听片段。安装 OpenPronounce 后运行页默认勾选，可关闭；它生成未经校准的音素模型候选，失败不丢弃其余分析，也不会把模型输出转换成猩际/PTE 分数。

### 2.4 Fluency Engine

`engines/fluency.py` 独立计算 WPM、voiced WPM、停顿数、长/很长停顿数、平均/最大停顿、语音/静音比、发声占比、平均短语时长/词数与局部语速变异系数。优先使用可靠 VAD 发声区间；必要时以可靠相邻词时间差形成低质量停顿候选。缺可靠时间窗时相应值为 `null`、质量 `unavailable`，不把未知写成 0。重复、false starts、fillers 因猩际转写可能删掉口误，当前固定标为不可用。阈值见配置文档；这些指标不是猩际 Fluency 的复刻评分。

### 2.5 双边比较和诊断

`comparison/service.py` 先用共同原文分别与两侧实际转写做顺序 LCS 匹配，只有映射到**同一原文位置**且两侧相同的实际词才进入共享词 A/B。颜色差异不参与选配。它同时给出每侧匹配原文词数、转写未匹配词数、共同位置数、原文尾部未见于转写的词数。旧记录没有共同原文时，仅在两侧实际转写之间按顺序配对同形词。重复词和省略仍可能产生不唯一的顺序匹配，报告中的配对需结合原文与音频核查。转写不一致可由朗读、猩际识别或录音截断造成，系统**不自动归因于发音问题**。

流利度各指标用同一算法与阈值分别测量，展示两侧原值、差值与质量；缺失值在表格中统一显示“无法判断”，表格上方说明常见原因及配置条件，下方以中文总结有效指标。两侧词数/尾部可能不同，速度差不是目标分数。发音侧另比较词色总体分布。报告页将证据时间轴放在双边样本之后，并用固定在视口上缘的页内锚点入口直达。时间轴默认聚焦用户红黄词，显示前后各三个词；AI 同词上下文只从 `shared_word_pairs` 的位置配对取得。每侧提供较长上下文回听和目标词加相邻各一词的短片段回听；短片段仅使用有可靠时间戳的邻词，目标词时间不可靠时禁用。用户可切换到全部可定位证据，按录音时间排列，仅给用户红词和黄词条目加对应底色，不截断尾部；无时间戳的证据单独计数说明。聚焦视图只减少前端 DOM 渲染，不重新运行模型，也不改变两侧波形音频加载。两侧波形播放器在页面内共享播放焦点，播放或证据回听时先暂停另一侧。

`engines/diagnosis.py` 在两个独立引擎之后运行，以有证据 ID 的红词、长停顿、局部语速波动生成最多三项建议；红词附近的停顿只表述为相关假设。可选 LLM 只改写这些规则建议，返回的 finding ID、证据 ID 及原文数字必须保持一致，否则整份改写回退原规则。新报告同时保存 `rule_findings` 与最终文字；网页显示真实 Provider 名称、改写/未改写/回退状态，并可展开查看改写前的本机建议。旧报告不追填原文。Content 不进入诊断。

## 3. 数据库、版本与接口

SQLite 迁移位于 `backend/app/persistence/migrations/`：0001 建立资产基础表；0002 建立 exercises、response_samples、external_scores、sample_tokens、pause_labels、sample_revisions、comparisons、screenshot_imports；0003 建立 analysis_runs、timed_tokens、metrics、evidence、findings、finding_evidence、comparisons_result；0004 为 exercises 加入 `reading_text_raw`；0005 加入朗读稿截图/OCR 来源及 `candidate` 词色状态；0006 修复已登记 0005、但词色表仍保留旧约束的数据库，同时复制已有词记录。每次修改样本产生新 revision；每次分析运行绑定两侧 revision ID、算法版本及关键阈值。旧报告存完整 JSON，不被输入更正覆盖。AI 录音来源 `audio_origin` 保存在样本 revision JSON 中；旧记录缺字段视为 `legacy_unspecified`。

API 前缀 `/api/v1`：资产上传/读取；`POST /comparisons`、`GET /comparisons/{id}`、`PATCH /samples/{id}`、截图导入、历史/删除预览/删除；`POST /comparisons/{id}/runs`、`GET /runs/{id}/report`、录音回听；`GET /health` 与 `GET /settings/providers`。写入采用样本版本冲突检查；分析已运行时不并发启动同一 Comparison。输出的 evidence 含维度、来源、位置、质量、算法版本；finding 引用 evidence ID。API key 和内网密码不进入响应、SQLite、日志或 Git。

## 4. Provider 与故障降级

已实现的选择：`ALIGNMENT_PROVIDER=whisperx|none`；OpenPronounce 由每次运行开关控制；LLM 可选 `openai`（官方 Responses API）或 `openai_compatible`（Chat Completions API，供 CLIProxyAPI 使用）。两者都需要后端 key、模型和本次 `allow_cloud` 勾选；兼容接口还需要 `OPENAI_BASE_URL`。适配器将规则 finding 与必要证据打包，要求 JSON 对象，再用 Pydantic 解析；Diagnosis Engine 对 finding/evidence ID 做最终校验。兼容接口允许本机 HTTP，远程仅允许 HTTPS；密钥不保存到报告。缺对齐模型或对齐失败时使用 `NoAlignment`，并将依赖位置的指标标为不可用。OpenPronounce 失败只影响该词候选。LLM 失败回退规则。Anthropic、Gemini、Ollama/LM Studio 专用适配器和本地 ASR/LLM 仍是预留方向。

## 5. 内网部署边界

`scripts/serve_lan.py` 读取项目 `.env`，要求 `PTE_LAN_MODE=true`、至少 16 字符密码和已构建的 `frontend/dist`。配置只接受 RFC1918/loopback IPv4，实际监听当前设置的单一地址。FastAPI 中间件对网页、静态资源、API 和音频统一验证 HTTP Basic。当前共享 SQLite 和文件存储，没有每用户隔离。固定地址的网络层由路由器 DHCP 保留完成；应用不能保证 DHCP 租约永不变。HTTP 明文不适合公网或不可信网络。具体启动与当前地址见 [CONFIGURATION.md](CONFIGURATION.md)。

## 6. 已知限制

- 截图候选颜色参与首轮统计与低可信度建议；需要人工回听或修正。停顿符号自动映射尚不可用。
- 对齐、VAD 与 OpenPronounce 均有误差；发音音素候选未校准，不能承诺具体错音诊断。
- 同一原文的不同转写可能含替换、省略和尾部截断；当前 LCS 是词序启发式，重复词歧义需回听核查。
- 内网访问者共用数据和删除权限；上线给更广泛用户前需实现账户隔离与 HTTPS。

## 7. 本轮新增的报告处理流程

双边音频经 FFmpeg 标准化后，独立运行发音、流利度和可选展示曲线。曲线子进程限时 20 秒，不读取词色或参与诊断；50 ms 一点的 RMS 能量用于强弱可视化，周期性自相关给出粗略 F0，静音处不连线。前端把保留原色的双边 WaveSurfer 波形放在证据时间轴正上方，增高至 144 px；点击证据仍用整段 WAV 的 `[start,end]` 回听，不创建逐词音频文件。聚焦卡片的两侧目标词分别读取自己的猩际红/黄/绿标签，未知则显示未知。曲线默认折叠，点击可回听附近约 1.5 秒。

独立指标与截图颜色汇合后，Diagnosis 先保存有证据 ID 的发现；本机总结再选择本次 WPM、长停顿、速率波动及红黄词与停顿实例，输出具体词和时间，同时标明低质量来源。已配置的 AI 在本次勾选时生成两段结构化总结；后端验证引用及禁止新增数字/具体音素断言，失败则保留本机总结。报告 JSON 追加 `summaries` 和两侧 `acoustic`；旧报告没有新字段时仍可回听和显示原结论。“无法判断”来自对应 Metric 的 `reason`，不是 AI 配置状态。
