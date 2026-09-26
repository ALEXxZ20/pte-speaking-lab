import { useState } from 'react'
import type { Evidence, Report, SideResult } from '../api/client'
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

function SidePanel({ side, role, report, jump, setJump }: { side: SideResult; role: Role; report: Report; jump: { start: number; end?: number; nonce: number } | null; setJump: (jump: { start: number; end?: number; nonce: number }) => void }) {
  const scores = side.sample
  const counts = side.pronunciation.summary.counts
  return <section className="panel space-y-5"><div><p className="eyebrow">{role === 'user' ? 'User' : 'Benchmark'}</p><h3 className="mt-1 text-xl font-semibold">{names[role]}</h3><p className="mt-1 text-sm text-slate-600">对齐 {side.alignment.trusted_count ?? 0}/{side.alignment.total_count ?? side.sample.tokens.length} 词 · 录音 {side.audio.duration_s.toFixed(1)} 秒</p></div><div className="grid grid-cols-3 gap-2">{([['发音', scores.pronunciation_score], ['流利度', scores.fluency_score], ['内容', scores.content_score]] as const).map(([name, score]) => <div key={name} className="rounded-xl bg-slate-50 p-3 text-center"><p className="text-xs text-slate-500">猩际{name}</p><p className="mt-1 font-semibold">{score ? `${score.value}/${score.max}` : '未提供'}</p></div>)}</div><Waveform label={names[role]} url={`/api/v1/runs/${report.run_id}/audio/${role}`} jump={jump} /><div><h4 className="font-semibold">逐词颜色</h4><p className="mt-1 text-sm text-slate-600">红 {counts.red} · 黄 {counts.yellow} · 绿 {counts.green} · <span className="font-semibold text-red-700" title="未知词需要手动复核">! 未知 {side.pronunciation.summary.unknown_count}（请手动复核）</span> · 截图候选 {side.pronunciation.summary.candidate_count || 0}</p><div className="mt-3 flex max-h-40 flex-wrap gap-1.5 overflow-auto">{side.sample.tokens.map(token => { const time = side.alignment.tokens[token.index]; const known = token.color_review_status === 'confirmed' || token.color_review_status === 'candidate' ? token.color : 'unknown'; return <button key={token.index} type="button" disabled={!time || time.quality !== 'medium' || time.start_s === null} onClick={() => setJump({ start: Math.max(0, time.start_s! - 0.2), end: (time.end_s || time.start_s!) + 0.2, nonce: Date.now() })} className={`rounded-md px-2 py-1 text-sm disabled:cursor-not-allowed ${colorStyles[known]}`} title={`${token.color_review_status === 'candidate' ? '截图候选，待人工复核；' : ''}${time?.quality === 'medium' ? '点击回听词片段' : '时间定位不可靠'}`}>{token.surface}</button> })}</div></div></section>
}

function EvidenceTimeline({ report, setJump }: { report: Report; setJump: (role: Role, start: number, end?: number) => void }) {
  const entries: { role: Role; item: Evidence }[] = (['user', 'benchmark'] as const).flatMap(role => [...report.samples[role].pronunciation.evidence, ...report.samples[role].fluency.evidence].filter(item => item.start_s !== null && item.start_s !== undefined).map(item => ({ role, item })))
  const highlightColor = ({ role, item }: { role: Role; item: Evidence }) => role === 'user' && item.kind === 'xingji_word_color' && (item.details.color === 'red' || item.details.color === 'yellow') ? String(item.details.color) : null
  entries.sort((a, b) => (a.item.start_s || 0) - (b.item.start_s || 0))
  return <section className="panel"><h3 className="text-lg font-semibold">证据时间轴</h3><p className="mt-1 text-sm text-slate-600">按录音时间查看两侧证据；我的红词和黄词用对应颜色标出。点击证据回听；“低质量”只作核查线索。</p><div className="mt-4 max-h-80 space-y-2 overflow-auto">{entries.slice(0, 120).map(({ role, item }) => <button key={item.id} type="button" className={`flex w-full items-center justify-between gap-3 rounded-lg p-3 text-left text-sm hover:ring-2 hover:ring-indigo-200 ${highlightColor({ role, item }) ? colorStyles[highlightColor({ role, item })!] : 'bg-slate-50'}`} onClick={() => setJump(role, Math.max(0, (item.start_s || 0) - 0.15), (item.end_s || item.start_s || 0) + 0.15)}><span><strong>{names[role]}</strong> · {item.kind === 'xingji_word_color' ? `${item.details.surface || '词'} · ${item.details.color || ''}${item.details.review_status === 'candidate' ? '（截图候选）' : ''}` : item.kind === 'pause_candidate' ? '停顿候选' : item.kind}</span><span className="shrink-0 text-slate-500">{item.start_s?.toFixed(2)}s · {item.quality}</span></button>)}{!entries.length && <p className="text-sm text-slate-500">暂无可信时间定位证据。</p>}</div></section>
}

function TranscriptCoverage({ report }: { report: Report }) {
  const coverage = report.comparison.transcript_comparison
  if (!coverage) return null
  return <section className="panel"><h3 className="text-lg font-semibold">共同朗读稿与实际转写</h3><p className="mt-1 text-sm text-slate-600">{coverage.basis === 'shared_reading_text' ? `原稿 ${coverage.script_word_count} 词；我匹配 ${coverage.user_matched_script_words} 词，AI 参考匹配 ${coverage.benchmark_matched_script_words} 词；共同位置 ${coverage.shared_script_words} 词。` : '旧记录没有共同朗读稿；仅按两侧转写顺序寻找相同词。'}</p><p className="mt-2 text-sm text-slate-600">转写中的未匹配词：我 {coverage.user_unmatched_transcript_words}，AI 参考 {coverage.benchmark_unmatched_transcript_words}。{coverage.user_script_tail_unobserved !== null && `原稿尾部未见于转写：我 ${coverage.user_script_tail_unobserved} 词，AI 参考 ${coverage.benchmark_script_tail_unobserved} 词。`}</p><p className="mt-2 text-xs text-amber-800">差异可能来自实际朗读、猩际识别或录音截断，不能单凭转写判定发音错误。</p></section>
}

