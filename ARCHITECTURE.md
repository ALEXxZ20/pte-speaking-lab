# PTE Speaking Lab — 技术架构

**文档修订：** v1.99 · **日期：** 2026-09-26<br>
**产品范围：** 见 [PROJECT_SPEC.md](PROJECT_SPEC.md)。本文件中的阈值和算法口径是 MVP 初始配置，须随分析记录版本化；它们不是 PTE 官方评分规则。

**当前代码实现与本设计蓝图的差异以 [TECHNICAL_ARCHITECTURE.md](docs/TECHNICAL_ARCHITECTURE.md) 为准。** 当前输入是共同朗读原文、用户真人录音，以及用户上传的 AI 生成高分录音；两侧各保留独立猩际实际转写、截图和分数。内网部署配置见 [CONFIGURATION.md](docs/CONFIGURATION.md)。

`1.0` 基线后的实现变化、数据库迁移和验证记录见 [版本变更记录](docs/RELEASE_1.0_TO_v1.99.md)。

## 1. 架构约束与决策

| 决策 | MVP 实现 | 原因 |
|---|---|---|
| 部署 | 单机 macOS 开发或受密码保护的可信内网访问 | 适合 M2/24 GB，迁移到 M5 Pro/48 GB 不改业务结构。 |
| 前端 | React + Vite + Tailwind + WaveSurfer | 表单、时间轴和片段回放。 |
| 后端 | FastAPI + SQLite + 本地 filesystem + FFmpeg/ffprobe | 持久化与可复算音频预处理，避免额外服务。 |
| 数据源 | 共同朗读原文 + 双边 ResponseSample；用户真人录音与已生成 AI 参考录音各自的猩际转写、分数、颜色截图和复核后的词级标签 | 分别保留原始来源与修订历史，不尝试重建猩际评分。 |
| 分析 | Pronunciation 与 Fluency 独立运行；Diagnosis 最后融合 | 可以单独验证、单独失败与重跑。 |
| AI | 官方 OpenAI 与兼容 Chat Completions 接口；Provider 契约隔离 | 可经本机 CLIProxyAPI 调用已授权模型，后续可扩展其他实现。 |
| Content | 仅存储猩际值/量表 | 防止需求蔓延和误称自行评分。 |

ChatGPT Plus 订阅与 OpenAI API 是独立产品和计费渠道；使用官方 OpenAI 时需独立 API key，使用 CLIProxyAPI 时需该代理认可的访问密钥。两者在项目中均由服务端 `OPENAI_API_KEY` 配置，不进入浏览器或 SQLite。模型名全部配置化，不锁定某个随时间变化的型号。

报告前端默认只渲染用户红黄词的上下文卡片，每张显示用户侧前后各三个转写词；只有比较层的 `shared_word_pairs` 给出明确位置配对时，才显示 AI 侧同词及其上下文。两侧片段各自依据可信词时间戳回听。切换到全部视图后，前端按录音时间渲染全部可定位证据，不截断尾部；无可靠时间戳的证据单独计数，不伪造定位。WaveSurfer 实例共享页面内播放焦点，新播放会暂停旧实例。

## 2. 组件与依赖方向

```text
React UI ──HTTP──> FastAPI
                   ├─ Color Screenshot Mapping / Review ──> SQLite + filesystem
                   ├─ Ingest / Validation ──> SQLite + filesystem
                   ├─ Audio Preprocess ─────> FFmpeg, speech regions
                   ├─ AlignmentProvider ────> token timestamps + quality
                   ├─ PronunciationEngine ───> PronunciationEvidence
                   ├─ FluencyEngine ────────> FluencyEvidence
                   ├─ ComparisonService ────> two-sided differences
                   └─ DiagnosisEngine ──────> findings + training actions
                                    └────────> LLMProvider (optional wording)
```

