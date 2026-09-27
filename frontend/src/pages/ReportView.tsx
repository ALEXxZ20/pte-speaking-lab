import { useEffect, useRef, useState } from 'react'
import type { Evidence, Report, SideResult } from '../api/client'
import AcousticPlot from '../components/AcousticPlot'
import { Waveform } from '../components/Waveform'

type Role = 'user' | 'benchmark'
const names: Record<Role, string> = { user: '我的回答', benchmark: 'AI 高分参考录音' }
const metricNames: Record<string, string> = { wpm: '整体词速', voiced_wpm: '发声词速', pause_count: '停顿候选', long_pause_count: '长停顿候选', very_long_pause_count: '很长停顿候选', mean_pause_ms: '平均停顿', max_pause_ms: '最长停顿', speech_silence_ratio: '语音/静音比', speech_fraction: '发声占比', mean_phrase_s: '平均短语时长', mean_phrase_words: '平均短语词数', rate_stability_cv: '局部语速波动', repetition_count: '重复', false_start_count: '重启', filler_count: '填充词' }
const colorStyles: Record<string, string> = { red: 'bg-red-100 text-red-800', yellow: 'bg-amber-100 text-amber-800', green: 'bg-emerald-100 text-emerald-800', unknown: 'bg-slate-100 text-slate-600' }
function display(value: number | null, unit: string) { return value === null ? '无法判断' : `${value}${unit === 'words/min' ? ' WPM' : unit === 'ms' ? ' ms' : unit === 's' ? ' s' : unit === 'count' ? ' 次' : ''}` }
const qualityNames: Record<string, string> = { high: '高', medium: '中', low: '低', unavailable: '无法判断' }
function fluencySummary(report: Report) {
  const metrics = report.comparison.fluency_metric_differences
  const parts: string[] = []
  const wpm = metrics.wpm
  if (wpm?.delta_user_minus_benchmark !== null && wpm?.delta_user_minus_benchmark !== undefined) parts.push(wpm.delta_user_minus_benchmark === 0 ? 'WPM／每分钟词数：我的回答与参考相同。' : `WPM／每分钟词数：我的回答比参考${wpm.delta_user_minus_benchmark > 0 ? '快' : '慢'} ${Math.abs(wpm.delta_user_minus_benchmark).toFixed(1)} 词/分钟。`)
  const pauses = metrics.long_pause_count
  if (pauses?.delta_user_minus_benchmark !== null && pauses?.delta_user_minus_benchmark !== undefined) parts.push(pauses.delta_user_minus_benchmark === 0 ? '长停顿候选：我与参考次数相同。' : `长停顿候选：我比参考${pauses.delta_user_minus_benchmark > 0 ? '多' : '少'} ${Math.abs(pauses.delta_user_minus_benchmark)} 次。`)
  const stability = metrics.rate_stability_cv
  if (stability?.delta_user_minus_benchmark !== null && stability?.delta_user_minus_benchmark !== undefined) parts.push(`局部语速波动：我${stability.delta_user_minus_benchmark === 0 ? '与参考相同' : stability.delta_user_minus_benchmark > 0 ? '比参考更大' : '比参考更小'}，仍需结合回听判断。`)
  return (parts.length ? parts.join(' ') : '本次缺少足够可靠的双边时间指标，暂无法做数量对比。') + ' 差值为“我的回答减参考”，正值表示我在该指标上更高；质量“高/中/低”表示证据可靠程度，“无法判断”表示没有可用测量。速度差和这些指标都不是猩际评分。'
}

