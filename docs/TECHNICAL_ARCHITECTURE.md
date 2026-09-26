# PTE Speaking Lab：当前实现的技术架构与处理原理

此文描述**现在的代码行为**。产品目标与后续扩展见 [PROJECT_SPEC.md](../PROJECT_SPEC.md) 和 [ARCHITECTURE.md](../ARCHITECTURE.md)；运行与配置见 [CONFIGURATION.md](CONFIGURATION.md)。

## 1. 系统边界与实际输入

前端为 React + Vite + Tailwind + WaveSurfer；后端为 FastAPI；SQLite 保存结构化记录，filesystem 保存音频和截图；FFmpeg 做音频转换。本机开发是 Vite 5173 代理 API 8000。内网部署先构建前端，FastAPI 在单一 8765 端口同源提供网页/API/录音，并用 HTTP Basic 覆盖所有路径。`scripts/start.sh`、`stop.sh`、`restart.sh` 通过 macOS `launchd` 管理服务；plist、PID 与日志位于 Git 忽略的 `data/`。

`Comparison` 由一个 `Exercise` 与两个 `ResponseSample` 组成。Exercise 的 `reading_text_raw` 是**共同计划朗读的原文**；可从完整英文朗读稿截图 OCR 后编辑，原图与 OCR 草稿分别保存。user 样本是人的录音；benchmark 样本是用户上传的**已生成 AI 参考录音**。每侧保存上传音频、猩际截图、截图 OCR 草稿、最终编辑稿、可选复制稿、三项原始分数和词色状态。两侧实际转写可以在个别词和尾部不同。AI 参考不等于标准发音，Content 只存外部分数。

## 2. 一次比较的具体处理过程

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

流利度各指标用同一算法与阈值分别测量，展示两侧原值、差值与质量；缺失值在表格中统一显示“无法判断”，表格上方说明常见原因及配置条件，下方以中文总结有效指标。两侧词数/尾部可能不同，速度差不是目标分数。发音侧另比较词色总体分布。证据时间轴按录音时间排列，仅给用户红词和黄词条目加对应底色，不改变时间顺序。

`engines/diagnosis.py` 在两个独立引擎之后运行，以有证据 ID 的红词、长停顿、局部语速波动生成最多三项建议；红词附近的停顿只表述为相关假设。可选 LLM 只改写这些规则建议，返回的 finding ID 和证据 ID 必须与本机结果完全一致，否则回退原规则。Content 不进入诊断。

## 3. 数据库、版本与接口

SQLite 迁移位于 `backend/app/persistence/migrations/`：0001 建立资产基础表；0002 建立 exercises、response_samples、external_scores、sample_tokens、pause_labels、sample_revisions、comparisons、screenshot_imports；0003 建立 analysis_runs、timed_tokens、metrics、evidence、findings、finding_evidence、comparisons_result；0004 为 exercises 加入 `reading_text_raw`；0005 加入朗读稿截图/OCR 来源及 `candidate` 词色状态。每次修改样本产生新 revision；每次分析运行绑定两侧 revision ID、算法版本及关键阈值。旧报告存完整 JSON，不被输入更正覆盖。AI 录音来源 `audio_origin` 保存在样本 revision JSON 中；旧记录缺字段视为 `legacy_unspecified`。

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