共享依赖只包括不可变的 `PreparedSample`：音频元数据、原始/规范化转写、token、语音区间和有质量标记的词时间戳。发音引擎不得读取流利度结果；流利度引擎不得读取发音结果。ComparisonService 接收两侧同一维度结果；DiagnosisEngine 才能同时读取两种 Evidence。Content 分不进入两个引擎的判定条件。

当前代码以同步请求执行分析，运行记录为 `running → complete/partial/failed`；长任务会占用该请求直到完成。后台任务队列、细粒度状态和进程中断恢复属于后续扩展。

## 3. 输入与数据合同

```python
class Score:
    value: float
    max_value: float | None  # None 时只展示，不比较
    source: Literal["xingji"]

class TokenInput:
    index: int                  # 在该侧转写中唯一，0-based
    surface: str                # 保留原样、标点和大小写
    normalized: str             # 比较用；由后端生成
    color: Literal["red", "yellow", "green", "unknown"]
    color_review_status: Literal["confirmed", "candidate", "unreviewed"]
    color_source_screenshot_id: str | None

class PauseLabelInput:
    after_token_index: int | None
    raw_label: str
    review_status: Literal["confirmed", "unreviewed"]

class ResponseSample:
    role: Literal["user", "benchmark"]
    audio_origin: Literal["human_recording", "ai_generated", "legacy_unspecified"]
    audio_asset_id: str | None   # 草稿可空；分析时必须有音频
    color_screenshot_asset_ids: list[str]  # 逐词颜色原图
    pronunciation_score: Score | None
    fluency_score: Score | None
    content_score: Score | None
    transcript_raw: str | None  # 直接粘贴的猩际转写；分析前校验
    transcript_source: Literal["xingji_copy", "manual_correction", "screenshot_ocr", "screenshot_ocr_edited"] | None
    tokens: list[TokenInput]
    pause_labels: list[PauseLabelInput]

class Exercise:
    reading_text_raw: str | None  # 两侧共同计划朗读的原文；旧记录可为空
```

当前实现以截图 OCR 文字作为两侧转写默认草稿，复制的猩际文本可选并用于差异核对；三项分数及量表由用户录入。Tesseract 给出正文词框与词序，像素分类器给出红/黄/绿候选，正文区域排除页眉和评分杂字。共同计划朗读稿另可上传完整英文文本截图。编辑 OCR 稿后重新按词序映射颜色；重复词歧义、漏词、裁剪和低置信度保持 `unknown`。不把 OCR 文本标为复制的猩际原文。

截图处理产生可编辑转写和标签映射草稿；逐词保留来源截图、坐标框、识别置信度和人工复核状态。低置信度颜色为 `unknown`，不能自动当作绿色。UI 并排显示原图、最终转写和候选颜色，允许逐词修改。截图候选以较低证据质量参与第一次统计与诊断；人工确认后提升证据质量。当前一侧支持一张整页截图。

转写以截图 OCR 后的可编辑文本为默认来源，复制文本仅是可选校对来源。输入校验要求 token index 连续、词序与最终文本一致；无法自动解析的标点/特殊符号进入人工修正，不静默挪动颜色。保存 OCR 草稿、可选复制文本、最终文本、原始截图和映射草稿。`unknown` 数量用红色感叹号提示。相同词多次出现用 `(sample_id, token_index)` 唯一识别；运行时绑定不可变 revision。

音频只通过上传接口写入数据目录，数据库存相对路径。上传后用 ffprobe 校验实际编码、时长及采样率，不信任扩展名和 MIME。原始音频只读保存；衍生音频由 FFmpeg 生成，例如 16 kHz、单声道 PCM WAV，保留转码命令/版本/hash。所有位置使用相对于音频起点的秒数，区间统一半开 `[start_s, end_s)`。

## 4. 音频处理与对齐