function fluencyMissingExplanation(report: Report) {
  // 只根据本次实际的 reason 解释缺失；缺 API key 不会影响音频测量。
  const reasons = new Set((['user', 'benchmark'] as const).flatMap(role =>
    Object.values(report.samples[role].fluency.metrics).filter(item => item.value === null).map(item => item.reason)))
  const lines: string[] = []
  if (reasons.has('vad_regions_unreliable')) {
    const side = report.samples.user.audio
    const nearlyAllSpeech = side.speech_regions?.quality === 'low' && side.speech_regions.speech_s > side.duration_s * 0.98
    lines.push(nearlyAllSpeech ? '我的录音被语音活动检测近乎整段判为发声，无法可靠算发声词速、语音/静音比和发声占比；需要更清晰的录音或经真实样本验证的语音活动检测方案。' : '语音活动检测没有可靠分开语音与静音；发声词速、语音/静音比和发声占比暂无法计算，可检查录音噪声并重新录制。')
  }
  if (reasons.has('insufficient_word_timestamps') || reasons.has('no_reliable_speech_window') || reasons.has('no_reliable_pause_source')) lines.push('部分词级时间不足：检查转写是否与录音一致，并启用或修复词级对齐；无法精确定位时不补造时间。')
  if (reasons.has('source_transcript_may_omit_disfluencies')) lines.push('重复、重启、填充词需要保留口误的逐字转写或人工标注；猩际转写可能省略它们，目前没有可开启的配置。')
  if (reasons.has('too_few_windows')) lines.push('局部语速窗口数量不足，需要更长的可对齐语音，不能靠 API key 补算。')
  return lines
}

function SidePanel({ side, role, setJump }: { side: SideResult; role: Role; setJump: (jump: { start: number; end?: number; nonce: number }) => void }) {
  const scores = side.sample
  const counts = side.pronunciation.summary.counts
  const isTTS = role === 'benchmark' && scores.audio_origin === 'edge_tts'
  return <section className="panel space-y-5"><div><p className="eyebrow">{role === 'user' ? 'User' : 'Benchmark'}</p><h3 className="mt-1 text-xl font-semibold">{isTTS ? 'TTS 练习参考录音' : names[role]}</h3><p className="mt-1 text-sm text-slate-600">{isTTS ? '合成词时间' : '对齐'} {side.alignment.trusted_count ?? 0}/{side.alignment.total_count ?? side.sample.tokens.length} 词 · 录音 {side.audio.duration_s.toFixed(1)} 秒</p></div>{isTTS ? <p className="rounded-lg bg-teal-50 p-3 text-sm text-teal-900">在线合成 · {side.audio.tts?.voice} · {side.audio.tts?.rate} 语速。没有猩际分数和逐词颜色；词时间来自生成事件，未经过独立语音识别核验。</p> : <div className="grid grid-cols-3 gap-2">{([['发音', scores.pronunciation_score], ['流利度', scores.fluency_score], ['内容', scores.content_score]] as const).map(([name, score]) => <div key={name} className="rounded-xl bg-slate-50 p-3 text-center"><p className="text-xs text-slate-500">猩际{name}</p><p className="mt-1 font-semibold">{score ? `${score.value}/${score.max}` : '未提供'}</p></div>)}</div>}<div><h4 className="font-semibold">{isTTS ? '朗读稿词语与回听位置' : '逐词颜色'}</h4>{!isTTS && <p className="mt-1 text-sm text-slate-600">红 {counts.red} · 黄 {counts.yellow} · 绿 {counts.green} · <span className="font-semibold text-red-700" title="未知词需要手动复核">! 未知 {side.pronunciation.summary.unknown_count}（请手动复核）</span> · 截图候选 {side.pronunciation.summary.candidate_count || 0}</p>}<div className="mt-3 flex max-h-40 flex-wrap gap-1.5 overflow-auto">{side.sample.tokens.map(token => { const time = side.alignment.tokens[token.index]; const known = token.color_review_status === 'confirmed' || token.color_review_status === 'candidate' ? token.color : 'unknown'; return <button key={token.index} type="button" disabled={!time || time.quality !== 'medium' || time.start_s === null} onClick={() => setJump({ start: Math.max(0, time.start_s! - 0.2), end: (time.end_s || time.start_s!) + 0.2, nonce: Date.now() })} className={`rounded-md px-2 py-1 text-sm disabled:cursor-not-allowed ${isTTS ? 'bg-teal-50 text-teal-900' : colorStyles[known]}`} title={isTTS ? '合成服务返回的词位置；点击回听' : `${token.color_review_status === 'candidate' ? '截图候选，待人工复核；' : ''}${time?.quality === 'medium' ? '点击回听词片段' : '时间定位不可靠'}`}>{token.surface}</button> })}</div></div></section>
}

