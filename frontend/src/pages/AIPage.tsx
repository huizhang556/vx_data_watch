import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, DatePicker, Empty, Form, Input, InputNumber, Modal, Popconfirm, Radio, Segmented, Select, Space, Typography, message } from 'antd'
import { Bot, Eye, History, Pencil, PlugZap, Search, Settings2, Sparkles, Trash2 } from 'lucide-react'
import dayjs, { type Dayjs } from 'dayjs'
import ReactECharts from 'echarts-for-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api, query } from '../api'
import { useAccount } from '../account'
import { useAuth } from '../auth'
import type { RangeAnalytics } from '../types'

interface Provider { id: number; name: string; base_url: string; model: string; protocol: string; timeout_seconds: number; api_key_configured: boolean }
interface QueryHistory { id: number; start_date: string; end_date: string; created_at: string }
interface AnalysisResult extends QueryHistory { report_text: string; snapshot: RangeAnalytics }
interface ProviderForm { name: string; base_url: string; model: string; protocol: string; timeout_seconds: number; api_key?: string }

const periodOptions = [
  { label: '单日', value: 1 }, { label: '近 3 天', value: 3 }, { label: '近 7 天', value: 7 },
  { label: '近 15 天', value: 15 }, { label: '近 30 天', value: 30 },
]

