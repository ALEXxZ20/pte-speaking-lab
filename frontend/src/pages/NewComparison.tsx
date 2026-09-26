import { useEffect, useState, type FormEvent } from 'react'
import { createComparison, importScreenshot, upload, type Comparison, type Draft, type Sample, type SampleRecord, updateSample } from '../api/client'

type Role = 'user' | 'benchmark'
type FormSide = { audio: File | null; screenshot: File | null; transcript: string; pronunciation: string; fluency: string; content: string }
const empty = (): FormSide => ({ audio: null, screenshot: null, transcript: '', pronunciation: '', fluency: '', content: '' })
const names: Record<Role, string> = { user: '我的回答', benchmark: 'AI 生成的高分参考录音' }
const colors = { red: '红色', yellow: '黄色', green: '绿色', unknown: '未知' }

function ScoreField({ label, value, max, change }: { label: string; value: string; max: string; change: (value: string) => void }) {
  return <label className="block text-sm text-slate-700"><span className="font-medium">{label}</span><span className="mt-1 flex items-center gap-2"><input className="field w-24" type="number" min="0" max={max} step="0.1" value={value} onChange={event => change(event.target.value)} required /><span className="text-slate-500">/ {max}</span></span></label>
}

function SampleForm({ role, value, change }: { role: Role; value: FormSide; change: (next: FormSide) => void }) {
  const set = (field: keyof FormSide, next: string | File | null) => change({ ...value, [field]: next })
  return <section className="panel space-y-5"><div><p className="text-xs font-semibold uppercase tracking-widest text-indigo-600">{role === 'user' ? '01' : '02'} · Response Sample</p><h2 className="mt-1 text-xl font-semibold">{names[role]}</h2>{role === 'benchmark' && <p className="mt-1 text-sm text-slate-600">上传已生成的 AI 音频，以及这段音频在猩际 PTE 得到的转写、截图和三项分数。本项目不生成朗读音频。</p>}</div>
    <label className="block text-sm font-medium">录音文件 <span className="text-red-600">*</span><input className="file-field mt-2" type="file" accept="audio/*,.m4a,.mp4,.webm,.wav,.mp3" onChange={event => set('audio', event.target.files?.[0] || null)} /></label>
    <label className="block text-sm font-medium">猩际逐词颜色截图 <span className="text-red-600">*</span><input className="file-field mt-2" type="file" accept="image/png,image/jpeg" onChange={event => set('screenshot', event.target.files?.[0] || null)} /></label>
    <label className="block text-sm font-medium">复制的猩际转写 <span className="text-red-600">*</span><textarea className="field mt-2 min-h-40 w-full resize-y" value={value.transcript} onChange={event => set('transcript', event.target.value)} placeholder="在猩际复制完整转写，粘贴到这里" /></label>
    <div className="grid grid-cols-3 gap-3"><ScoreField label="Pronunciation" value={value.pronunciation} max="90" change={next => set('pronunciation', next)} /><ScoreField label="Fluency" value={value.fluency} max="90" change={next => set('fluency', next)} /><ScoreField label="Content" value={value.content} max="5" change={next => set('content', next)} /></div>
  </section>
}