1. **Ingest：** 上传原文件到临时目录，探测并校验，计算 SHA-256，原子移动到 `data/audio/original/`。
2. **Prepare：** 生成分析 WAV、记录音量峰值/静音异常和总时长。原文件始终保留。
3. **Speech regions：** FFmpeg 静音探测只给出音量阈值以下的候选区间，不能直接视为无语音。MVP 用真实录音校验噪声/呼吸误报；若候选区间不足以稳定计算停顿和语音比例，加入实际 VAD 后才开放相关指标。
4. **Align：** 先检查复核转写与音频是否明显不符，再做词级 forced alignment，输出每词 `[start,end)`、质量/状态。WhisperX 是候选适配器；它提供词级时间戳，但在 Apple Silicon 上必须实测 CPU/内存表现后确定默认安装方式。MVP 开发先实现 `AlignmentProvider` 和可插拔适配器；上线验收需要至少一个在目标机实际可运行的词级对齐实现。
5. **Validate：** 检查时间单调、区间落入音频、覆盖率、异常长词、空 token；未通过的词标记 `unreliable`，不能用于精确回放或跨维度归因。

音频级流利度不依赖对齐，词级定位和局部语速依赖对齐。若对齐失败，分析结果为 `partial`，不伪造时间戳。可选 ASR 仅用于检测猩际 transcript 与音频明显不符的情况；它不覆盖猩际原文，也不作为 Content 评分。人工确认后的 transcript 修订需保留新版本和来源。

```python
class AlignmentProvider(Protocol):
    async def align(self, wav_path: Path, tokens: list[TokenInput]) -> AlignmentResult: ...

class PronunciationProvider(Protocol):
    async def assess(self, wav_path: Path, targets: list[TimedToken]) -> list[PronunciationSignal]: ...

class TranscriptionProvider(Protocol):  # 可选质量检查/未来本地 ASR
    async def transcribe(self, wav_path: Path, language: str) -> TranscriptResult: ...

class LLMProvider(Protocol):
    async def explain(self, evidence_package: DiagnosisInput) -> StructuredExplanation: ...
```

Provider Registry 按配置构建实例，业务层只调用契约。当前实现 OpenAI 官方 Responses API 与 OpenAI-compatible Chat Completions API（用于 CLIProxyAPI）；`TranscriptionProvider` 可接 OpenAI，但主流程已获得猩际转写，不强制调用。OpenPronounce 作为可选 `PronunciationProvider`；需要通过真实样本验证校准，不能把它的分数映射为猩际或官方分数。为 Anthropic、Gemini、Ollama/LM Studio、本地 ASR、本地 LLM 保留配置名和接口/适配器位置；**不把未实现项显示为可用 Provider**。OpenAI-compatible 使用服务端配置的自定义 base URL；本机 HTTP 可用，远端须为 HTTPS。

## 5. 发音 pipeline

**输入：** 单侧 `PreparedSample`、猩际标签/Pronunciation 分、可用发音 Provider。<br>
**输出：** 词级 `PronunciationEvidence[]` 和总体 `PronunciationSummary`。<br>
**独立性测试：** 不创建 FluencyResult 也能完整输出。

1. 计算明确颜色词中的红/黄/绿比例和连续红黄区间；另报告未知数量。
2. 选择目标词：用户红词 → 黄词 → 绿词抽样对照；benchmark 中共享词优先。选择规则和上限版本化。
3. 有可靠对齐时截取目标片段，向 PronunciationProvider 送最小音频范围及目标文本；记录模型名称、原始信号、其校准范围与错误。
4. 综合猩际标签、模型信号与音频片段，形成**证据**；具体音素、重音和尾音描述仅在 Provider 确实输出该维度且质量达标时出现。
5. 不输出自造发音分数；猩际分数作为外部参照。

共享词 A/B：先以 Unicode 规范化、大小写折叠、去外围标点获得 `normalized`；不做语义同义词匹配或简单词干化。对于重复实例，生成候选对并按对齐质量、颜色差异、出现顺序选配，保证一个实例最多参与一个配对；页面显示该配对是“相同词形的不同说法”，避免把时长差直接解释为发音好坏。没有共享词时返回空列表和明确说明。整体颜色比例可以比较，但显示样本量、差值和“不同文本/不同难度”限制。

