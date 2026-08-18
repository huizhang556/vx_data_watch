import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, DatePicker, Empty, Form, Input, InputNumber, Modal, Popconfirm, Radio, Segmented, Select, Space, Typography, message } from 'antd'
import { Bot, Eye, History, PlugZap, Plus, Search, Settings2, Sparkles, Trash2 } from 'lucide-react'
import dayjs, { type Dayjs } from 'dayjs'
import ReactECharts from 'echarts-for-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useLocation, useNavigate } from 'react-router-dom'
import { api, query } from '../api'
import { useAccount } from '../account'
import { disableUnavailableDate, rangeHasAllDates, useAvailableDates } from '../dateRange'
import { useAuth } from '../auth'
import type { RangeAnalytics } from '../types'

interface Provider { id: number; account_id: number | null; name: string; base_url: string; model: string; protocol: string; timeout_seconds: number; api_key_configured: boolean; is_active: boolean }
interface QueryHistory { id: number; start_date: string; end_date: string; created_at: string }
interface AnalysisResult extends QueryHistory { report_text: string; snapshot: RangeAnalytics }
interface ProviderForm { account_id: number; provider_id?: number; name: string; base_url: string; model: string; protocol: string; timeout_seconds: number; api_key?: string }
const reportMetrics = [
  { key: 'plays' as const, label: '播放', color: '#1677ff' },
  { key: 'likes' as const, label: '点赞', color: '#d4380d' },
  { key: 'comments' as const, label: '评论', color: '#722ed1' },
  { key: 'shares' as const, label: '分享', color: '#d48806' },
  { key: 'follows' as const, label: '关注', color: '#08979c' },
  { key: 'recommendations' as const, label: '收藏', color: '#389e0d' },
]

const periodOptions = [
  { label: '单日', value: 1 }, { label: '近 3 天', value: 3 }, { label: '近 7 天', value: 7 },
  { label: '近 15 天', value: 15 }, { label: '近 30 天', value: 30 },
]