function PlaybackDock({ report, jumps, jump }: { report: Report; jumps: Record<Role, { start: number; end?: number; nonce: number } | null>; jump: (role: Role, start: number, end?: number) => void }) {
  // 波形与时间轴上下相邻；时间轴卡片复用整段录音播放器，不生成音频切片。
  return <section className="panel" aria-label="证据回听播放器">
    <h3 className="text-lg font-semibold">证据回听 · 双边录音</h3>
    <p className="mt-1 text-sm text-slate-600">点击下方证据卡片会在对应的整段录音中定位播放。波形高度表示振幅，不表示音高；当前播放位置由深色光标显示。</p>
    <div className="mt-4 grid gap-4 lg:grid-cols-2">{(['user', 'benchmark'] as const).map(role => <div key={role} className="min-w-0">
      <Waveform label={role === 'benchmark' && report.samples.benchmark.sample.audio_origin === 'edge_tts' ? 'TTS 练习参考录音' : names[role]} url={`/api/v1/runs/${report.run_id}/audio/${role}`} jump={jumps[role]} height={144} />
      <div className="mt-1 flex justify-between px-2 text-xs text-slate-500"><span>0 秒</span><span>{report.samples[role].audio.duration_s.toFixed(1)} 秒</span></div>
      <details className="mt-2 rounded-lg border border-slate-200 p-3"><summary className="cursor-pointer text-sm font-medium">查看音高与能量曲线（辅助观察）</summary><div className="mt-3"><AcousticPlot data={report.samples[role].acoustic} duration={report.samples[role].audio.duration_s} label={role === 'benchmark' && report.samples.benchmark.sample.audio_origin === 'edge_tts' ? 'TTS 练习参考录音' : names[role]} onSeek={time => jump(role, Math.max(0, time - 0.75), Math.min(report.samples[role].audio.duration_s, time + 0.75))} /></div></details>
    </div>)}</div>
  </section>
}