## 6. 流利度 pipeline

**输入：** 单侧 `PreparedSample`、猩际 Fluency 分。<br>
**输出：** `FluencyMetric[]`、`FluencyEvidence[]`。<br>
**独立性测试：** 不创建 PronunciationResult 也能完整输出。

| 指标 | MVP 定义与依赖 |
|---|---|
| WPM | 猩际 token 数 / 首尾语音之间时长（分钟）；音频区间 + transcript。 |
| 发声 WPM | 猩际 token 数 / 语音区间总时长；与含停顿 WPM 分列。 |
| pause count | 首尾语音之间的内部非语音间隔，达到 `PAUSE_MIN_MS`；时间区间。 |
| long/very long pause | 内部停顿分别达到 `LONG_PAUSE_MS` / `VERY_LONG_PAUSE_MS`。 |
| mean/max pause | 候选内部停顿的均值/最大值；无停顿时显示 0 和 `n=0`。 |
| speech/silence ratio | 首尾语音窗口内语音时长与静音时长；同时保留 speech fraction，静音 0 时 ratio 为 null/∞ 状态。 |
| phrase length | 以长停顿切分语音段，报告平均段时长；每短语词数需要可信词时间戳。 |
| repetition | 已复核转写明确保留重复时才计数；否则为 `unavailable`，不能视为零。 |
| false starts | 已复核转写中的截断/重启或可信 ASR/音频线索；默认疑似，需可回听；缺证据为 `unavailable`。 |
| fillers | 已复核转写或可信音频/ASR 证据支持时计数；不能把语义上正常的 “like” 一律算 filler；缺证据为 `unavailable`。 |
| rate stability | 固定长度滑动窗口内词速的变异系数或分位差，要求可信词时间戳及最少窗口数。 |

默认 `PAUSE_MIN_MS=250`、`LONG_PAUSE_MS=500`、`VERY_LONG_PAUSE_MS=1000`，并记录噪声阈值、算法版本。边界精度取决于录音质量，不把这些指标等同猩际 Fluency 的计算方式。双边比较使用同一算法/阈值运行两侧，展示原值、差值与样本量；速度并非越快越好，诊断需考虑停顿、稳定性与清晰度，不为 WPM 设置单一“高分目标”。

## 7. 比较、诊断与错误证据模型

比较层生成三类结构：`pronunciation_distribution_comparison`、`shared_word_pairs`、`fluency_metric_differences`。每条明确两侧输入 ID、算法版本和缺失原因。高分样本只是观察对象，不作为绝对阈值。

```json
{
  "id": "ev_01",
  "run_id": "run_01",
  "dimension": "fluency",
  "kind": "long_pause",
  "sample_id": "sample_user",
  "token_index": 12,
  "start_s": 8.30,
  "end_s": 9.02,
  "value": 720,
  "unit": "ms",
  "source_type": "measured",
  "source_ref": "ffmpeg:silencedetect",
  "quality": "high",
  "algorithm_version": "pause-v1",
  "details": {"threshold_ms": 500}
}
```

`Evidence` 是不可变的结构化观察；`source_type` 取 `external | measured | model_signal`。`Finding` 才是推断，包含 `type`、`severity`、`confidence_level`（low/medium/high）、`evidence_ids[]`、`statement`、`limitations[]`、`recommendation` 和 `rule_version`。不要给没有校准依据的模型置信数值硬套概率含义。

交叉规则示例：在同一**用户样本**中，可信红/黄词区间与长停顿之间距离 `<=750 ms`，且多次出现，才可生成 `pronunciation_associated_hesitation` 候选；只有一次时最多提示“可能相关”。若对齐质量差、停顿处为句法边界、benchmark 同词也有类似停顿，降低置信度。LLM 只能在 JSON schema 内改写解释和训练文案，不能新增未被引用的测量、音素错误或因果结论；后端验证 `evidence_ids` 都存在且对应原文，否则拒绝并回退到规则模板。