export default function AIPage() {
  const { account } = useAccount()
  const { user } = useAuth()
  const [provider, setProvider] = useState<Provider | null>(null)
  const [histories, setHistories] = useState<QueryHistory[]>([])
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [configOpen, setConfigOpen] = useState(false)
  const [editHistory, setEditHistory] = useState<QueryHistory | null>(null)
  const [editRange, setEditRange] = useState<[Dayjs, Dayjs] | null>(null)
  const [models, setModels] = useState<string[]>([])
  const [tested, setTested] = useState(false)
  const [modelLoading, setModelLoading] = useState(false)
  const [draftTestLoading, setDraftTestLoading] = useState(false)
  const [saveLoading, setSaveLoading] = useState(false)
  const [connectionLoading, setConnectionLoading] = useState(false)
  const [analyzeLoading, setAnalyzeLoading] = useState(false)
  const [viewingId, setViewingId] = useState<number | null>(null)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [editLoading, setEditLoading] = useState(false)
  const [error, setError] = useState('')
  const [days, setDays] = useState(7)
  const [endDate, setEndDate] = useState<Dayjs>(dayjs().subtract(1, 'day'))
  const [form] = Form.useForm<ProviderForm>()

  const loadProvider = () => api<Provider | null>('/api/ai/provider').then((value) => {
    setProvider(value)
    if (value) { form.setFieldsValue({ ...value, api_key: undefined }); setModels([value.model]) }
  })
  const loadHistories = () => account && api<QueryHistory[]>(`/api/ai/reports?${query({ account_id: account.id })}`).then(setHistories)
  useEffect(() => { void loadProvider() }, []) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { void loadHistories() }, [account]) // eslint-disable-line react-hooks/exhaustive-deps

  const draftValues = async (requireModel = false) => {
    const fields: Array<keyof ProviderForm> = ['base_url', 'protocol', 'timeout_seconds', 'api_key']
    if (requireModel) fields.push('model')
    const values = await form.validateFields(fields)
    return values
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
      await api('/api/ai/provider', { method: 'PUT', body: JSON.stringify(values) })
      await loadProvider(); setConfigOpen(false); message.success('接口配置已保存')
    } catch (cause) { setError(cause instanceof Error ? cause.message : '保存失败') }
    finally { setSaveLoading(false) }
  }

  const testSavedConnection = async () => {
    setConnectionLoading(true); setError('')
    try { const response = await api<{ result: string }>('/api/ai/provider/test', { method: 'POST' }); message.success(response.result.slice(0, 100) || '连接成功') }
    catch (cause) { setError(cause instanceof Error ? cause.message : '连接失败') }
    finally { setConnectionLoading(false) }
  }

  const analyze = async (start?: string, end?: string) => {
    if (!account) return
    const endValue = end || endDate.format('YYYY-MM-DD')
    const startValue = start || endDate.subtract(days - 1, 'day').format('YYYY-MM-DD')
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
      message.success('分析已重新生成')
    } catch (cause) { setError(cause instanceof Error ? cause.message : '查看分析失败') }
    finally { setViewingId(null) }
  }

  const openHistoryEdit = (item: QueryHistory) => {
    setEditHistory(item)
    setEditRange([dayjs(item.start_date), dayjs(item.end_date)])
  }

  const saveHistoryEdit = async () => {
    if (!editHistory || !editRange) return
    setEditLoading(true); setError('')
    try {
      await api(`/api/ai/reports/${editHistory.id}`, { method: 'PUT', body: JSON.stringify({ start_date: editRange[0].format('YYYY-MM-DD'), end_date: editRange[1].format('YYYY-MM-DD') }) })
      if (result?.id === editHistory.id) setResult(null)
      await loadHistories(); setEditHistory(null); message.success('查询条件已更新')
    } catch (cause) { setError(cause instanceof Error ? cause.message : '编辑失败') }
    finally { setEditLoading(false) }
  }

  const deleteHistory = async (item: QueryHistory) => {
    setDeletingId(item.id); setError('')
    try {
      await api(`/api/ai/reports/${item.id}`, { method: 'DELETE' })
      if (result?.id === item.id) setResult(null)
      setHistories((rows) => rows.filter((row) => row.id !== item.id)); message.success('查询记录已删除')
    } catch (cause) { setError(cause instanceof Error ? cause.message : '删除失败') }
    finally { setDeletingId(null) }
  }

  const reportChart = useMemo(() => ({
    animation: false,
    tooltip: { trigger: 'axis' }, legend: { top: 0 }, grid: { left: 52, right: 18, top: 42, bottom: 32 },
    xAxis: { type: 'category', data: result?.snapshot.trend.map((row) => dayjs(row.date).format('MM-DD')) || [] },
    yAxis: [{ type: 'value', name: '播放' }, { type: 'value', name: '互动' }],
    series: [
      { name: '播放', type: 'bar', data: result?.snapshot.trend.map((row) => row.plays) || [] },
      { name: '点赞', type: 'line', yAxisIndex: 1, data: result?.snapshot.trend.map((row) => row.likes) || [] },
      { name: '分享', type: 'line', yAxisIndex: 1, data: result?.snapshot.trend.map((row) => row.shares) || [] },
    ],
  }), [result])

  if (!account) return <Empty description="请先创建视频号账号" />
  return (
    <div className="page">
      <div className="page-heading"><div><Typography.Title level={2}>AI 建议</Typography.Title><Typography.Text type="secondary">{provider ? `${provider.name} · ${provider.model}` : '尚未配置 AI 接口'}</Typography.Text></div>{user.role === 'admin' && <Button icon={<Settings2 size={18} />} onClick={() => { setError(''); setTested(false); setConfigOpen(true) }}>接口配置</Button>}</div>
      {error && <Alert type="error" showIcon closable onClose={() => setError('')} message={error} />}
      <section className="ai-control">
        <div><span className={`status-dot ${provider ? 'online' : ''}`} /><Typography.Text>{provider ? '接口已配置' : '等待配置'}</Typography.Text></div>
        <Space wrap>
          <Segmented value={days} onChange={(value) => setDays(Number(value))} options={periodOptions} />
          <DatePicker allowClear={false} value={endDate} onChange={(value) => value && setEndDate(value)} />
          {user.role === 'admin' && <Button icon={<PlugZap size={18} />} disabled={!provider} loading={connectionLoading} onClick={() => void testSavedConnection()}>测试连接</Button>}
          <Button type="primary" icon={<Sparkles size={18} />} disabled={!provider} loading={analyzeLoading} onClick={() => void analyze()}>生成分析</Button>
        </Space>
      </section>

      {analyzeLoading ? <section className="report-browser report-loading"><Bot size={28} /><Typography.Text>正在生成分析报告...</Typography.Text></section> : result && <section className="report-browser">
        <header><div><Bot size={20} /><strong>{result.start_date} 至 {result.end_date}</strong></div><time>{dayjs(result.created_at).format('YYYY-MM-DD HH:mm')}</time></header>
        <ReactECharts option={reportChart} style={{ height: 300 }} notMerge />
        <article className="markdown-report"><ReactMarkdown remarkPlugins={[remarkGfm]}>{result.report_text}</ReactMarkdown></article>
      </section>}

      <section className="section-band">
        <div className="section-heading"><Typography.Title level={3}>查询记录</Typography.Title><History size={20} /></div>
        {!histories.length ? <Empty description="暂无查询记录" /> : <div className="history-list">{histories.map((item) => <article key={item.id}><div><strong>{item.start_date === item.end_date ? item.start_date : `${item.start_date} 至 ${item.end_date}`}</strong><time>{dayjs(item.created_at).format('YYYY-MM-DD HH:mm')}</time></div><Space className="history-actions" size={6} wrap>
          <Button size="small" icon={<Eye size={16} />} loading={viewingId === item.id} disabled={viewingId !== null && viewingId !== item.id} onClick={() => void viewHistory(item)}>查看分析</Button>
          <Button size="small" icon={<Pencil size={16} />} onClick={() => openHistoryEdit(item)}>编辑</Button>
          <Popconfirm title="删除查询记录" description="只删除这条查询条件，不会删除视频号数据。" okText="删除" cancelText="取消" okButtonProps={{ danger: true }} onConfirm={() => void deleteHistory(item)}>
            <Button size="small" danger icon={<Trash2 size={16} />} loading={deletingId === item.id}>删除</Button>
          </Popconfirm>
        </Space></article>)}</div>}
      </section>

      <Modal title="编辑查询条件" open={Boolean(editHistory)} onCancel={() => setEditHistory(null)} onOk={() => void saveHistoryEdit()} confirmLoading={editLoading} okText="保存" cancelText="取消" destroyOnHidden>
        <DatePicker.RangePicker className="history-range-picker" allowClear={false} value={editRange} onChange={(value) => value && setEditRange(value as [Dayjs, Dayjs])} />
      </Modal>

      <Modal title="OpenAI 兼容接口" open={configOpen} onCancel={() => setConfigOpen(false)} footer={null} destroyOnHidden width={620}>
        <Alert type="info" showIcon message="API Key 仅在后端加密存储" description="先查询模型并测试草稿配置，测试成功后再保存。测试不会修改已保存配置。" />
        {error && <Alert type="error" showIcon message={error} />}
        <Form form={form} layout="vertical" initialValues={{ name: '默认 AI', protocol: 'chat_completions', timeout_seconds: 60 }} requiredMark={false} onValuesChange={() => setTested(false)}>
          <Form.Item name="name" label="配置名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="base_url" label="Base URL" rules={[{ required: true }, { type: 'url' }]}><Input placeholder="https://api.openai.com/v1" /></Form.Item>
          <Form.Item name="api_key" label={provider?.api_key_configured ? 'API Key（留空保持不变）' : 'API Key'} rules={provider ? [] : [{ required: true }]}><Input.Password autoComplete="new-password" /></Form.Item>
          <div className="model-row"><Form.Item name="model" label="模型" rules={[{ required: true }]}><Select showSearch placeholder="先查询模型" options={models.map((model) => ({ value: model, label: model }))} /></Form.Item><Button icon={<Search size={17} />} loading={modelLoading} onClick={() => void fetchModels()}>查询模型</Button></div>
          <Form.Item name="protocol" label="协议"><Radio.Group optionType="button" options={[{ label: 'Chat Completions', value: 'chat_completions' }, { label: 'Responses', value: 'responses' }]} /></Form.Item>
          <Form.Item name="timeout_seconds" label="超时（秒）"><InputNumber min={5} max={300} /></Form.Item>
          <div className="modal-actions"><Button loading={draftTestLoading} onClick={() => void testDraft()}>测试</Button><Button type="primary" loading={saveLoading} disabled={!tested} onClick={() => void saveProvider()}>保存</Button></div>
        </Form>
      </Modal>
    </div>
  )
}