function EvidenceTimeline({ report, setJump, focusRequest }: { report: Report; setJump: (role: Role, start: number, end?: number) => void; focusRequest: { id: string; nonce: number } | null }) {
  const referenceName = report.samples.benchmark.sample.audio_origin === 'edge_tts' ? 'TTS 练习参考录音' : names.benchmark
  const listRef = useRef<HTMLDivElement>(null)
  const handledFocusRequest = useRef<number | null>(null)
  const [focused, setFocused] = useState(true)
  useEffect(() => {
    if (!focusRequest || handledFocusRequest.current === focusRequest.nonce) return
    // 同一跳转请求只处理一次，否则手动切回红黄词视图会被旧请求再次覆盖。
    if (focused) { setFocused(false); return }
    handledFocusRequest.current = focusRequest.nonce
    const element = Array.from(listRef.current?.querySelectorAll<HTMLElement>('[data-evidence-id]') || [])
      .find(node => node.dataset.evidenceId === focusRequest.id)
    if (element) element.scrollIntoView({ behavior: 'smooth', block: 'center' })
    else document.getElementById('evidence-timeline')?.scrollIntoView({ behavior: 'smooth' })
  }, [focusRequest, focused])
  const allEvidence: { role: Role; item: Evidence }[] = (['user', 'benchmark'] as const).flatMap(role =>
    [...report.samples[role].pronunciation.evidence, ...report.samples[role].fluency.evidence]
      .map(item => ({ role, item })))
  const entries = allEvidence.filter(({ item }) => item.start_s !== null && item.start_s !== undefined)
  const untimedCount = allEvidence.length - entries.length
  const highlightColor = ({ role, item }: { role: Role; item: Evidence }) =>
    role === 'user' && item.kind === 'xingji_word_color' && (item.details.color === 'red' || item.details.color === 'yellow')
      ? String(item.details.color) : null
  const wordFor = (role: Role, item: Evidence) =>
    typeof item.token_index === 'number' ? report.samples[role].sample.tokens[item.token_index]?.surface : undefined
  const labelFor = (role: Role, item: Evidence) => {
    if (item.kind === 'xingji_word_color') {
      const color = { red: '红色', yellow: '黄色', green: '绿色' }[String(item.details.color)] || '未知颜色'
      const source = item.details.review_status === 'candidate' ? '截图候选' : '已确认'
      return `词色：${item.details.surface || wordFor(role, item) || '词'} · ${color}（${source}）`
    }
    if (item.kind === 'phoneme_model_candidate') return `OpenPronounce 音素模型线索：${wordFor(role, item) || '目标词'}（未经校准）`
    if (item.kind === 'speech_window') return '发声时段'
    if (item.kind === 'pause_candidate') return '停顿候选'
    if (item.kind.startsWith('metric_')) return `流利度指标：${metricNames[item.kind.slice(7)] || item.kind.slice(7)}`
    return item.kind
  }
  const pairByUserIndex = new Map(report.comparison.shared_word_pairs.map(pair => [pair.user_index, pair]))
  const focusTokens = report.samples.user.sample.tokens.filter(token =>
    (token.color_review_status === 'confirmed' || token.color_review_status === 'candidate') &&
    (token.color === 'red' || token.color === 'yellow'))
  const context = (role: Role, index: number) => {
    const side = report.samples[role]
    const targetToken = side.sample.tokens[index]
    // 两侧各显示自己的猩际词色；参考侧绿色不再被统一的紫色高亮掩盖。
    const targetColor = targetToken && ['confirmed', 'candidate'].includes(targetToken.color_review_status) ? targetToken.color : 'unknown'
    const colorNames: Record<string, string> = { red: 'red／红', yellow: 'yellow／黄', green: 'green／绿', unknown: 'unknown／未知' }
    const tokens = side.sample.tokens.slice(Math.max(0, index - 3), index + 4)
    const timed = tokens.map(token => side.alignment.tokens.find(time => time.index === token.index))
      .filter(time => time?.quality === 'medium' && time.start_s !== null && time.end_s !== null)
    const targetTime = side.alignment.tokens.find(time => time.index === index)
    const playable = targetTime?.quality === 'medium' && targetTime.start_s !== null && targetTime.end_s !== null
    const start = timed.length ? Math.max(0, timed[0]!.start_s! - 0.2) : 0
    const end = timed.length ? timed[timed.length - 1]!.end_s! + 0.2 : undefined
    const nearby = tokens.filter(token => Math.abs(token.index - index) <= 1)
      .map(token => side.alignment.tokens.find(time => time.index === token.index))
      .filter(time => time?.quality === 'medium' && time.start_s !== null && time.end_s !== null)
    const wordStart = nearby.length ? Math.max(0, Math.min(...nearby.map(time => time!.start_s!)) - 0.12) : 0
    const wordEnd = nearby.length ? Math.max(...nearby.map(time => time!.end_s!)) + 0.12 : undefined
    return <div className="rounded-lg bg-white/80 p-3">
      <p className="text-xs font-semibold text-slate-600">{role === 'benchmark' ? referenceName : names[role]} · {playable ? `${targetTime.start_s!.toFixed(2)}s` : '时间定位不可靠'} · {role === 'benchmark' && report.samples.benchmark.sample.audio_origin === 'edge_tts' ? '合成词位置（无猩际词色）' : <>猩际词色：<span className={`rounded px-1 ${colorStyles[targetColor]}`}>{colorNames[targetColor]}</span>{targetToken?.color_review_status === 'candidate' && '（截图候选）'}</>}</p>
      <p className="mt-1 text-sm leading-7">{tokens.map(token => <span key={token.index} className={token.index === index ? `rounded px-1 font-semibold ${colorStyles[targetColor]}` : ''}>{token.surface}{' '}</span>)}</p>
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2">
        <button type="button" className="text-sm font-medium text-indigo-700 underline disabled:text-slate-400" disabled={!playable || end === undefined} onClick={() => setJump(role, start, end)}>回听这段上下文</button>
        <button type="button" className="text-sm font-medium text-indigo-700 underline disabled:text-slate-400" disabled={!playable || wordEnd === undefined} onClick={() => setJump(role, wordStart, wordEnd)} title="播放目标词及前后各一词；邻词时间不可靠时仅播放可定位部分">回听这个词</button>
      </div>
    </div>
  }
  entries.sort((a, b) => (a.item.start_s || 0) - (b.item.start_s || 0))
  return <section id="evidence-timeline" className="panel scroll-mt-20">
    <h3 className="text-lg font-semibold">证据时间轴</h3>
    <p className="mt-1 text-sm text-slate-600">{focused ? `优先查看我的 ${focusTokens.length} 个红黄词及前后各 3 个词；有共同朗读稿配对时显示 AI 同词及上下文。` : `按录音时间查看全部 ${entries.length} 条可定位证据；我的红词和黄词用对应颜色标出。点击证据回听。证据可信度描述来源可靠程度，不是发音分数。`}{untimedCount > 0 && `另有 ${untimedCount} 条证据没有可靠时间戳，无法精确定位。`}</p>
    <button type="button" aria-pressed={focused} className="mt-3 rounded-lg border border-indigo-300 px-3 py-2 text-sm font-medium text-indigo-700" onClick={() => { setFocused(value => !value); listRef.current?.scrollTo({ top: 0 }) }}>{focused ? '显示全部证据' : '只看红黄词与上下文'}</button>
    {(focused ? focusTokens.length : entries.length) > 0 && <button type="button" className="ml-4 mt-2 text-sm font-medium text-indigo-700 underline" onClick={() => listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })}>跳到录音尾部</button>}
    <div ref={listRef} className="mt-4 max-h-80 space-y-2 overflow-auto">
      {focused ? focusTokens.map(token => {
        const pair = pairByUserIndex.get(token.index)
        const signals = report.samples.user.pronunciation.evidence.filter(item => item.token_index === token.index && item.kind === 'phoneme_model_candidate')
        return <article key={token.index} className={`rounded-lg p-3 ${colorStyles[token.color]}`}>
          <p className="font-semibold">我的{token.color === 'red' ? '红' : '黄'}词：{token.surface}{token.color_review_status === 'candidate' && '（截图候选）'}</p>
          {signals.length > 0 && <p className="mt-1 text-xs">OpenPronounce 音素模型线索（未经校准）</p>}
          <div className="mt-2 grid gap-2 md:grid-cols-2">{context('user', token.index)}{pair ? context('benchmark', pair.benchmark_index) : <p className="rounded-lg bg-white/80 p-3 text-sm text-slate-600">这处词没有可靠配对的 AI 同词录音。</p>}</div>
        </article>
      }) : entries.map(({ role, item }) => {
        const color = highlightColor({ role, item })
        return <button key={item.id} data-evidence-id={item.id} type="button" className={`flex w-full items-center justify-between gap-3 rounded-lg p-3 text-left text-sm hover:ring-2 hover:ring-indigo-200 ${color ? colorStyles[color] : 'bg-slate-50'}`} onClick={() => setJump(role, Math.max(0, (item.start_s || 0) - 0.15), (item.end_s || item.start_s || 0) + 0.15)}>
          <span><strong>{role === 'benchmark' ? referenceName : names[role]}</strong> · {labelFor(role, item)}</span>
          <span className="shrink-0 text-slate-500">{item.start_s?.toFixed(2)}s · 证据可信度：{qualityNames[item.quality] || '未知'}</span>
        </button>
      })}
      {focused && !focusTokens.length && <p className="text-sm text-slate-500">没有可聚焦的红黄词；可切换到全部证据。</p>}
      {!focused && !entries.length && <p className="text-sm text-slate-500">暂无可信时间定位证据。</p>}
    </div>
  </section>
}