## 8. SQLite 数据库 schema

以下是 MVP 逻辑 schema，采用迁移脚本落地。所有时间使用 UTC ISO-8601；秒数使用 REAL，原始分数及量表使用 REAL；JSON 字段用于保留 Provider 原始细节，不替代查询主键。

```sql
CREATE TABLE exercises (
  id TEXT PRIMARY KEY, question_type TEXT NOT NULL, title TEXT,
  source_note TEXT, source_question_id TEXT, reference_image_path TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE comparisons (
  id TEXT PRIMARY KEY, exercise_id TEXT NOT NULL REFERENCES exercises(id),
  user_sample_id TEXT, benchmark_sample_id TEXT, created_at TEXT NOT NULL,
  CHECK (user_sample_id IS NULL OR user_sample_id <> benchmark_sample_id)
);
CREATE TABLE audio_assets (
  id TEXT PRIMARY KEY, relative_path TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL,
  original_name TEXT, mime_type TEXT, duration_s REAL, sample_rate_hz INTEGER,
  created_at TEXT NOT NULL
);
CREATE TABLE screenshot_assets (
  id TEXT PRIMARY KEY, relative_path TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL,
  width_px INTEGER NOT NULL, height_px INTEGER NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE response_samples (
  id TEXT PRIMARY KEY, exercise_id TEXT NOT NULL REFERENCES exercises(id),
  role TEXT NOT NULL CHECK(role IN ('user','benchmark')),
  audio_asset_id TEXT REFERENCES audio_assets(id),
  transcript_raw TEXT, transcript_source TEXT,
  input_payload_json TEXT NOT NULL,
  input_version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
);
CREATE TABLE sample_screenshots (
  sample_id TEXT NOT NULL REFERENCES response_samples(id),
  screenshot_id TEXT NOT NULL REFERENCES screenshot_assets(id),
  display_order INTEGER NOT NULL,
  PRIMARY KEY(sample_id, screenshot_id)
);
CREATE TABLE screenshot_imports (
  id TEXT PRIMARY KEY, sample_id TEXT NOT NULL REFERENCES response_samples(id),
  parser_version TEXT NOT NULL, draft_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE sample_revisions (
  id TEXT PRIMARY KEY, sample_id TEXT NOT NULL REFERENCES response_samples(id),
  version INTEGER NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(sample_id, version)
);
CREATE TABLE external_scores (
  sample_id TEXT NOT NULL REFERENCES response_samples(id),
  dimension TEXT NOT NULL CHECK(dimension IN ('pronunciation','fluency','content')),
  value REAL NOT NULL, max_value REAL, source TEXT NOT NULL DEFAULT 'xingji',
  PRIMARY KEY(sample_id, dimension)
);
CREATE TABLE sample_tokens (
  sample_id TEXT NOT NULL REFERENCES response_samples(id), token_index INTEGER NOT NULL,
  surface TEXT NOT NULL, normalized TEXT NOT NULL,
  color TEXT NOT NULL CHECK(color IN ('red','yellow','green','unknown')),
  color_review_status TEXT NOT NULL CHECK(color_review_status IN ('confirmed','candidate','unreviewed')),
  color_source_screenshot_id TEXT REFERENCES screenshot_assets(id),
  PRIMARY KEY(sample_id, token_index)
);
CREATE TABLE pause_labels (
  id TEXT PRIMARY KEY, sample_id TEXT NOT NULL REFERENCES response_samples(id),
  after_token_index INTEGER, raw_label TEXT NOT NULL,
  review_status TEXT NOT NULL CHECK(review_status IN ('confirmed','unreviewed'))
);
CREATE TABLE analysis_runs (
  id TEXT PRIMARY KEY, comparison_id TEXT NOT NULL REFERENCES comparisons(id),
  user_revision_id TEXT NOT NULL REFERENCES sample_revisions(id),
  benchmark_revision_id TEXT NOT NULL REFERENCES sample_revisions(id),
  status TEXT NOT NULL, pipeline_version TEXT NOT NULL, config_json TEXT NOT NULL,
  provider_versions_json TEXT NOT NULL, error_json TEXT,
  started_at TEXT NOT NULL, finished_at TEXT
);
CREATE TABLE timed_tokens (
  run_id TEXT NOT NULL REFERENCES analysis_runs(id), sample_id TEXT NOT NULL,
  token_index INTEGER NOT NULL, start_s REAL, end_s REAL, quality TEXT NOT NULL,
  provider TEXT NOT NULL, PRIMARY KEY(run_id, sample_id, token_index)
);
CREATE TABLE metrics (
  run_id TEXT NOT NULL REFERENCES analysis_runs(id), sample_id TEXT NOT NULL,
  dimension TEXT NOT NULL, metric_key TEXT NOT NULL, value REAL,
  unit TEXT, quality TEXT NOT NULL, details_json TEXT NOT NULL,
  PRIMARY KEY(run_id, sample_id, dimension, metric_key)
);
CREATE TABLE evidence (
  id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES analysis_runs(id),
  sample_id TEXT NOT NULL, dimension TEXT NOT NULL, kind TEXT NOT NULL,
  token_index INTEGER, start_s REAL, end_s REAL, value REAL, unit TEXT,
  source_type TEXT NOT NULL, source_ref TEXT NOT NULL, quality TEXT NOT NULL,
  algorithm_version TEXT NOT NULL, details_json TEXT NOT NULL
);
CREATE TABLE findings (
  id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES analysis_runs(id),
  kind TEXT NOT NULL, severity TEXT NOT NULL, confidence_level TEXT NOT NULL,
  statement TEXT NOT NULL, limitations_json TEXT NOT NULL,
  recommendation_json TEXT NOT NULL, rule_version TEXT NOT NULL
);
CREATE TABLE finding_evidence (
  finding_id TEXT NOT NULL REFERENCES findings(id), evidence_id TEXT NOT NULL REFERENCES evidence(id),
  PRIMARY KEY(finding_id, evidence_id)
);
CREATE TABLE comparisons_result (
  run_id TEXT PRIMARY KEY REFERENCES analysis_runs(id), result_json TEXT NOT NULL
);
```

