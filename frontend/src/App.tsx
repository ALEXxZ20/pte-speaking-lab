import { useEffect, useState } from 'react'
import NewComparison from './pages/NewComparison'
import ComparisonDetail from './pages/ComparisonDetail'
import Settings from './pages/Settings'
import { getHistory } from './api/client'

type Check = { status: string; detail: string }
type Health = { status: 'ok' | 'degraded'; api: Check; database: Check; ffmpeg: Check; ffprobe: Check }

function Home() {
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/v1/health', { signal: controller.signal })
      .then(async response => { if (!response.ok) throw new Error('health_failed'); return response.json() as Promise<Health> })
      .then(setHealth)
      .catch(reason => { if (reason.name !== 'AbortError') setError('无法连接本机分析服务。') })
    return () => controller.abort()
  }, [])
  return <div className="space-y-16"><section className="grid gap-10 py-10 lg:grid-cols-[1.5fr_1fr] lg:items-center"><div><span className="rounded-full bg-indigo-100 px-3 py-1 text-sm font-medium text-indigo-700">发音 · 流利度</span><h1 className="mt-6 max-w-2xl text-4xl font-semibold tracking-tight sm:text-5xl">听见差异，找到下一次练习的重点。</h1><p className="mt-5 max-w-xl text-lg leading-8 text-slate-600">把你的回答与同题高分样本放在一起，保留猩际原始反馈，并用录音中的证据解释词色、停顿和节奏。</p><a href="/comparisons/new" className="button-primary mt-8 inline-block">新建双边比较</a></div><div className="panel"><p className="text-sm font-medium text-slate-500">本机服务状态</p><div className="mt-4 flex items-center gap-3"><span className={`size-3 rounded-full ${health?.status === 'ok' ? 'bg-emerald-500' : 'bg-amber-400'}`} /><strong className="text-xl">{error || (health ? health.status === 'ok' ? '基础服务已就绪' : '部分组件待配置' : '正在检查…')}</strong></div><p className="mt-4 text-sm leading-6 text-slate-600">原始录音与截图保存在本机。Content 只保留猩际分数。</p>{health && <dl className="mt-6 grid grid-cols-2 gap-3 text-sm">{([['API', health.api], ['数据库', health.database], ['FFmpeg', health.ffmpeg], ['音频探测', health.ffprobe]] as const).map(([label, check]) => <div key={label} className="rounded-xl bg-slate-50 p-3"><dt className="text-slate-500">{label}</dt><dd className={`mt-1 font-medium ${check.status === 'ok' ? 'text-emerald-700' : 'text-amber-700'}`}>{check.status === 'ok' ? '可用' : '待检查'}</dd></div>)}</dl>}</div></section><section><h2 className="text-2xl font-semibold">三步看清一次回答</h2><p className="mt-2 text-slate-600">高分回答用于对照，不是标准答案。</p><div className="mt-6 grid gap-4 md:grid-cols-3">{[['01','保存双边样本','上传两侧录音和词色截图，粘贴转写，录入猩际分数。'],['02','分别分析','发音与流利度独立计算，共享可靠的词级时间位置。'],['03','查看证据','比较共享词和节奏差异，得到可回听的训练重点。']].map(([number,title,description]) => <article key={number} className="panel"><span className="text-sm font-semibold text-indigo-600">{number}</span><h3 className="mt-4 text-lg font-semibold">{title}</h3><p className="mt-2 leading-7 text-slate-600">{description}</p></article>)}</div></section></div>
}

function History() {
  const [items, setItems] = useState<{ id: string; created_at: string; question_type: string; title: string | null }[]>([])
  const [error, setError] = useState('')
  useEffect(() => { getHistory().then(setItems).catch(reason => setError(String(reason))) }, [])
  return <div><p className="eyebrow">历史</p><h1 className="page-title">已保存的比较</h1>{error && <p role="alert">{error}</p>}<div className="mt-8 space-y-3">{items.map(item => <a key={item.id} href={`/comparisons/${item.id}`} className="panel block hover:border-indigo-300"><span className="text-xs font-semibold text-indigo-600">{item.question_type}</span><h2 className="mt-1 font-semibold">{item.title || '未命名题目'}</h2><p className="mt-1 text-sm text-slate-500">{new Date(item.created_at).toLocaleString()}</p></a>)}{!error && !items.length && <p className="text-slate-600">还没有保存的比较。<a className="text-indigo-700 underline" href="/comparisons/new">创建第一条</a></p>}</div></div>
}

export default function App() {
  const path = window.location.pathname
  const page = path === '/comparisons/new' ? <NewComparison /> : path === '/history' ? <History /> : path === '/settings' ? <Settings /> : path.startsWith('/comparisons/') ? <ComparisonDetail id={path.split('/')[2]} /> : <Home />
  return <div className="min-h-screen bg-slate-50 text-slate-900"><header className="border-b border-slate-200 bg-white"><nav className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-5"><a href="/" className="flex items-center gap-3"><span className="grid size-10 place-items-center rounded-xl bg-indigo-600 text-lg font-bold text-white">P</span><span><strong className="block text-lg leading-tight">PTE Speaking Lab</strong><small className="text-slate-500">本机口语对比工作台</small></span></a><div className="flex gap-5 text-sm font-medium text-slate-600"><a className="hover:text-indigo-700" href="/">首页</a><a className="hover:text-indigo-700" href="/comparisons/new">新建比较</a><a className="hover:text-indigo-700" href="/history">历史</a><a className="hover:text-indigo-700" href="/settings">设置</a></div></nav></header><main className="mx-auto max-w-6xl px-6 py-12">{page}</main><footer className="mt-16 border-t border-slate-200 px-6 py-6 text-center text-sm text-slate-500">本机保存 · Content 仅保留猩际分数 · 不生成官方 PTE 成绩</footer></div>
}