function TranscriptCoverage({ report }: { report: Report }) {
  const coverage = report.comparison.transcript_comparison
  if (!coverage) return null
  return <section className="panel"><h3 className="text-lg font-semibold">共同朗读稿与实际转写</h3><p className="mt-1 text-sm text-slate-600">{coverage.basis === 'shared_reading_text' ? `原稿 ${coverage.script_word_count} 词；我匹配 ${coverage.user_matched_script_words} 词，AI 参考匹配 ${coverage.benchmark_matched_script_words} 词；共同位置 ${coverage.shared_script_words} 词。` : '旧记录没有共同朗读稿；仅按两侧转写顺序寻找相同词。'}</p><p className="mt-2 text-sm text-slate-600">转写中的未匹配词：我 {coverage.user_unmatched_transcript_words}，AI 参考 {coverage.benchmark_unmatched_transcript_words}。{coverage.user_script_tail_unobserved !== null && `原稿尾部未见于转写：我 ${coverage.user_script_tail_unobserved} 词，AI 参考 ${coverage.benchmark_script_tail_unobserved} 词。`}</p><p className="mt-2 text-xs text-amber-800">差异可能来自实际朗读、猩际识别或录音截断，不能单凭转写判定发音错误。</p></section>
}

function AnalysisMethods({ report }: { report: Report }) {
  // 从当前不可变报告读取实际运行结果，不把“可安装的 Provider”当成本次已使用的方法。
  const user = report.samples.user
  const benchmark = report.samples.benchmark
  const provider = report.config?.llm_provider && report.config.llm_provider !== 'none' ? report.config.llm_provider : null
  return <details className="panel"><summary className="cursor-pointer text-lg font-semibold">本次实际使用的分析方法与限制</summary>
    <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-6 text-slate-700">
      <li>猩际截图逐词颜色：我的回答红 {user.pronunciation.summary.counts.red}、黄 {user.pronunciation.summary.counts.yellow}；其中截图候选 {user.pronunciation.summary.candidate_count || 0}，候选需要人工复核。</li>
      <li>词级时间对齐：我的回答可信 {user.alignment.trusted_count ?? 0}/{user.alignment.total_count ?? user.sample.tokens.length} 词，参考可信 {benchmark.alignment.trusted_count ?? 0}/{benchmark.alignment.total_count ?? benchmark.sample.tokens.length} 词；未可靠定位的词不强行回听。</li>
      <li>流利度：计算 WPM、词间停顿候选、短语长度和局部语速波动；语音活动检测质量为我的 {qualityNames[user.audio.speech_regions?.quality || 'unavailable'] || '未知'}、参考 {qualityNames[benchmark.audio.speech_regions?.quality || 'unavailable'] || '未知'}。低质量结果只作回听线索。</li>
      <li>音高和能量：{user.acoustic?.status === 'complete' && benchmark.acoustic?.status === 'complete' ? '两侧均已提取展示曲线' : '至少一侧曲线不可用或属于旧报告'}；曲线不参与发音或流利度分数。</li>
      <li>OpenPronounce：{report.config?.pronunciation_provider === 'openpronounce' ? '本次启用未经校准的音素候选' : '本次未启用'}。AI 文字：{provider ? `本次请求 ${provider}，各段实际来源在总结旁标出` : '本次只使用本机规则'}。</li>
    </ul>
  </details>
}