迁移时添加 `PRAGMA foreign_keys=ON`、必要索引（`analysis_runs.comparison_id`、`evidence.run_id/sample_id`、`response_samples.exercise_id`），并在服务层校验 `comparisons` 的两个样本同属其 Exercise 且角色正确。外键关系需在建表/提交次序中处理：先建 comparison 空关联或先建 samples，再更新两个 ID；完成前不允许分析。`response_samples`、`external_scores`、`sample_tokens` 和 `pause_labels` 是当前可编辑视图；每次确认或修正都写入不可变 `sample_revisions.payload_json`，其中封存音频、粘贴转写、截图、分数、词序/颜色、停顿及字段复核状态。运行时锁定双边 revision ID，旧报告及证据均按该快照解释，不读取当前可编辑视图。删除时通过服务层事务和文件垃圾回收统一处理，避免孤儿文件。

## 9. API 草案

以 `/api/v1` 为前缀；返回 Pydantic JSON，文件上传为 multipart；所有写操作经本机同源前端调用，默认仅监听 `127.0.0.1`。

| 方法/路径 | 作用 |
|---|---|
| `GET /health` | API、数据库、FFmpeg、Provider 配置状态（不泄露密钥）。 |
| `POST /assets/audio` | 上传并探测音频，返回 `audio_asset_id`。 |
| `POST /assets/screenshots` | 上传猩际逐词颜色截图，校验格式/大小并保留原图，返回 asset ID。 |
| `POST /screenshots/{id}/preview` | 提交前 OCR：猩际截图提取转写和词色；共同朗读稿截图提取可编辑文字；修改后的转写可重新映射。 |
| `POST /samples/{id}/screenshot-imports` | 以样本中最终转写为基准，保存截图词色映射草稿；返回坐标、置信度和错位提示。 |
| `POST /comparisons` | 创建 Exercise 与双边 ResponseSample 草稿；允许未填完字段，返回校验结果和 ID。 |
| `GET /comparisons/{id}` | 读取输入与最近分析摘要。 |
| `PATCH /samples/{id}` | 复核或修正 transcript、分数或标签，生成不可变 sample revision。 |
| `POST /comparisons/{id}/runs` | 启动一次分析，返回 `run_id` 和状态。 |
| `GET /runs/{id}` | 查询阶段、进度、错误/降级原因。 |
| `GET /runs/{id}/report` | 结构化双边指标、证据、比较、诊断和建议。 |
| `GET /assets/audio/{id}` | 支持 Range 的本机音频播放；校验资源 ID，不接收任意路径。 |
| `GET /history` | 分页列出比较及最新运行。 |
| `DELETE /comparisons/{id}` | 删除比较及其专属数据；共享 benchmark 文件引用计数为零才清理。 |
| `GET /settings/providers` | 返回可用性、当前模型名和缺失配置，不返回 key。 |