function FluencyPanel({ report }: { report: Report }) {
  return <section className="panel"><h3 className="text-lg font-semibold">流利度对比</h3>
    <p className="mt-1 text-sm text-slate-600">两侧按同一算法计算；实际词数与录音尾部可能不同。</p>
    <p className="mt-3 rounded-lg bg-slate-50 p-3 text-sm text-slate-700">“无法判断”和旧报告中的 unavailable 表示没有可靠测量：词级时间缺失时请配置对齐，录音质量不足时请重新录制；重复、重启、填充词目前无法可靠检测，没有可开启的配置。质量高/中/低表示证据可靠程度，低质量请结合回听。</p>
    <div className="mt-4 overflow-x-auto"><table className="w-full min-w-[45rem] text-left text-sm"><thead><tr className="border-b border-slate-200 text-slate-500"><th className="py-2">指标</th><th>我的回答</th><th>Benchmark</th><th>差值</th><th>质量</th></tr></thead><tbody>{Object.entries(report.comparison.fluency_metric_differences).map(([key, item]) => <tr key={key} className="border-b border-slate-100"><th className="py-2 font-medium">{metricNames[key] || key}</th><td>{display(item.user.value, item.user.unit)}</td><td>{display(item.benchmark.value, item.benchmark.unit)}</td><td>{item.delta_user_minus_benchmark === null ? '—' : item.delta_user_minus_benchmark.toFixed(2)}</td><td className={item.quality === 'low' ? 'text-amber-700' : 'text-slate-500'}>{qualityNames[item.quality] || item.quality}</td></tr>)}</tbody></table></div>
    <p className="mt-4 rounded-lg bg-indigo-50 p-4 text-sm leading-6 text-indigo-950">{fluencySummary(report)}</p>
  </section>
}

function SharedWords({ report }: { report: Report }) {
  return <section className="panel"><h3 className="text-lg font-semibold">共享词 A/B</h3><p className="mt-1 text-sm text-slate-600">按共同朗读稿的位置比较同一词。未配对和尾部差异不自动算发音问题。</p><div className="mt-4 flex max-h-64 flex-wrap gap-2 overflow-auto">{report.comparison.shared_word_pairs.map((pair, index) => <div key={`${pair.user_index}-${pair.benchmark_index}-${index}`} className={`rounded-lg border border-slate-200 px-3 py-2 text-sm ${pair.user_color === 'red' ? 'bg-red-100' : pair.user_color === 'yellow' ? 'bg-amber-100' : ''}`}><strong>{pair.word}</strong><span className="ml-3 text-slate-600">我 {pair.user_color} · 高分 {pair.benchmark_color}</span></div>)}{!report.comparison.shared_word_pairs.length && <p className="text-slate-500">没有可比较的共享词。</p>}</div></section>
}

export default function ReportView({ report }: { report: Report }) {
  const [jumps, setJumps] = useState<Record<Role, { start: number; end?: number; nonce: number } | null>>({ user: null, benchmark: null })
  const jump = (role: Role, start: number, end?: number) => setJumps(previous => ({ ...previous, [role]: { start, end, nonce: Date.now() + Math.random() } }))
  return <div className="space-y-6"><div className={`rounded-xl p-4 text-sm ${report.status === 'complete' ? 'bg-emerald-50 text-emerald-800' : 'bg-amber-50 text-amber-900'}`}>报告状态：{report.status === 'complete' ? '完整' : '部分完成'}。低质量或缺失的测量不会被当作已证实的发音问题。</div><div className="grid gap-6 lg:grid-cols-2">{(['user', 'benchmark'] as const).map(role => <SidePanel key={role} role={role} side={report.samples[role]} report={report} jump={jumps[role]} setJump={value => setJumps(previous => ({ ...previous, [role]: value }))} />)}</div><TranscriptCoverage report={report} /><FluencyPanel report={report} /><SharedWords report={report} /><EvidenceTimeline report={report} setJump={jump} /><section className="panel"><h3 className="text-lg font-semibold">训练优先事项</h3><p className="mt-1 text-sm text-slate-600">由独立证据生成，最多三项。解释来源：{report.diagnosis.llm_status === 'used' ? 'OpenAI 辅助改写' : '本机规则'}。</p><div className="mt-4 space-y-4">{report.diagnosis.findings.map((finding, index) => <article key={finding.id} className="rounded-xl bg-indigo-50 p-4"><div className="flex justify-between gap-3"><h4 className="font-semibold">{index + 1}. {finding.statement}</h4><span className="text-xs text-indigo-700">{finding.confidence_level}</span></div><p className="mt-2 text-sm text-slate-700">{finding.recommendation}</p><p className="mt-2 text-xs text-slate-500">证据 {finding.evidence_ids.length} 项 · {finding.limitations.join(' ')}</p></article>)}{!report.diagnosis.findings.length && <p className="text-slate-600">当前可用证据不足以生成训练结论。请先复核词色或检查对齐质量。</p>}</div></section></div>
}