export default function AIPage() {
  const { account } = useAccount()
  const availableDates = useAvailableDates(account?.id)
  const { user } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [provider, setProvider] = useState<Provider | null>(null)
  const [providers, setProviders] = useState<Provider[]>([])
  const [histories, setHistories] = useState<QueryHistory[]>([])
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [configOpen, setConfigOpen] = useState(false)
  const [models, setModels] = useState<string[]>([])
  const [tested, setTested] = useState(false)
  const [modelLoading, setModelLoading] = useState(false)
  const [draftTestLoading, setDraftTestLoading] = useState(false)
  const [saveLoading, setSaveLoading] = useState(false)
  const [connectionLoading, setConnectionLoading] = useState(false)
  const [analyzeLoading, setAnalyzeLoading] = useState(false)
  const [rangeChecking, setRangeChecking] = useState(false)
  const [rangeWarning, setRangeWarning] = useState('')
  const [viewingId, setViewingId] = useState<number | null>(null)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [days, setDays] = useState(7)
  const [endDate, setEndDate] = useState<Dayjs>(dayjs().subtract(1, 'day'))
  const [startDate, setStartDate] = useState<Dayjs>(() => dayjs().subtract(7, 'day'))
  const [form] = Form.useForm<ProviderForm>()

  const loadProviders = async (accountId: number) => {
    const [rows, active] = await Promise.all([
      api<Provider[]>(`/api/ai/providers?${query({ account_id: accountId })}`),
      api<Provider | null>(`/api/ai/provider?${query({ account_id: accountId })}`),
    ])
    setProviders(rows)
    setProvider(active)
    if (active) { form.setFieldsValue({ ...active, account_id: accountId, provider_id: active.id, api_key: undefined }); setModels([active.model]) }
    else { form.resetFields(); form.setFieldsValue({ account_id: accountId, protocol: 'chat_completions', timeout_seconds: 60 }); setModels([]) }
  }
  const loadHistories = () => account && api<QueryHistory[]>(`/api/ai/reports?${query({ account_id: account.id })}`).then(setHistories)
  useEffect(() => { if (account) void loadProviders(account.id) }, [account]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { void loadHistories() }, [account]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!account) return
    const start = startDate.format('YYYY-MM-DD')
    const end = endDate.format('YYYY-MM-DD')
    const requestedDays = endDate.diff(startDate, 'day') + 1
    setRangeChecking(true)
    setRangeWarning('')
    api<RangeAnalytics>(`/api/analytics/range?${query({ account_id: account.id, start_date: start, end_date: end })}`)
      .then((snapshot) => {
        if (snapshot.days_with_data < requestedDays) {
          setRangeWarning(`当前数据库仅有 ${snapshot.days_with_data}/${requestedDays} 天数据，暂时无法分析完整时间段，请先导入缺少日期的数据。`)
        }
      })
      .catch(() => setRangeWarning('暂时无法检查该时间段的数据量，请稍后重试。'))
      .finally(() => setRangeChecking(false))
  }, [account, startDate, endDate])

  const draftValues = async (requireModel = false) => {
    const fields: Array<keyof ProviderForm> = ['base_url', 'protocol', 'timeout_seconds', 'api_key']
    if (requireModel) fields.push('model')
    const values = await form.validateFields(fields)
    return { ...values, account_id: account!.id, provider_id: form.getFieldValue('provider_id') }
  }

  const fetchModels = async () => {
    setModelLoading(true); setError('')
    try {
      const values = await draftValues()
      const response = await api<{ models: string[] }>('/api/ai/provider/models', { method: 'POST', body: JSON.stringify(values) })
      setModels(response.models)
      if (!response.models.includes(form.getFieldValue('model'))) form.setFieldValue('model', response.models[0])
      message.success(`查询到 ${response.models.length} 个模型`)
    } catch (cause) { setError(cause instanceof Error ? cause.message : '模型查询失败') }
    finally { setModelLoading(false) }
  }

  const testDraft = async () => {
    setDraftTestLoading(true); setError('')
    try {
      const values = await draftValues(true)
      const response = await api<{ result: string }>('/api/ai/provider/test-draft', { method: 'POST', body: JSON.stringify(values) })
      setTested(true); message.success(response.result.slice(0, 100) || '连接成功')
    } catch (cause) { setTested(false); setError(cause instanceof Error ? cause.message : '测试失败') }
    finally { setDraftTestLoading(false) }
  }

  const saveProvider = async () => {
    setSaveLoading(true); setError('')
    try {
      const values = await form.validateFields()
      await api('/api/ai/provider', { method: 'PUT', body: JSON.stringify({ ...values, account_id: account!.id, provider_id: form.getFieldValue('provider_id') }) })
      await loadProviders(account!.id); setConfigOpen(false); message.success('接口配置已保存')
    } catch (cause) { setError(cause instanceof Error ? cause.message : '保存失败') }
    finally { setSaveLoading(false) }
  }

  const testSavedConnection = async () => {
    setConnectionLoading(true); setError('')
    try { const response = await api<{ result: string }>(`/api/ai/provider/test?${query({ account_id: account!.id })}`, { method: 'POST' }); message.success(response.result.slice(0, 100) || '连接成功') }
    catch (cause) { setError(cause instanceof Error ? cause.message : '连接失败') }
    finally { setConnectionLoading(false) }
  }

  const analyze = async (start?: string, end?: string) => {
    if (!account) return
    const endValue = end || endDate.format('YYYY-MM-DD')
    const startValue = start || startDate.format('YYYY-MM-DD')
    setAnalyzeLoading(true); setError(''); setResult(null)
    try {
      const response = await api<AnalysisResult>('/api/ai/analyze', { method: 'POST', body: JSON.stringify({ account_id: account.id, start_date: startValue, end_date: endValue }) })
      setResult(response); await loadHistories(); message.success('分析已生成')
    } catch (cause) { setError(cause instanceof Error ? cause.message : '生成失败') }
    finally { setAnalyzeLoading(false) }
  }

  const viewHistory = async (item: QueryHistory) => {
    setViewingId(item.id); setError(''); setResult(null)
    try {
      const response = await api<AnalysisResult>(`/api/ai/reports/${item.id}/analyze`, { method: 'POST' })
      setResult(response)
      message.success('已查看缓存分析')
    } catch (cause) { setError(cause instanceof Error ? cause.message : '查看分析失败') }
    finally { setViewingId(null) }
  }

  useEffect(() => {
    const historyId = (location.state as { historyId?: unknown } | null)?.historyId
    if (typeof historyId !== 'number') return
    const item = histories.find((row) => row.id === historyId)
    if (!item || viewingId !== null) return
    setStartDate(dayjs(item.start_date))
    setEndDate(dayjs(item.end_date))
    setDays(dayjs(item.end_date).diff(dayjs(item.start_date), 'day') + 1)
    void viewHistory(item)
    navigate('/ai', { replace: true, state: null })
  }, [histories, location.state, navigate]) // eslint-disable-line react-hooks/exhaustive-deps

  const deleteHistory = async (item: QueryHistory) => {
    setDeletingId(item.id); setError('')
    try {
      await api(`/api/ai/reports/${item.id}`, { method: 'DELETE' })
      if (result?.id === item.id) setResult(null)
      setHistories((rows) => rows.filter((row) => row.id !== item.id)); message.success('查询记录已删除')
    } catch (cause) { setError(cause instanceof Error ? cause.message : '删除失败') }
    finally { setDeletingId(null) }
  }

  const deleteProvider = async (item: Provider) => {
    if (!account) return
    try {
      await api(`/api/ai/provider/${item.id}?${query({ account_id: account.id })}`, { method: 'DELETE' })
      setProviders((rows) => rows.filter((row) => row.id !== item.id))
      if (provider?.id === item.id) await loadProviders(account.id)
      message.success('接口配置已删除')
    } catch (cause) { setError(cause instanceof Error ? cause.message : '删除配置失败') }
  }

  const providerOptions = providers.map((item) => ({
    value: item.id,
    label: <div className="provider-option"><span>{item.name}</span><Popconfirm title="删除接口配置" description="删除后不能恢复，历史分析记录使用过的配置无法删除。" okText="删除" cancelText="取消" okButtonProps={{ danger: true }} onConfirm={(event) => { event?.stopPropagation(); void deleteProvider(item) }}><Button type="text" danger size="small" icon={<Trash2 size={14} />} aria-label={`删除配置 ${item.name}`} onMouseDown={(event) => event.stopPropagation()} onClick={(event) => event.stopPropagation()} /></Popconfirm></div>,
  }))

  const reportTrendChart = useMemo(() => ({
    animation: false,
    color: reportMetrics.map((item) => item.color),
    tooltip: { trigger: 'axis', confine: true },
    legend: { top: 0, type: 'scroll', data: reportMetrics.map((item) => item.label) },
    grid: { left: 56, right: 48, top: 50, bottom: 38 },
    xAxis: { type: 'category', data: result?.snapshot.trend.map((row) => dayjs(row.date).format('MM-DD')) || [] },
    yAxis: [
      { type: 'value', name: '播放', splitLine: { lineStyle: { color: '#edf0ee' } } },
      { type: 'value', name: '互动', splitLine: { show: false } },
    ],
    series: reportMetrics.map((metric) => ({
      name: metric.label,
      type: 'line',
      smooth: true,
      symbolSize: 6,
      yAxisIndex: metric.key === 'plays' ? 0 : 1,
      data: result?.snapshot.trend.map((row) => row[metric.key]) || [],
      connectNulls: false,
    })),
  }), [result])

  const reportPieChart = useMemo(() => ({
    animation: false,
    color: reportMetrics.slice(1).map((item) => item.color),
    tooltip: { trigger: 'item', formatter: '{b}<br/>{c} ({d}%)' },
    legend: { type: 'scroll', bottom: 0 },
    series: [{
      type: 'pie',
      radius: ['42%', '68%'],
      center: ['50%', '44%'],
      data: reportMetrics.slice(1).map((metric) => ({
        name: metric.label,
        value: result?.snapshot.totals[metric.key] ?? 0,
      })),
      label: { formatter: '{b}\n{d}%' },
    }],
  }), [result])

  if (!account) return <Empty description="请先创建视频号账号" />
  return (
    <div className="page">
      <div className="page-heading"><div><Typography.Title level={2}>AI 建议</Typography.Title><Typography.Text type="secondary">{provider ? `${provider.name} · ${provider.model}` : '尚未配置 AI 接口'}</Typography.Text></div>{user.role === 'admin' && <Button icon={<Settings2 size={18} />} onClick={() => { setError(''); setTested(false); setConfigOpen(true); void loadProviders(account.id) }}>接口配置</Button>}</div>
      {error && <Alert type="error" showIcon closable onClose={() => setError('')} message={error} />}
      <section className="ai-control">
        <div><span className={`status-dot ${provider ? 'online' : ''}`} /><Typography.Text>{provider ? '接口已配置' : '等待配置'}</Typography.Text></div>
        <Space wrap>
          <Segmented value={periodOptions.some((item) => item.value === days) ? days : 0} onChange={(value) => { const nextDays = Number(value); if (!nextDays) { setDays(0); return }; setDays(nextDays); setStartDate(endDate.subtract(nextDays - 1, 'day')) }} options={[...periodOptions.map((item) => ({ ...item, disabled: !rangeHasAllDates(endDate, item.value, availableDates) })), { label: '自定义', value: 0 }]} />
          <DatePicker disabledDate={(value) => disableUnavailableDate(value, availableDates)} aria-label="开始日期" placeholder="开始日期" allowClear={false} value={startDate} onChange={(value) => value && setStartDate(value.isAfter(endDate, 'day') ? endDate : value)} />
          <DatePicker disabledDate={(value) => disableUnavailableDate(value, availableDates)} aria-label="结束日期" placeholder="结束日期" allowClear={false} value={endDate} onChange={(value) => { if (!value) return; setEndDate(value); setStartDate(days ? value.subtract(days - 1, 'day') : (startDate.isAfter(value, 'day') ? value : startDate)) }} />
          {user.role === 'admin' && <Select aria-label="AI 接口配置" value={provider?.id} placeholder="选择接口配置" style={{ minWidth: 190 }} options={providerOptions} onChange={(id) => {
            const next = providers.find((item) => item.id === id)
            if (next) void api<Provider>('/api/ai/provider/select', { method: 'POST', body: JSON.stringify({ account_id: account.id, provider_id: next.id }) }).then((active) => { setProvider(active); message.success(`已切换到 ${active.name}`) }).catch((cause) => setError(cause instanceof Error ? cause.message : '切换配置失败'))
          }} />}
          {user.role === 'admin' && <Button icon={<PlugZap size={18} />} disabled={!provider} loading={connectionLoading} onClick={() => void testSavedConnection()}>测试连接</Button>}
          <Button type="primary" icon={<Sparkles size={18} />} disabled={!provider || rangeChecking || Boolean(rangeWarning)} loading={analyzeLoading || rangeChecking} onClick={() => void analyze()}>生成分析</Button>
        </Space>
      </section>
      {rangeWarning && <Alert type="warning" showIcon message="当前数据量不足" description={rangeWarning} />}

      {analyzeLoading ? <section className="report-browser report-loading"><Bot size={28} /><Typography.Text>正在生成分析报告...</Typography.Text></section> : result && <section className="report-browser">
        <header><div><Bot size={20} /><strong>查询范围：{result.start_date} 至 {result.end_date}</strong></div><time>查询时间：{dayjs(result.created_at).format('YYYY-MM-DD HH:mm')}</time></header>
        <section className="chart-grid report-charts">
          <div className="chart-panel"><Typography.Title level={3}>指标趋势</Typography.Title><ReactECharts option={reportTrendChart} style={{ height: 320 }} notMerge /></div>
          <div className="chart-panel"><Typography.Title level={3}>互动构成</Typography.Title><ReactECharts option={reportPieChart} style={{ height: 320 }} notMerge /></div>
        </section>
        <article className="markdown-report"><ReactMarkdown remarkPlugins={[remarkGfm]}>{result.report_text}</ReactMarkdown></article>
      </section>}

      <section className="section-band">
        <div className="section-heading"><Typography.Title level={3}>查询记录</Typography.Title><History size={20} /></div>
        {viewingId !== null && <Alert type="info" showIcon message="正在查看分析" description="正在读取已缓存的分析报告；如果是旧记录，系统可能需要重新生成，请稍候。" />}
        {!histories.length ? <Empty description="暂无查询记录" /> : <div className="history-list">{histories.map((item) => <article key={item.id}><div><strong>查询范围：{item.start_date} 至 {item.end_date}</strong><time>查询时间：{dayjs(item.created_at).format('YYYY-MM-DD HH:mm')}</time></div><Space className="history-actions" size={6} wrap>
          <Button size="small" icon={<Eye size={16} />} loading={viewingId === item.id} disabled={viewingId !== null && viewingId !== item.id} onClick={() => void viewHistory(item)}>{viewingId === item.id ? '查看分析中...' : '查看分析'}</Button>
          <Popconfirm title="删除查询记录" description="会同时删除这条分析报告缓存，不会删除视频号数据。" okText="删除" cancelText="取消" okButtonProps={{ danger: true }} onConfirm={() => void deleteHistory(item)}>
            <Button size="small" danger icon={<Trash2 size={16} />} loading={deletingId === item.id}>删除</Button>
          </Popconfirm>
        </Space></article>)}</div>}
      </section>

      <Modal title="OpenAI 兼容接口" open={configOpen} onCancel={() => setConfigOpen(false)} footer={null} destroyOnHidden width={620}>
        <Alert type="info" showIcon message="API Key 仅在后端加密存储" description="先查询模型并测试草稿配置，测试成功后再保存。测试不会修改已保存配置。" />
        {error && <Alert type="error" showIcon message={error} />}
        <Space style={{ marginBottom: 12 }} wrap><Select aria-label="切换配置" value={form.getFieldValue('provider_id')} placeholder="选择已有配置" style={{ minWidth: 220 }} options={providerOptions} onChange={(id) => { const next = providers.find((item) => item.id === id); if (next) { form.setFieldsValue({ ...next, account_id: account.id, provider_id: next.id, api_key: undefined }); setTested(false); setModels([next.model]) } }} /><Button icon={<Plus size={16} />} onClick={() => { form.resetFields(); form.setFieldsValue({ account_id: account.id, protocol: 'chat_completions', timeout_seconds: 60 }); setTested(false); setModels([]) }}>新建配置</Button></Space>
        <Form form={form} layout="vertical" initialValues={{ account_id: account.id, name: '默认 AI', protocol: 'chat_completions', timeout_seconds: 60 }} requiredMark={false} onValuesChange={() => setTested(false)}>
          <Form.Item name="name" label="配置名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="base_url" label="Base URL" rules={[{ required: true }, { type: 'url' }]}><Input placeholder="https://api.openai.com（系统自动兼容 /v1）" /></Form.Item>
          <Form.Item name="api_key" label="API Key（已有配置可留空保持不变）" rules={[({ getFieldValue }) => ({ validator: async (_rule, value) => { if (value || getFieldValue('provider_id')) return; throw new Error('新建配置必须填写 API Key') } })]}><Input.Password autoComplete="new-password" /></Form.Item>
          <div className="model-row"><Form.Item name="model" label="模型" rules={[{ required: true }]}><Select showSearch placeholder="先查询模型" options={models.map((model) => ({ value: model, label: model }))} /></Form.Item><Button icon={<Search size={17} />} loading={modelLoading} onClick={() => void fetchModels()}>查询模型</Button></div>
          <Form.Item name="protocol" label="协议"><Radio.Group optionType="button" options={[{ label: 'Chat Completions', value: 'chat_completions' }, { label: 'Responses', value: 'responses' }]} /></Form.Item>
          <Form.Item name="timeout_seconds" label="超时（秒）"><InputNumber min={5} max={300} /></Form.Item>
          <div className="modal-actions"><Button loading={draftTestLoading} onClick={() => void testDraft()}>测试</Button><Button type="primary" loading={saveLoading} disabled={!tested} onClick={() => void saveProvider()}>保存</Button></div>
        </Form>
      </Modal>
    </div>
  )
}