示例运行响应：`{"run_id":"...","status":"partial","completed_steps":["pronunciation","fluency"],"degraded_reasons":["benchmark_alignment_low_quality"]}`。HTTP 422 用于用户可修正的输入，409 用于已有活动分析，503 用于必需本地依赖不可用；各错误有稳定 `code`、`field`、`message`。

## 10. 目录结构与配置

```text
pte-speaking-lab/
├── frontend/src/{pages,components,api,types}/
├── backend/app/
│   ├── api/                 # FastAPI routes / schemas
│   ├── domain/              # ResponseSample, Evidence, Finding
│   ├── ingest/              # validation, normalization
│   ├── screenshots/         # match pasted transcript to screenshot colors/pauses
│   ├── audio/               # FFmpeg, speech regions, alignment
│   ├── engines/             # pronunciation.py, fluency.py, diagnosis.py
│   ├── comparison/          # shared words and metric deltas
│   ├── providers/           # registry, openai, openpronounce, adapters
│   ├── persistence/         # SQLite repositories and migrations
│   └── config.py
├── backend/tests/
├── data/                     # gitignored, portable; relative paths in DB
│   ├── db/pte.sqlite3
│   ├── audio/{original,derived}/
│   ├── screenshots/original/
│   └── temp/
├── .env.example
└── docs/
```

```dotenv
# Copy to .env; never commit .env or data/
PTE_DATA_DIR=./data
PTE_HOST=127.0.0.1
PTE_PORT=8000
MAX_AUDIO_MB=100
MAX_AUDIO_SECONDS=120
FFMPEG_BIN=ffmpeg
FFPROBE_BIN=ffprobe
PAUSE_MIN_MS=250
LONG_PAUSE_MS=500
VERY_LONG_PAUSE_MS=1000
CROSS_DIMENSION_WINDOW_MS=750
ALIGNMENT_PROVIDER=whisperx
PRONUNCIATION_PROVIDER=none
LLM_PROVIDER=openai
ASR_PROVIDER=none
OPENAI_API_KEY=
OPENAI_ANALYSIS_MODEL=<set-a-current-supported-model>
OPENAI_TRANSCRIPTION_MODEL=<set-only-if-asr-enabled>
OPENAI_BASE_URL=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
OLLAMA_BASE_URL=http://127.0.0.1:11434
LM_STUDIO_BASE_URL=http://127.0.0.1:1234/v1
```