function FluencyPanel({ report }: { report: Report }) {
  const missing = fluencyMissingExplanation(report)
  const summary = report.summaries?.fluency
  return <section className="panel"><h3 className="text-lg font-semibold">流利度对比</h3>
    <p className="mt-1 text-sm text-slate-600">两侧按同一算法计算；实际词数与录音尾部可能不同。{report.samples.benchmark.sample.audio_origin === 'edge_tts' && ' TTS 分段接缝附近的停顿已排除出候选；整体 WPM 仍包含分段间隔。'}</p>
    <div className="mt-3 rounded-lg bg-slate-50 p-3 text-sm text-slate-700"><p>“无法判断”及旧报告的 unavailable 表示本次没有可靠测量，并非缺少 API key。质量高/中/低表示证据可靠程度。</p>{missing.map(line => <p key={line} className="mt-1">{line}</p>)}</div>
    <div className="mt-4 overflow-x-auto"><table className="w-full min-w-[45rem] text-left text-sm"><thead><tr className="border-b border-slate-200 text-slate-500"><th className="py-2">指标</th><th>我的回答</th><th>Benchmark</th><th>差值</th><th>质量</th></tr></thead><tbody>{Object.entries(report.comparison.fluency_metric_differences).map(([key, item]) => <tr key={key} className="border-b border-slate-100"><th className="py-2 font-medium">{metricNames[key] || key}</th><td>{display(item.user.value, item.user.unit)}</td><td>{display(item.benchmark.value, item.benchmark.unit)}</td><td>{item.delta_user_minus_benchmark === null ? '—' : item.delta_user_minus_benchmark.toFixed(2)}</td><td className={item.quality === 'low' ? 'text-amber-700' : 'text-slate-500'}>{qualityNames[item.quality] || item.quality}</td></tr>)}</tbody></table></div>
    <div className="mt-4 rounded-lg bg-indigo-50 p-4 text-sm leading-6 text-indigo-950"><p className="font-semibold">{summary?.source === 'ai' ? 'AI 基于本次指标的总结' : '本机基于本次指标的总结'}</p><p className="mt-1">{summary?.text || fluencySummary(report)}</p>{summary && <details className="mt-2 text-xs"><summary className="cursor-pointer">查看指标读法与差值说明</summary><p className="mt-1">{fluencySummary(report)}</p></details>}{report.summaries?.fallback_reason && <p className="mt-1 text-xs">AI 调用或校验未通过，已保留本机总结。</p>}</div>
  </section>
}

