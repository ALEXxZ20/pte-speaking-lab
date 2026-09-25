import { useEffect, useState } from 'react'
import { deleteComparison, getComparison, getImports, getProviders, getReport, listRuns, previewDeletion, startRun, type Comparison, type Draft, type Report } from '../api/client'
import { ReviewPanel } from './NewComparison'
import ReportView from './ReportView'

type RunSummary = { id: string; status: string; started_at: string }

export default function ComparisonDetail({ id }: { id: string }) {
  const [comparison, setComparison] = useState<Comparison | null>(null)
  const [drafts, setDrafts] = useState<{ user: Draft | null; benchmark: Draft | null }>({ user: null, benchmark: null })
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [report, setReport] = useState<Report | null>(null)
  const [provider, setProvider] = useState<{ openai_key_configured: boolean; openai_model: string | null } | null>(null)
  const [cloud, setCloud] = useState(false)
  const [phonemes, setPhonemes] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    Promise.all([getComparison(id), listRuns(id), getProviders()]).then(async ([result, runList, settings]) => {
      setComparison(result); setRuns(runList); setProvider(settings)
      const [user, benchmark] = await Promise.all([getImports(result.samples.user.id), getImports(result.samples.benchmark.id)])
      setDrafts({ user: user.at(-1)?.draft || null, benchmark: benchmark.at(-1)?.draft || null })
      const latest = runList.find(run => ['complete', 'partial'].includes(run.status))
      if (latest) setReport(await getReport(latest.id))
    }).catch(reason => setError(String(reason)))
  }, [id])
  async function analyze() {
    setBusy(true); setError('')
    try {
      const result = await startRun(id, { allow_cloud: cloud, use_openpronounce: phonemes })
      const [newReport, runList] = await Promise.all([getReport(result.run_id), listRuns(id)])
      setReport(newReport); setRuns(runList)
    } catch (reason) { setError(String(reason)) }
    finally { setBusy(false) }
  }
  async function remove() {
    setBusy(true); setError('')
    try {
      const preview = await previewDeletion(id)
      const description = `将删除此比较、${preview.sample_count} 份样本、${preview.run_count} 份报告，以及 ${preview.audio_file_count} 个录音和 ${preview.screenshot_file_count} 张截图。${preview.preserved_shared_assets ? `另有 ${preview.preserved_shared_assets} 个共享文件会保留。` : ''}\n\n专属文件：\n${preview.files.join('\n') || '无'}\n\n确定删除吗？`
      if (!window.confirm(description)) return
      const result = await deleteComparison(id)
      if (result.file_cleanup_pending.length) setError('记录已删除，但部分文件清理失败。请检查本地数据目录。')
      else window.location.assign('/history')
    } catch (reason) { setError(String(reason)) }
    finally { setBusy(false) }
  }
  if (error && !comparison) return <p role="alert" className="rounded-xl bg-red-50 p-5 text-red-800">{error}</p>
  if (!comparison) return <p>正在读取样本…</p>
  return <div className="space-y-6"><div><p className="eyebrow">比较记录 · {comparison.exercise.question_type}</p><h1 className="page-title">{comparison.exercise.title || '未命名题目'}</h1><p className="page-subtitle">两份回答独立分析；benchmark 只是高分表现的参考。</p></div><section className="panel"><div className="flex flex-wrap items-center justify-between gap-5"><div><h2 className="text-lg font-semibold">运行分析</h2><p className="mt-1 text-sm text-slate-600">新运行会锁定当前两侧样本版本，旧报告保持可追溯。</p></div><button type="button" onClick={analyze} disabled={busy} className="button-primary">{busy ? '正在分析，请稍候…' : report ? '重新分析' : '开始分析'}</button></div><div className="mt-4 flex flex-wrap gap-5 text-sm"><label className="flex items-center gap-2"><input type="checkbox" checked={phonemes} onChange={event => setPhonemes(event.target.checked)} />启用本地 OpenPronounce 音素候选（较慢）</label><label className="flex items-center gap-2"><input type="checkbox" checked={cloud} disabled={!provider?.openai_key_configured || !provider?.openai_model} onChange={event => setCloud(event.target.checked)} />允许 OpenAI 改写训练建议（发送所需证据）</label></div><p className="mt-2 text-xs text-slate-500">OpenAI：{provider?.openai_key_configured && provider.openai_model ? `已配置 ${provider.openai_model}` : '未配置独立 API key 或模型，本机规则仍可运行'}</p>{runs.length > 0 && <label className="mt-4 block text-sm">历史报告 <select className="field ml-2" value={report?.run_id || ''} onChange={event => getReport(event.target.value).then(setReport).catch(reason => setError(String(reason)))}>{runs.filter(run => ['complete','partial'].includes(run.status)).map(run => <option value={run.id} key={run.id}>{new Date(run.started_at).toLocaleString()} · {run.status}</option>)}</select></label>}</section>{error && <p role="alert" className="rounded-xl bg-red-50 p-4 text-sm text-red-800">{error}</p>}{report && <ReportView report={report} />}<details className="rounded-2xl border border-slate-200 bg-white p-6" open={!report}><summary className="cursor-pointer text-lg font-semibold">输入与词色复核</summary><div className="mt-5 space-y-6">{(['user', 'benchmark'] as const).map(role => <ReviewPanel key={role} record={comparison.samples[role]} draft={drafts[role]} onSaved={next => setComparison(previous => previous && ({ ...previous, samples: { ...previous.samples, [role]: next } }))} />)}</div></details><section className="text-right"><button type="button" onClick={remove} disabled={busy} className="text-sm text-red-700 underline disabled:opacity-50">删除此比较及其专属数据</button></section></div>
}
