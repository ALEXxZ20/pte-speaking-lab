# 外部口语诊断源码功能审查与 PTE Speaking Lab 技术选型

更新：2026-09-27。审查对象为 Hugging Face Space `ztt625/tonigjw` 的提交 `fcef7d858b5f19949a6f943e87ac41a981264472`，本机独立副本位于 `/Users/alex/codex_project/pte 口语分析/`。重点审查 `app.py`、`analyze_v2.py`、`batch_analyze.py`；`export_html.py`、`ui_components.py` 仅用于核实报告出口。结论基于源码静态审查，未把作者使用的经验阈值当成 PTE 官方评分规则，也未运行准确率基准测试。

## 一、先看结论

这个 Space 更像一套**单录音、规则驱动的可视化诊断工具**：`faster-whisper base` 转写并给词时间戳，Praat/Librosa 提取音高与能量，程序按手写阈值生成节奏、逐词和语调提示，最后导出可回听的单文件 HTML。它的“AI”主要是语音识别和 Microsoft Edge 在线 TTS；诊断本身没有调用大语言模型。公开页面只暴露单题 RA 入口和另一个逐句朗读入口。核心代码虽有参考录音、共同原文和多题聚合能力，但公开页面没有把这些功能接上。[入口源码](https://huggingface.co/spaces/ztt625/tonigjw/blob/fcef7d858b5f19949a6f943e87ac41a981264472/app.py) · [分析源码](https://huggingface.co/spaces/ztt625/tonigjw/blob/fcef7d858b5f19949a6f943e87ac41a981264472/analyze_v2.py) · [批量源码](https://huggingface.co/spaces/ztt625/tonigjw/blob/fcef7d858b5f19949a6f943e87ac41a981264472/batch_analyze.py)

**建议保持我们项目的 React + FastAPI + SQLite + 双边样本/不可变证据架构**。有价值的是它把“问题摘要 → 逐词证据 → 波形回听 → 示例朗读”连起来的报告体验，以及音高、能量、功能词时长等可验证的候选测量。不要直接移植其“发音错音”“母语者标准”或“蹦词分”，也不要把 Edge TTS 生成音频当成经过猩际验证的高分 benchmark。

## 二、三个核心文件各做什么

| 文件 | 实际职责 | 已开放与未开放的边界 |
|---|---|---|
| [`app.py`](https://huggingface.co/spaces/ztt625/tonigjw/blob/fcef7d858b5f19949a6f943e87ac41a981264472/app.py) | Gradio 页面、上传音频或视频、FFmpeg 提取视频音轨、调用分析、导出 HTML；另有“粘贴英文 → 逐句 TTS 网页”。分析库延迟导入，队列限同时一个任务。 | `analyze_btn.click` 只传音频/视频；`diagnose()` 调 `run_analysis(..., ref_path=None, model_name="base", question_type="RA")`。页面没有共同原文、参考录音、题型或多题输入。 |
| [`analyze_v2.py`](https://huggingface.co/spaces/ztt625/tonigjw/blob/fcef7d858b5f19949a6f943e87ac41a981264472/analyze_v2.py) | 主流水线：音频加载、Whisper 转写、可选原文顺序匹配、音高/能量、节奏/停顿、逐词规则、可选双录音时长对比、CMU 词典提示、波形、Markdown/JSON、句级 Edge TTS。 | 独立 CLI/函数能接 `text`、`ref_path`、`question_type`；这不等于公开网页已经提供这些能力。 |
| [`batch_analyze.py`](https://huggingface.co/spaces/ztt625/tonigjw/blob/fcef7d858b5f19949a6f943e87ac41a981264472/batch_analyze.py) | `run_batch(items)` 用最多四个线程逐题调用 `run_analysis`，保留输入顺序与单题失败；`generate_synthesis` 按提示文字归类，生成错误频次、题型表、热力图和综合 Markdown。 | `app.py` 没有导入或调用 `run_batch`。分析结果没有数据库持久化；综合报告是规则文本聚合，并非独立模型的跨题根因判断。 |

`app.py` 是公开交互入口，`analyze_v2.py` 是复用的单题计算核心，`batch_analyze.py` 是尚未接到该公开入口的批量包装层。附属的 [`export_html.py`](https://huggingface.co/spaces/ztt625/tonigjw/blob/fcef7d858b5f19949a6f943e87ac41a981264472/export_html.py) 将诊断稿和音频嵌入单文件 HTML；[`ui_components.py`](https://huggingface.co/spaces/ztt625/tonigjw/blob/fcef7d858b5f19949a6f943e87ac41a981264472/ui_components.py) 负责可点击回听的波形。

## 三、`analyze_v2.py` 的真实处理过程

```text
单侧音频 → 16 kHz → Whisper base/CPU int8 + VAD + 词时间戳
                    ↓
          可选：ASR 词与提供原文按顺序匹配
                    ↓
          Praat 基频 + Librosa RMS + 词时长/间隙
                    ↓
          规则判断：WPM、非意群停顿、拖长、填充词、节奏、语调
                    ↓
          可选：参考录音也运行 ASR/基频，再比较共同词位时长
                    ↓
          CMU 词典参考 + 逐词提示 + 波形 + Markdown/JSON
                    ↓
          分句调用 Edge TTS → HTML 中的示范播放器
```

1. `run_whisper` 使用 `WhisperModel(model_name, device="cpu", compute_type="int8")`，英语、`beam_size=5`、`vad_filter=True`、`word_timestamps=True`；超过 115 秒截取前段。模型实例缓存且推理有全局锁。词时间戳和词概率都是 ASR 输出，不是发音标准答案。[源码](https://huggingface.co/spaces/ztt625/tonigjw/blob/fcef7d858b5f19949a6f943e87ac41a981264472/analyze_v2.py)；[faster-whisper 官方说明](https://github.com/SYSTRAN/faster-whisper)。
2. 有 `text` 时，先将识别词与原文做顺序匹配，未匹配词可能被标为缺失或替换；无 `text` 时用 ASR 词作为分析文本。代码也用能量检测修正第一个词可能包含的前置静音。原文对齐是字符串与识别词匹配，不等同声学 forced alignment。[源码](https://huggingface.co/spaces/ztt625/tonigjw/blob/fcef7d858b5f19949a6f943e87ac41a981264472/analyze_v2.py)
3. `analyze_rhythm` 计算词间隙、WPM、功能词/实词平均时长比、拖音、填充词、>=500 ms 非句法边界停顿；`analyze_pitch` 用 Parselmouth 的 F0 和 Librosa RMS 计算变化程度。像 120 ms 非边界间隙、1.6 的时长比、110–200 WPM 和音高 CV 分档，均为源码中的**启发式阈值**。某些句法边界来自标点/规则推断，误判会传播到“异常停顿”。“蹦词指数”是多项规则相加，源码没有校准样本或官方分数映射；加项上限与页面显示的 `/6` 也需核查一致性。[源码](https://huggingface.co/spaces/ztt625/tonigjw/blob/fcef7d858b5f19949a6f943e87ac41a981264472/analyze_v2.py)
4. `analyze_word_stress` 从 CMU 词典取得标准音素/重音。代码明确注释多音节词重音“词典参考信息，不做音频检测”；疑似难点音素依赖 Whisper 低词概率，疑似音素差异依赖 ASR 识别词与目标词的字典音素差。它不能证明真实录音发错了某个音素；网络噪声、口音、ASR 误识别或省词也可造成同样现象。`_analyze_connected_speech` 主要用词首尾字母及词间结构生成连读/失爆提示，应标为读法建议，不是已测得的连读行为。[源码](https://huggingface.co/spaces/ztt625/tonigjw/blob/fcef7d858b5f19949a6f943e87ac41a981264472/analyze_v2.py)
5. 有 `ref_path` 时 `compare_with_native` 会分析第二段音频；有共同原文时按原文词位比较时长和音高，没有原文则退化为按第 `i` 个词对第 `i` 个词。这种退化在漏词、重复词和结尾不同时会错配。作者代码称参考侧为“native”，但任意上传音频都可能被传入；我们项目必须继续称为“AI 参考录音/benchmark”，不可推定母语或标准。[源码](https://huggingface.co/spaces/ztt625/tonigjw/blob/fcef7d858b5f19949a6f943e87ac41a981264472/analyze_v2.py)
6. `run_analysis` 返回单题结构，同时在音频旁写 Markdown 与 JSON；网页再经 `export_html.py` 输出内嵌音频/波形的 HTML。单文件易于保存和分享，若音频多，文件体积和生成耗时会增加。[分析源码](https://huggingface.co/spaces/ztt625/tonigjw/blob/fcef7d858b5f19949a6f943e87ac41a981264472/analyze_v2.py) · [导出源码](https://huggingface.co/spaces/ztt625/tonigjw/blob/fcef7d858b5f19949a6f943e87ac41a981264472/export_html.py)

## 四、Microsoft Edge TTS 的两条路径

| 路径 | 输入与输出 | 关键限制 |
|---|---|---|
| `app.py:generate_reading_page` | 用户粘贴英文，按句末标点/换行切句；逐句 `edge_tts.Communicate(sentence, voice).save(mp3)`；生成带独立播放器的 HTML。页面可选 `en-GB-SoniaNeural` 或 `en-US-AriaNeural`。 | 最长 3000 字符；句子逐个生成，联网失败则整个生成失败。 |
| `analyze_v2.py:_edge_tts` + `generate_markdown_draft` | 单题报告优先用原文，否则用 ASR 文本，经标点恢复/分句后逐句调用 Edge TTS，音频以 base64 嵌入报告；默认 `en-US-AriaNeural`。 | 失败返回无音频并保留报告。单词级示范在代码中暂时关闭。 |

`edge-tts` 调用的是 Microsoft Edge 的**在线**语音服务，语音生成发生在外部服务端；下载后的 HTML 可离线播放，不代表生成过程离线。它无需在本机部署 TTS 大模型，但存在网络可用性、数据外发、服务接口变化和语音控制边界。若录音文本涉及隐私，要把发送文本到外部服务明确告知用户。该 Space 的 TTS 示范**没有经过猩际评分验证**，不能直接等同我们双边样本里的“AI 高分参考录音”。[源码](https://huggingface.co/spaces/ztt625/tonigjw/blob/fcef7d858b5f19949a6f943e87ac41a981264472/app.py) · [edge-tts 项目说明](https://github.com/rany2/edge-tts)

## 五、与 PTE Speaking Lab 的功能/架构对比

| 维度 | 外部 Space | 我们的当前项目 | 判断 |
|---|---|---|---|
| 产品输入 | 公开页面单侧录音/视频；核心函数可选原文和参考录音 | 双侧音频、猩际分数/截图词色、共同朗读原文和修订历史 | 双边实证分析应保留我们的数据模型。 |
| 语音识别 | Whisper base CPU int8 自动转写并给词时间 | 猩际截图 OCR 转写为主，WhisperX 可选对齐；尚无独立 ASR 校验实际读法 | 外部的独立 ASR 可补充“实际说了什么/尾部漏词”，但不能覆盖猩际原始输入。 |
| 发音证据 | ASR 概率/识别差 + CMU 参考 + 规则提示 | 猩际红黄绿优先；可选 OpenPronounce 候选，证据记录来源和质量 | 我们的来源边界更清楚；外部的词典参考可作为教学资料，不宜提升为确诊。 |
| 流利度/韵律 | 词间隙、WPM、拖音、功能词时长、音高、RMS、意群候选 | VAD 停顿/语速/短语/稳定性，双侧同算法比较；没有独立 F0/RMS | 可增设可回听的 F0/RMS/词时长**候选测量**，先用真实样本验证质量。 |
| 对比 | 核心可按原文词位比单词时长；公开网页不提供参考录音 | 两侧独立运行，按共同原文词位配对共享词，比较词色和流利度 | 我们的匹配规则适合 AI 录音与用户内容略不同、尾部不一致的场景。 |
| 报告 | 摘要、图表、逐词回听、句级示范；下载单文件 HTML | 可复核证据、波形/时间轴、历史运行及不可变报告 | 借鉴信息层级和便携导出；保留我们的可追溯历史。 |
| 部署与扩展 | Gradio 单脚本式公开页、临时文件；批量模块与网页未连通 | React/FastAPI/SQLite/文件系统、Provider 接口、局域网服务 | 我们更适合长期迭代和多侧数据；外部更适合快速展示单次报告。 |
| TTS | Edge 在线逐句生成 | 用户提供已经在猩际评分的 AI 参考录音；本项目暂不生成 | 可新增“练习示范”，但与评分 benchmark 分开标注。 |

我们当前代码行为参见 [`TECHNICAL_ARCHITECTURE.md`](TECHNICAL_ARCHITECTURE.md) 与 [`PROJECT_SPEC.md`](../PROJECT_SPEC.md)。本表的优劣指**对当前产品目标的适配程度**，不是经过同数据集跑分的模型准确率排名。

## 六、后续技术选型与落地顺序

1. **先补独立 ASR 对照，但不改原始事实。** 在现有 `TranscriptionProvider` 位置接可替换实现：M2 可先用 `faster-whisper` 小模型验证，M5 Pro 48GB 再测 MLX Whisper 的较大模型。输出单独存 `observed_transcript`、词时间与差异证据；猩际 OCR 转写和截图词色保持原样。重点检查末尾遗漏、重复、填充词以及 ASR 自身误识别。MLX Whisper 官方示例支持 Apple Silicon 上的词时间戳；具体模型和延迟要在两台真实机器、同一录音上评测。[MLX Whisper 官方说明](https://github.com/ml-explore/mlx-examples/blob/main/whisper/README.md)
2. **保持发音与流利度独立。** 把 F0、RMS、功能词时长和意群停顿做成新的 `AcousticFeatureProvider`/测量结果，流利度引擎消费可信度达标的观测；发音引擎继续消费猩际词色和校准过的音素候选。ASR 低概率只可触发回听，不可直接生成“辅音读错”结论。规则阈值必须保存版本、单位和缺失原因，并在 `Choices of Lunch` 等真实题与用户人工标注上验证。
3. **把示范音与 benchmark 拆成两个概念。** 可以提供 Edge TTS 作为联网、可选的“逐句跟读”；若目标是完全本地运行，再单独部署本地 TTS Provider。无论哪种，只有音频确实作为猩际高分样本导入并保留外部分数/词色时，才进入高分 benchmark 对比。不要用 TTS 自评自身发音质量。
4. **报告先做轻量改进。** 首页展示 3 个主要问题、证据质量和可回听位置；再展开两侧指标、红黄词和波形。若需要独立分享，增加单文件 HTML 导出，但要设计脱敏、下载授权和音频体积上限；数据库历史仍是主记录。批量趋势可在单题证据稳定后加入：按题型聚合已确认的指标/证据，不从中文提示文字反推“根因”。
5. **M5 Pro 计算节点按阶段选模型。** 先实测独立 ASR + 可选对齐，然后实测本地 TTS，最后才接证据受约束的本地 LLM 解释。单用户可以顺序调度较大模型以控制内存峰值；不要根据“参数更大”推断音素定位一定更准。部署步骤见 [`M5_LOCAL_AUDIO_DEPLOYMENT_PLAN.md`](M5_LOCAL_AUDIO_DEPLOYMENT_PLAN.md)。

### 最小验收实验

- 选至少一题 RA 和一题 DI，包含重复词、真实口误及录音结尾不一致；人工标注实际读词与词时间，分别记录 ASR 漏词/错词、词时间偏差、分析耗时与 M5 峰值内存。
- 同一份录音下，确认旧猩际颜色、分数和历史报告不会被 ASR 或新 TTS 改写；模型失败时仍可完成现有发音/流利度路径，并明确列出不可用项。
- 让人复核新增 F0/RMS/功能词时长提示的误报，设定足够的观察样本后才决定是否显示用户可见诊断；不把内部指标换算为 PTE 官方分数。

## 七、许可与实施边界

该 Space 的公开副本没有发现 `LICENSE` 或明确 `license:` 元数据；这意味着当前无法确认移植、再发布其源码或界面资产的许可范围。本报告只引用源码来分析实现与产品思路，**不建议把其 Python/HTML/CSS 原样并入我们的仓库或上传另一仓库**；若要复用具体代码，先取得作者许可并记录版本与授权。其依赖库和模型也要逐一核查许可。[原 Space](https://huggingface.co/spaces/ztt625/tonigjw/tree/fcef7d858b5f19949a6f943e87ac41a981264472) · [Hugging Face 许可证说明](https://huggingface.co/docs/hub/repositories-licenses)

## 八、语言学与教学审查：保留教学价值，修正诊断措辞

本节从中国英语学习者的**可理解度、练习迁移与个体差异**出发审查源码，不声称已听过具体用户录音。目标是帮助学习者让听者更容易理解、在 PTE 任务中表达更流畅；不以抹去中国口音为目标。Pearson 的 PTE Academic 页面同时关注元音/辅音、词与短语重音、节奏、停顿及可理解度，并认可可被理解的地区/国家口音。[Pearson 题型与评分说明](https://www.pearsonpte.com/pte-academic/test-format/speaking-writing/)；二语发音教学荟萃研究也把可理解度与“听起来像母语者”分开。[Saito 2021](https://discovery.ucl.ac.uk/id/eprint/10125305/)

### 值得保留的教学设计

| 设计 | 教学价值 | 放入本项目时的口径 |
|---|---|---|
| 原音、参考音、原文与词位置放在一起 | 学习者可先听差别，再尝试改读，比一条笼统“发音不好”有操作性。 | 显示“用户原音 / AI 参考音 / 预期词”，并注明 AI 参考不是唯一正确读法。只比较可靠配对的同词。 |
| 元音/辅音难点词库与 CMU 重音 | 适合作为**针对性教学提示**，帮助学生知道该听什么、练什么。 | 字典展示“这个词的常见读法”，不写“系统已听出你把 /ɪ/ 读成 /iː/”。允许英美等读法差异。 |
| 意群、词间停顿和逐句模仿 | 在完整短语里练停顿与重音，更接近真实朗读任务；韵律教学对可理解度有价值。 | 用可信的音频时间、共同原文和回听给出“此处有 620 ms 停顿”，再解释其可能打断短语。单个阈值不等于扣分。 |
| Edge TTS 分句示范与 HTML 回听 | 用户可听、模仿、重录，报告也容易看懂。 | 标成“练习示范音（Edge 在线生成）”；不得标成“已经过猩际评分的高分录音”。 |

这些关注点有研究依据，但**中国学习者群体的常见困难不是每个中国用户的实际错误**。一项有中国大学生录音和跨国听者的研究指出，元音质量/长短、双元音、齿间擦音、词尾及辅音连缀、重音/节奏等可影响理解；它不能证明一个未听或未标注的个体犯了其中任何错误。[Zhang 2015](https://doi.org/10.1515/cjal-2015-0002)；[中国英语发音教学综述](https://www.cambridge.org/core/journals/language-teaching/article/is-english-pronunciation-teaching-in-china-ready-for-the-intelligibility-principle/DB7754973C593DEF7EF0551DE4851657)

### 必须修正的推断

| 源码中的说法或做法 | 为什么不可靠 | 建议对用户怎么说 |
|---|---|---|
| `analyze_v2.py` 将 Whisper 低词概率直接写成“元音不饱满/辅音不准”“严重不清晰”；识别替换被写成具体“音素偏差”。 | ASR 只给整词识别结果和模型概率，没有测量某个元音/辅音的实际发音。噪声、口音、漏词、近音词和模型偏差都能触发。 | “这个词的转写与原文不一致，建议听原音并与参考音核对；目前无法确定是读词不同、录音质量还是具体发音。” |
| CMU 第一读音用于“重音错误”，`CN_DIFFICULT_PHONEMES` 将许多音一律列为中国学习者问题。 | 词典给目标词的常见读音，并没有检测用户重音；个人所用语言、地区口音和英语变体不同。`ER` 等描述还混合英美读法。 | “本词常见重音在第 2 音节；可听示范核对。系统尚未可靠测出你把重音放在何处。”根据用户实际反复出现的困难再启用对应卡片。 |
| `_analyze_connected_speech` 通过拼写首尾字母断定“应连读/失爆”；`analyze_pitch` 说“偏平符合 PTE 偏好”、高音就可能异常。 | 字母不等于音素；连读/弱化受真实发音、语境和说话意图影响。内容词可因对比焦点而升高音高，功能词也可能被刻意强调。Pearson 描述的是自然、平顺、恰当的重音和分句，没有通用“越平越好”阈值。 | 改成“可尝试这样连起来读”的示范提示；F0/RMS 仅展示曲线或经人工验证的异常候选，不直接写“你不该重读”。[Pearson](https://www.pearsonpte.com/pte-academic/test-format/speaking-writing/) |
| 120 ms 词间隙、功能词/实词时长比 1.6、单词比 AI 参考长 1.8 倍，被直接解释为“蹦词”“想词”“元音拖长”。 | 时长与语速、音节数、词位、强调、说话人和语境有关；时间比只能说明差异，无法证明思维原因或元音本身。`app.py`、`app_gradio_backup.py`、`app_fastapi.py` 均显示“蹦词指数 /6”，但源码多项加分未统一限定在 6 以内。 | “在这两个词之间测得 620 ms 停顿；短语内连续性可能受影响。请回听判断是否是计划停顿。”指数先改为分项说明，实测校准前不作为评分。 |
| `batch_analyze.py` 从中文提示字符串提取“共性根因”，并把计数相加。 | 多题出现相同提示可说明**现象重复**，但不能证明同一个生理或认知根因；错误文本变更还会改变分类结果。 | 聚合结构化证据 ID、同一指标和题型；展示“在 3/5 题观察到相似停顿”，原因仍标为待核查。 |
| `analyze_template_content_ratio` 把固定比例写成模板过多会压低 Content/Fluency。 | 单靠词表比例不能判断图像信息是否覆盖、用词是否恰当，也不能推断官方分数变化；当前项目明确不自行评 Content。 | 本项目不采纳此类内容评分。若未来分析 DI 内容，须另设任务和证据。 |

`app_gradio_backup.py` 曾给用户可选“原文”；`app_fastapi.py` 的轻量替代入口也接可选原文，但改用 `Whisper tiny`、没有参考录音；当前 [`app.py`](https://huggingface.co/spaces/ztt625/tonigjw/blob/fcef7d858b5f19949a6f943e87ac41a981264472/app.py) 的诊断按钮只传音频/视频，因此用户在公开页面得不到有原文条件下的词序核查。这是**入口差异**，不能把三套入口的能力相加后描述为一个现成产品。

### 对我们项目建议增加的“教学层”

保持现有发音/流利度引擎与证据模型，再在诊断之后建立独立的 `TeachingRecommendation`：`观察到什么 → 可能影响什么 → 练习动作 → 下次如何核查`。候选音素卡需要明确“推荐检查的发音点”，只在目标词确实出现、且有猩际红黄词或用户复核的听感线索时展示；同一份报告只给优先级最高的 1–3 项。可选卡片：/ɪ/–/iː/ 的听辨与最小对立词、/θ/ 的舌位与气流、词尾辅音/辅音连缀、双元音移动、词重音和意群。教学卡内容可预先由语言教师审核，用户看到的是短中文动作说明和两段可回听音频；**选择卡片的证据等级**与**卡片本身的教学内容**分开保存。

例如：“猩际将 `ship` 标黄；本系统尚不能确认是哪一个音。请先听原音与示范，辨别 `ship` /ʃɪp/ 和 `sheep` /ʃiːp/，各读 3 次后放回完整短语再录一遍。若你听不出差异，先做听辨练习；若能听出但读不稳，再做跟读。下次比较同词的颜色、可理解度和录音片段。”只有经可靠声学分析或人工复核，才可把“检查 /ɪ/”升级为“本次 /ɪ/ 存在具体偏差”。这个范例是**教学模板**，不是对现有用户录音的诊断。