function SharedWords({ report }: { report: Report }) {
  const isTTS = report.samples.benchmark.sample.audio_origin === 'edge_tts'
  return <section className="panel"><h3 className="text-lg font-semibold">共享词 A/B</h3><p className="mt-1 text-sm text-slate-600">按共同朗读稿的位置比较同一词。未配对和尾部差异不自动算发音问题。{isTTS && ' TTS 侧可回听同词，但没有猩际词色。'}</p><div className="mt-4 flex max-h-64 flex-wrap gap-2 overflow-auto">{report.comparison.shared_word_pairs.map((pair, index) => <div key={`${pair.user_index}-${pair.benchmark_index}-${index}`} className={`rounded-lg border border-slate-200 px-3 py-2 text-sm ${pair.user_color === 'red' ? 'bg-red-100' : pair.user_color === 'yellow' ? 'bg-amber-100' : ''}`}><strong>{pair.word}</strong><span className="ml-3 text-slate-600">我 {pair.user_color} · {isTTS ? 'TTS 无词色' : `高分 ${pair.benchmark_color}`}</span></div>)}{!report.comparison.shared_word_pairs.length && <p className="text-slate-500">没有可比较的共享词。</p>}</div></section>
}

function TrainingPriorities({ report, onFocusEvidence }: { report: Report; onFocusEvidence: (id: string) => void }) {
  const providerName = report.config?.llm_provider === 'openai_compatible' ? 'CLIProxyAPI' : 'OpenAI'
  const status = report.diagnosis.llm_status
  const origin = status === 'used' ? `${providerName} 已改写文字`
    : status === 'unchanged' ? `${providerName} 已调用，文字未变化`
    : status === 'fallback_to_rules' ? `${providerName} 结果未采用，已使用本机规则`
    : '本机规则（未调用 AI）'
  const originals = new Map(report.diagnosis.rule_findings?.map(item => [item.id, item]) || [])
  return <section className="panel">
    <h3 className="text-lg font-semibold">训练优先事项</h3>
    <p className="mt-1 text-sm text-slate-600">由独立证据生成，最多三项。文字来源：{origin}。AI 不更改测量或评分。</p>
    <div className="mt-4 space-y-4">
      {report.diagnosis.findings.map((finding, index) => {
        const original = originals.get(finding.id)
        const card = report.diagnosis.teaching_cards?.find(item => item.finding_id === finding.id)
        return <article key={finding.id} className="rounded-xl bg-indigo-50 p-4">
          <div className="flex justify-between gap-3"><h4 className="font-semibold">{index + 1}. {finding.statement}</h4><span className="text-xs text-indigo-700">可信度：{finding.confidence_level}</span></div>
          {card ? <div className="mt-3 grid gap-2 text-sm leading-6 text-slate-700">
            <p><strong>观察：</strong>{card.observation}</p>
            {!!card.evidence_examples?.length && <p><strong>本次证据：</strong>{card.evidence_examples.join('、')}</p>}
            <p><strong>可能解释：</strong>{card.interpretation}</p>
            <p><strong>怎么练：</strong>{card.practice}</p>
            <p><strong>下次检查：</strong>{card.next_check}</p>
          </div> : <p className="mt-2 text-sm text-slate-700">{finding.recommendation}</p>}
          <p className="mt-2 text-xs text-slate-500">证据 {finding.evidence_ids.length} 项 · {finding.limitations.join(' ')}</p>
          {finding.evidence_ids.length > 0 && <button type="button" className="mt-2 text-sm font-medium text-indigo-700 underline" onClick={() => onFocusEvidence(finding.evidence_ids[0])}>在时间轴查看相关证据</button>}
          {status === 'used' && original && <details className="mt-3 text-sm text-slate-600">
            <summary className="cursor-pointer">查看改写前的本机建议</summary>
            <p className="mt-2">问题：{original.statement}</p>
            <p className="mt-1">建议：{original.recommendation}</p>
          </details>}
        </article>
      })}
      {!report.diagnosis.findings.length && <p className="text-slate-600">当前可用证据不足以生成训练结论。请先复核词色或检查对齐质量。</p>}
    </div>
  </section>
}