export function ReviewPanel({ record, draft, onSaved }: { record: SampleRecord; draft: Draft | null; onSaved: (next: SampleRecord) => void }) {
  const initial = record.sample.tokens.map(token => ({ color: token.color, confirmed: token.color_review_status === 'confirmed' }))
  const [choices, setChoices] = useState(() => draft ? draft.tokens.map((token, index) => ({ color: (initial[index]?.confirmed ? initial[index].color : token.candidate_color), confirmed: initial[index]?.confirmed || false })) : initial)
  useEffect(() => {
    if (!draft) return
    setChoices(draft.tokens.map((token, index) => {
      const saved = record.sample.tokens[index]
      const confirmed = saved?.color_review_status === 'confirmed'
      return { color: confirmed ? saved.color : token.candidate_color, confirmed }
    }))
  }, [draft, record.id])
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const setChoice = (index: number, color: Sample['tokens'][number]['color']) => setChoices(previous => previous.map((item, i) => i === index ? { color, confirmed: color !== 'unknown' } : item))
  const confirmAll = () => setChoices(previous => previous.map(item => ({ ...item, confirmed: item.color !== 'unknown' })))
  async function save() {
    setSaving(true); setMessage('')
    try {
      const sample: Sample = { ...record.sample, tokens: record.sample.tokens.map((token, index) => ({ ...token,
        color: choices[index]?.confirmed ? choices[index].color : 'unknown',
        color_review_status: choices[index]?.confirmed ? 'confirmed' : 'unreviewed',
        color_source_screenshot_id: choices[index]?.confirmed ? record.sample.color_screenshot_asset_ids[0] : null,
      })) }
      const result = await updateSample(record, sample)
      onSaved(result)
      setMessage('复核结果已保存。')
    } catch (error) { setMessage(error instanceof Error ? error.message : '保存失败') }
    finally { setSaving(false) }
  }
  return <section className="panel"><div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="text-lg font-semibold">{names[record.sample.role]} · 词色复核</h3><p className="mt-1 text-sm text-slate-600">{draft ? `识别 ${draft.candidate_count} 词，尚未人工确认 ${choices.filter(choice => !choice.confirmed).length} 词` : '暂无截图映射草稿'}</p></div><div className="flex gap-2"><button type="button" className="button-secondary" onClick={confirmAll} disabled={!draft}>确认全部可识别词</button><button type="button" className="button-primary" onClick={save} disabled={saving}>{saving ? '保存中…' : '保存复核'}</button></div></div>
    {message && <p role="status" className="mt-3 text-sm text-indigo-700">{message}</p>}
    <div className="mt-5 grid gap-5 lg:grid-cols-2"><div className="max-h-[36rem] overflow-auto rounded-xl bg-slate-100 p-2">{record.sample.color_screenshot_asset_ids[0] ? <img className="mx-auto max-w-full" src={`/api/v1/assets/screenshots/${record.sample.color_screenshot_asset_ids[0]}`} alt={`${names[record.sample.role]}猩际逐词颜色原图`} /> : '无截图'}</div><div className="max-h-[36rem] space-y-2 overflow-auto pr-2">{record.sample.tokens.map((token, index) => <label key={token.index} className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 p-2 text-sm"><span className="min-w-0 flex-1 truncate"><span className="mr-2 text-slate-400">{index + 1}</span>{token.surface}</span><select className="rounded-md border border-slate-300 p-1" aria-label={`${token.surface} 的颜色`} value={choices[index]?.color || 'unknown'} onChange={event => setChoice(index, event.target.value as Sample['tokens'][number]['color'])}>{Object.entries(colors).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select><span className={choices[index]?.confirmed ? 'text-emerald-700' : 'text-amber-700'}>{choices[index]?.confirmed ? '已确认' : '待确认'}</span></label>)}</div></div>
    <p className="mt-4 text-sm text-slate-500">截图没有可靠的停顿标签时会显示“不可用”；不能把空标签当成零次停顿。保存后，未确认词仍为未知。</p>
  </section>
}

export default function NewComparison() {
  const [title, setTitle] = useState('')
  const [questionType, setQuestionType] = useState('DI')
  const [readingText, setReadingText] = useState('')
  const [sides, setSides] = useState<Record<Role, FormSide>>({ user: empty(), benchmark: empty() })
  const [comparison, setComparison] = useState<Comparison | null>(null)
  const [drafts, setDrafts] = useState<Record<Role, Draft | null>>({ user: null, benchmark: null })
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  function score(value: string, max: number) { return value.trim() ? { value: Number(value), max } : null }
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!readingText.trim() || Object.values(sides).some(side => !side.audio || !side.screenshot || !side.transcript.trim() || !side.pronunciation || !side.fluency || !side.content)) { setMessage('请填写共同朗读稿，并为两侧提供录音、截图、猩际实际转写和三项分数。'); return }
    setBusy(true); setMessage('正在上传并保存双边样本…')
    try {
      const roles: Role[] = ['user', 'benchmark']
      const uploads = await Promise.all(roles.map(async role => ({ role, audio: await upload('audio', sides[role].audio!), screenshot: await upload('screenshots', sides[role].screenshot!) })))
      const body = { exercise: { question_type: questionType, title: title || null, reading_text_raw: readingText }, samples: uploads.map(({ role, audio, screenshot }) => ({ role, audio_origin: role === 'user' ? 'human_recording' : 'ai_generated', audio_asset_id: audio.id, color_screenshot_asset_ids: [screenshot.id], transcript_raw: sides[role].transcript, transcript_source: 'xingji_copy', pronunciation_score: score(sides[role].pronunciation, 90), fluency_score: score(sides[role].fluency, 90), content_score: score(sides[role].content, 5) })) }
      const created = await createComparison(body)
      setComparison(created)
      setMessage('双边样本已保存，正在生成截图词色草稿…')
      const results = await Promise.all(uploads.map(async ({ role, screenshot }) => ({ role, result: await importScreenshot(created.samples[role].id, screenshot.id) })))
      setDrafts(Object.fromEntries(results.map(({ role, result }) => [role, result.draft])) as Record<Role, Draft>)
      setMessage('截图草稿已生成。请并排核对颜色，然后分别保存两侧复核结果。')
    } catch (error) { setMessage(error instanceof Error ? error.message : '保存失败，请重试') }
    finally { setBusy(false) }
  }
  return <div className="space-y-8"><div><p className="eyebrow">新建比较</p><h1 className="page-title">比较同一朗读稿的两份录音</h1><p className="page-subtitle">一侧是你的录音，一侧是已生成并获得猩际评分的 AI 高分录音。两侧实际转写可有个别词和尾部差异；请分别粘贴原文。颜色由截图生成草稿后复核。</p></div>
    {!comparison ? <form onSubmit={submit} className="space-y-6"><div className="panel grid gap-4 sm:grid-cols-2"><label className="text-sm font-medium">题型<input className="field mt-2 w-full" value={questionType} onChange={event => setQuestionType(event.target.value)} required /></label><label className="text-sm font-medium">题目名称或编号（可选）<input className="field mt-2 w-full" value={title} onChange={event => setTitle(event.target.value)} /></label><label className="text-sm font-medium sm:col-span-2">两侧计划朗读的共同原文 <span className="text-red-600">*</span><textarea className="field mt-2 min-h-36 w-full resize-y" value={readingText} onChange={event => setReadingText(event.target.value)} placeholder="粘贴原本希望两侧都朗读的完整文本；不要用猩际转写替代" required /></label></div><div className="grid gap-6 lg:grid-cols-2">{(['user', 'benchmark'] as const).map(role => <SampleForm key={role} role={role} value={sides[role]} change={next => setSides(previous => ({ ...previous, [role]: next }))} />)}</div><button className="button-primary" disabled={busy}>{busy ? '处理中…' : '保存双边样本并识别词色'}</button></form> : <div className="space-y-6"><p className="rounded-xl bg-emerald-50 p-4 text-sm text-emerald-800">双边样本已保存。比较编号：{comparison.id}</p>{(['user', 'benchmark'] as const).map(role => <ReviewPanel key={role} record={comparison.samples[role]} draft={drafts[role]} onSaved={next => setComparison(previous => previous && ({ ...previous, samples: { ...previous.samples, [role]: next } }))} />)}<a className="button-primary inline-block" href={`/comparisons/${comparison.id}`}>查看比较</a></div>}
    {message && <p role="status" className="rounded-xl bg-indigo-50 p-4 text-sm text-indigo-800">{message}</p>}
  </div>
}
