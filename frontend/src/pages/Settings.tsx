import { useEffect, useState } from 'react'
import { getProviders } from '../api/client'

export default function Settings() {
  const [settings, setSettings] = useState<Awaited<ReturnType<typeof getProviders>> | null>(null)
  const [error, setError] = useState('')
  useEffect(() => { getProviders().then(setSettings).catch(reason => setError(String(reason))) }, [])
  return <div><p className="eyebrow">设置</p><h1 className="page-title">分析组件</h1><p className="page-subtitle">密钥只由本机后端读取；浏览器仅显示配置状态。</p>{error && <p role="alert" className="mt-5 text-red-700">{error}</p>}{settings && <div className="panel mt-8 space-y-3 text-sm"><p>词级对齐：<strong>{settings.alignment}</strong></p><p>发音模型：<strong>{settings.pronunciation}</strong>（运行时可选）</p><p>解释模型：<strong>{settings.llm}</strong> · {settings.openai_model || '未填写模型'}</p><p>OpenAI API key：<strong>{settings.openai_key_configured ? '已配置' : '未配置'}</strong></p><p className="text-slate-600">即使已配置，每次使用云端解释仍需在分析页面勾选。ChatGPT Plus 与 OpenAI API 分开计费和配置。</p></div>}</div>
}