function TeachingLibrary({ report }: { report: Report }) {
  // 新报告展示证据绑定的总结；旧报告仍可由原有 findings 生成保守的本机回退。
  const summary = report.summaries?.practice
  const legacyText = report.diagnosis.findings.length ? report.diagnosis.findings.slice(0, 2).map(item => item.recommendation).join(' ') : '这份历史报告没有足够的个性化训练证据。'
  return <section className="panel"><h3 className="text-lg font-semibold">发音与节奏分析</h3>
    <div className="mt-3 rounded-lg bg-indigo-50 p-4 text-sm leading-7 text-indigo-950"><p className="font-semibold">{summary?.source === 'ai' ? 'AI 基于本次证据的总结' : '本机基于本次证据的总结'}</p><p className="mt-1">{summary?.text || legacyText}</p>{report.summaries?.fallback_reason && <p className="mt-1 text-xs">AI 调用或校验未通过，已保留本机总结。</p>}</div>
    <details className="mt-4"><summary className="cursor-pointer text-sm font-medium text-slate-700">查看通用练习方法</summary>
    <p className="mt-2 text-sm text-slate-600">以下是自主练习参考，不是对本次录音中具体音素错误的诊断。</p>
    <div className="mt-4 grid gap-3 md:grid-cols-2 text-sm leading-6">
      <div className="rounded-lg bg-slate-50 p-3"><strong>元音对比</strong><p>选一组容易混淆的词，先听辨，再在短句中录两遍；关注听者能否区分词义，避免仅凭时长判定元音。</p></div>
      <div className="rounded-lg bg-slate-50 p-3"><strong>辅音与词尾</strong><p>回听词尾是否仍容易辨认，先在短语中练，再放回完整句子；不要把识别器漏词直接当作漏发辅音。</p></div>
      <div className="rounded-lg bg-slate-50 p-3"><strong>信息重点</strong><p>先划出句子要传达的关键词，尝试用自然的节奏突出重点；功能词也可能在对比或纠正时被强调。</p></div>
      <div className="rounded-lg bg-slate-50 p-3"><strong>意群与停顿</strong><p>按意思分段回听，判断停顿是否帮助理解。长停顿不一定是错误，重点看位置、上下文和整句是否连贯。</p></div>
    </div></details>
  </section>
}

export default function ReportView({ report }: { report: Report }) {
  const [jumps, setJumps] = useState<Record<Role, { start: number; end?: number; nonce: number } | null>>({ user: null, benchmark: null })
  const [focusRequest, setFocusRequest] = useState<{ id: string; nonce: number } | null>(null)
  useEffect(() => {
    // 切换历史报告时清除上一份报告的回听区间与证据跳转。
    setJumps({ user: null, benchmark: null })
    setFocusRequest(null)
  }, [report.run_id])
  const jump = (role: Role, start: number, end?: number) => setJumps(previous => ({ ...previous, [role]: { start, end, nonce: Date.now() + Math.random() } }))
  return <div className="space-y-6">
    <nav aria-label="报告快捷入口" className="sticky top-2 z-20 flex justify-end">
      <a href="#evidence-timeline" className="rounded-full bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-lg hover:bg-indigo-700">查看证据时间轴 ↓</a>
    </nav>
    <div className={`rounded-xl p-4 text-sm ${report.status === 'complete' ? 'bg-emerald-50 text-emerald-800' : 'bg-amber-50 text-amber-900'}`}>报告状态：{report.status === 'complete' ? '完整' : '部分完成'}。低质量或缺失的测量不会被当作已证实的发音问题。{report.samples.benchmark.sample.audio_origin === 'edge_tts' && ' 右侧是在线合成的练习参考，不代表猩际高分表现。'}</div>
    <div className="grid gap-6 lg:grid-cols-2">{(['user', 'benchmark'] as const).map(role => <SidePanel key={role} role={role} side={report.samples[role]} setJump={value => setJumps(previous => ({ ...previous, [role]: value }))} />)}</div>
    <PlaybackDock report={report} jumps={jumps} jump={jump} />
    <EvidenceTimeline report={report} setJump={jump} focusRequest={focusRequest} />
    <TranscriptCoverage report={report} />
    <AnalysisMethods report={report} />
    <FluencyPanel report={report} />
    <SharedWords report={report} />
    <TrainingPriorities report={report} onFocusEvidence={id => setFocusRequest({ id, nonce: Date.now() + Math.random() })} />
    <TeachingLibrary report={report} />
  </div>
}