`ALIGNMENT_PROVIDER=whisperx` 是目标配置示例；实际发布应通过 M2 实测确认版本及安装依赖。若模型首次下载需要网络或依赖许可，安装流程必须明确提示。`PRONUNCIATION_PROVIDER=none` 只做猩际标签级结果；启用 OpenPronounce 后才显示其具体模型线索。CLIProxyAPI 的实际配置为 `LLM_PROVIDER=openai_compatible`、`OPENAI_BASE_URL=http://127.0.0.1:8317/v1`，并填入其访问密钥与可用模型 ID。Provider 配置在运行前校验；不支持的名称返回明确错误。上方其他服务环境变量仅是未来扩展示例，不代表已有相应适配器。

## 11. 测试与观测

- 单元测试：token 规范化与重复词配对、不同量表不比较、停顿边界、空/无语音、无共享词、规则与证据 ID 验证。
- 集成测试：两份不同内容录音的完整运行；关闭任一引擎验证另一引擎独立输出；对齐失败/Provider 超时得到 partial report；原始音频哈希不变。
- 人工样本集：包含高分样本、红黄词密集、长停顿、噪声、重复、false start、转写与音频不符。记录时间戳误差、误报及 M2 资源峰值；验证后再确定对齐默认方案。
- 运行日志：仅记录 run/sample ID、阶段耗时、Provider 名与模型、质量等级、错误码；不记录密钥或完整转写。分析报告记录代码/规则/配置/Provider 版本，方便复现。

## 12. Phase 2/3 的技术演进

**Phase 2：** 优化 Apple Silicon 对齐（WhisperX 或替代方案）、OpenPronounce 校准、更多截图版式与批量导入、多 benchmark、训练趋势；可让较大模型在 M5 Pro/48 GB 运行，但通过 Provider 切换而非重写引擎。

**Phase 3：** 本地 ASR/LLM、可选独立任务队列、长期错误画像、更多题型；PronounceAI/GOPT 只在评估集证明收益且许可满足后接入。任何新模型分数保持为独立 `model_signal`，不覆盖猩际原始分数。

## 13. 第三方来源与许可证核对

以下基于仓库当前公开声明；实际锁定依赖版本时复核具体 LICENSE、模型权重和数据集的单独条款。

| 项目 | 用途 | 当前仓库声明 / 注意事项 |
|---|---|---|
| [Echoic](https://github.com/xialeistudio/echoic) | UI/交互参考，不复制其业务逻辑 | [MIT LICENSE](https://github.com/xialeistudio/echoic/blob/main/LICENSE)；若复制代码/素材需保留声明并核对素材权利。 |
| [OpenPronounce](https://github.com/Halleck45/OpenPronounce) | 可选发音 Provider | 仓库声明 [MIT](https://github.com/Halleck45/OpenPronounce/blob/main/LICENSE)；另核对模型权重、词典和依赖许可。 |
| [WhisperX](https://github.com/m-bain/whisperX) | 候选 forced alignment | 仓库声明 [BSD-2-Clause](https://github.com/m-bain/whisperX/blob/main/LICENSE)；下载的对齐模型和可选 diarization 组件可能另有条款。 |
| [PronounceAI](https://github.com/vikranthreddimasu/PronounceAI) | Phase 2/3 研究参考 | 仓库声明 [MIT](https://github.com/vikranthreddimasu/PronounceAI/blob/main/LICENSE)；含多模型，不能只看仓库许可证。 |
| [GOPT](https://github.com/YuanGongND/gopt) | Phase 2/3 研究参考 | 仓库声明 [BSD-3-Clause](https://github.com/YuanGongND/gopt/blob/master/LICENSE)；预训练权重、语料和评估数据分别核对。 |

同时核对 FFmpeg 构建选项与分发许可、WaveSurfer/前端依赖许可、OpenAI 与其他 Provider 的数据处理和使用条款。项目仅处理用户自行提供且有使用权的猩际数据；不内置、抓取或再分发猩际内容。第三方声明的快照和实际依赖版本应进入项目的 `THIRD_PARTY_NOTICES`。
