import { useEffect, useState } from 'react'
import { Alert, Button, DatePicker, Divider, Empty, Input, InputNumber, Segmented, Table, Tag, Typography, Upload, message } from 'antd'
import { Check, FileSpreadsheet, ImagePlus, ScanText, UploadCloud } from 'lucide-react'
import dayjs, { type Dayjs } from 'dayjs'
import { api, query } from '../api'
import { useAccount } from '../account'

interface PreviewRow { date: string; plays: number; recommendations?: number; likes?: number; comments?: number; shares?: number; follows?: number; action: string; differences?: object }
interface CsvPreview { filename: string; record_count: number; date_range: string[]; summary: Record<string, number>; rows: PreviewRow[] }
interface Candidate {
  title: string; published_at?: string | null; metric_date: string; plays: number; cumulative_plays?: number | null; cumulative_plays_approximate?: boolean; likes?: number | null; comments?: number | null; shares?: number | null; confidence?: number
}
interface ImportHistory { id: number; type: string; status: string; filename?: string; record_count: number; created_at: string }

const actionColor: Record<string, string> = { new: 'green', update: 'orange', duplicate: 'default' }
const actionText: Record<string, string> = { new: '新增', update: '修订', duplicate: '重复' }

export default function ImportsPage() {
  const { account } = useAccount()
  const [mode, setMode] = useState<'csv' | 'screenshot' | 'sheet'>('csv')
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<CsvPreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [csvEndDate, setCsvEndDate] = useState<Dayjs | null>(null)
  const [metricDate, setMetricDate] = useState<Dayjs | null>(null)
  const [screenshotFiles, setScreenshotFiles] = useState<File[]>([])
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [history, setHistory] = useState<ImportHistory[]>([])

  const loadHistory = () => account && api<ImportHistory[]>(`/api/imports?${query({ account_id: account.id })}`).then(setHistory)
  useEffect(() => { void loadHistory() }, [account]) // eslint-disable-line react-hooks/exhaustive-deps

  const formData = (selected: File, field?: string, value?: Dayjs | null) => {
    const body = new FormData(); body.append('account_id', String(account!.id)); body.append('file', selected)
    if (field && value) body.append(field, value.format('YYYY-MM-DD'))
    return body
  }
  const previewCsv = async () => {
    if (!file || !account) return
    setBusy(true); setError('')
    if (!csvEndDate) { setError('请先选择文件数据截止日期，确认没有选错日期'); return }
    try { setPreview(await api<CsvPreview>('/api/imports/account-csv/preview', { method: 'POST', body: formData(file, 'data_end_date', csvEndDate) })) }
    catch (cause) { setError(cause instanceof Error ? cause.message : '解析失败') }
    finally { setBusy(false) }
  }
  const commitCsv = async () => {
    if (!file || !account) return
    setBusy(true); setError('')
    if (!csvEndDate) { setError('请先选择文件数据截止日期，确认没有选错日期'); return }
    try {
      const result = await api<{ summary: Record<string, number> }>('/api/imports/account-csv/commit', { method: 'POST', body: formData(file, 'data_end_date', csvEndDate) })
      message.success(`导入完成：新增 ${result.summary.new}，修订 ${result.summary.update}，重复 ${result.summary.duplicate}`)
      setFile(null); setPreview(null); await loadHistory()
    } catch (cause) { setError(cause instanceof Error ? cause.message : '导入失败') }
    finally { setBusy(false) }
  }
  const previewSheet = async () => {
    if (!file || !account) return
    setBusy(true); setError('')
    try {
      if (!metricDate) { setError('请先选择这批表格对应的数据日期，确认没有选错日期'); return }
      const result = await api<{ rows: Candidate[]; filename: string }>('/api/imports/video-sheet/preview', { method: 'POST', body: formData(file, 'metric_date', metricDate) })
      setCandidates(result.rows); message.success(`识别到 ${result.rows.length} 条视频数据`)
    } catch (cause) { setError(cause instanceof Error ? cause.message : '解析失败') }
    finally { setBusy(false) }
  }
  const recognize = async () => {
    if (!screenshotFiles.length || !metricDate) { setError('请先选择截图对应的数据日期，确认没有选错日期'); return }
    const maxBytes = 20 * 1024 * 1024
    const oversized = screenshotFiles.find((item) => item.size > maxBytes)
    if (oversized) { setError(`图片 ${oversized.name} 大小为 ${(oversized.size / 1024 / 1024).toFixed(1)} MB，超过单文件 20 MB 限制，请压缩后重试`); return }
    const totalBytes = screenshotFiles.reduce((sum, item) => sum + item.size, 0)
    if (totalBytes > maxBytes) { setError(`本次选择的 ${screenshotFiles.length} 张图片合计 ${(totalBytes / 1024 / 1024).toFixed(1)} MB，超过默认 20 MB 上传限制，请分批识别`); return }
    setBusy(true); setError('')
    const body = new FormData(); body.append('metric_date', metricDate.format('YYYY-MM-DD')); screenshotFiles.forEach((item) => body.append('files', item))
    try {
      const result = await api<{ candidates: Candidate[]; errors: { filename: string; error: string }[] }>('/api/imports/screenshots/recognize', { method: 'POST', body })
      setCandidates(result.candidates)
      if (result.errors.length) setError(result.errors.map((item) => `${item.filename}: ${item.error}`).join('；'))
      if (result.candidates.length) message.success(`识别到 ${result.candidates.length} 条候选记录`)
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'OCR 失败') }
    finally { setBusy(false) }
  }
  const commitCandidates = async () => {
    if (!account || !candidates.length) return
    setBusy(true); setError('')
    try {
      await api('/api/imports/video-metrics/commit', { method: 'POST', body: JSON.stringify({ account_id: account.id, metric_date: metricDate?.format('YYYY-MM-DD'), filename: mode === 'sheet' ? file?.name : '截图 OCR 确认', rows: candidates }) })
      message.success('逐视频数据已入库'); setCandidates([]); setScreenshotFiles([]); setFile(null); await loadHistory()
    } catch (cause) { setError(cause instanceof Error ? cause.message : '提交失败') }
    finally { setBusy(false) }
  }
  const updateCandidate = (index: number, patch: Partial<Candidate>) => setCandidates((rows) => rows.map((row, i) => i === index ? { ...row, ...patch } : row))

  if (!account) return <Empty description="请先创建视频号账号" />
  return (
    <div className="page">
      <div className="page-heading"><div><Typography.Title level={2}>数据导入</Typography.Title><Typography.Text type="secondary">导入前预览，确认后持久化</Typography.Text></div></div>
      <Segmented block className="import-tabs" value={mode} onChange={(value) => { setMode(value as typeof mode); setFile(null); setPreview(null); setCandidates([]); setError('') }} options={[{ label: '每日 CSV', value: 'csv' }, { label: '视频截图', value: 'screenshot' }, { label: '视频表格', value: 'sheet' }]} />
      {error && <Alert type="error" showIcon closable onClose={() => setError('')} message={error} />}

      {mode === 'csv' && <section className="tool-section">
        <Typography.Title level={3}>7 日汇总文件</Typography.Title>
        <div className="upload-row">
          <DatePicker aria-label="数据截止日期" placeholder="先选数据截止日期" allowClear value={csvEndDate} onChange={(value) => { setCsvEndDate(value); setFile(null); setPreview(null) }} />
          <Upload disabled={!csvEndDate} accept=".csv,text/csv" maxCount={1} showUploadList={false} beforeUpload={(value) => { setFile(value); setPreview(null); return false }}><Button icon={<FileSpreadsheet size={18} />}>选择 CSV</Button></Upload>
          <span className="selected-file">{file?.name || '尚未选择文件'}</span>
          <Button type="primary" icon={<ScanText size={18} />} disabled={!file} loading={busy} onClick={() => void previewCsv()}>解析预览</Button>
        </div>
        <Alert type="info" showIcon message="请先选择这份文件的数据截止日期" description="例如文件覆盖 8 月 11 日至 8 月 17 日，就选择 8 月 17 日；系统会校验文件内最新日期，重复日期会自动去重或修订。" />
        {preview && <>
          <div className="preview-summary"><span>{preview.date_range[0]} 至 {preview.date_range[1]}</span><Tag color="green">新增 {preview.summary.new}</Tag><Tag color="orange">修订 {preview.summary.update}</Tag><Tag>重复 {preview.summary.duplicate}</Tag></div>
          <Table size="small" rowKey="date" pagination={false} scroll={{ x: 720 }} dataSource={preview.rows} columns={[
            { title: '日期', dataIndex: 'date' }, { title: '播放', dataIndex: 'plays' }, { title: '推荐', dataIndex: 'recommendations' }, { title: '喜欢', dataIndex: 'likes' }, { title: '评论', dataIndex: 'comments' }, { title: '分享', dataIndex: 'shares' }, { title: '关注', dataIndex: 'follows' },
            { title: '处理', dataIndex: 'action', render: (value) => <Tag color={actionColor[value]}>{actionText[value]}</Tag> },
          ]} />
          <div className="action-row"><Button type="primary" icon={<Check size={18} />} loading={busy} onClick={() => void commitCsv()}>确认导入</Button></div>
        </>}
      </section>}

      {mode === 'screenshot' && <section className="tool-section">
        <Typography.Title level={3}>视频数据截图</Typography.Title>
        <div className="upload-row">
          <DatePicker aria-label="截图数据日期" placeholder="先选数据日期" allowClear value={metricDate} onChange={(value) => { setMetricDate(value); setScreenshotFiles([]) }} />
          <Upload disabled={!metricDate} accept="image/png,image/jpeg,image/webp" multiple showUploadList={false} beforeUpload={(value) => { setScreenshotFiles((items) => [...items, value]); return false }}><Button icon={<ImagePlus size={18} />}>选择多张截图</Button></Upload>
          <span className="selected-file">已选择 {screenshotFiles.length} 张</span>
          <Button type="primary" icon={<ScanText size={18} />} disabled={!screenshotFiles.length} loading={busy} onClick={() => void recognize()}>开始识别</Button>
        </div>
        <Alert type="info" showIcon message={metricDate ? `指标日期：${metricDate.format('YYYY-MM-DD')}` : '请先选择截图数据日期'} description="这里填写截图实际对应的统计日期，不一定是昨天；识别结果不会自动入库，确认前请检查日期。" />
      </section>}

      {mode === 'sheet' && <section className="tool-section">
        <div className="section-heading"><Typography.Title level={3}>逐视频 CSV / Excel</Typography.Title><Button type="link" href="/api/templates/video-metrics.csv">下载模板</Button></div>
        <div className="upload-row">
          <DatePicker aria-label="表格数据日期" placeholder="先选数据日期" allowClear value={metricDate} onChange={(value) => { setMetricDate(value); setFile(null); setCandidates([]) }} />
          <Upload disabled={!metricDate} accept=".csv,.xlsx" maxCount={1} showUploadList={false} beforeUpload={(value) => { setFile(value); setCandidates([]); return false }}><Button icon={<FileSpreadsheet size={18} />}>选择文件</Button></Upload>
          <span className="selected-file">{file?.name || '尚未选择文件'}</span>
          <Button type="primary" icon={<ScanText size={18} />} disabled={!file} loading={busy} onClick={() => void previewSheet()}>解析预览</Button>
        </div>
        <Alert type="info" showIcon message="请先选择这批表格对应的数据日期" description="系统会将本次确认的日期用于所有视频行，请确认没有选错日期。" />
      </section>}

      {candidates.length > 0 && <section className="candidate-section">
        <Divider orientation="left">确认逐视频数据（{candidates.length} 条）</Divider>
        <div className="candidate-list">
          {candidates.map((row, index) => <article className="candidate-card" key={`${row.title}-${index}`}>
            <div className="candidate-title"><Input value={row.title} aria-label="视频标题" onChange={(event) => updateCandidate(index, { title: event.target.value })} /><Button danger type="text" onClick={() => setCandidates((items) => items.filter((_, i) => i !== index))}>移除</Button></div>
            <div className="candidate-fields">
              <label>数据日期<Input value={row.metric_date} onChange={(event) => updateCandidate(index, { metric_date: event.target.value })} /></label>
              <label>新增播放<InputNumber min={0} value={row.plays} onChange={(value) => updateCandidate(index, { plays: Number(value || 0) })} /></label>
              <label>发布时间<Input value={row.published_at || ''} placeholder="可留空" onChange={(event) => updateCandidate(index, { published_at: event.target.value || null })} /></label>
              <label>累计播放<InputNumber min={0} value={row.cumulative_plays} onChange={(value) => updateCandidate(index, { cumulative_plays: value })} /></label>
              <label>喜欢<InputNumber min={0} value={row.likes} onChange={(value) => updateCandidate(index, { likes: value })} /></label>
              <label>评论<InputNumber min={0} value={row.comments} onChange={(value) => updateCandidate(index, { comments: value })} /></label>
              <label>分享<InputNumber min={0} value={row.shares} onChange={(value) => updateCandidate(index, { shares: value })} /></label>
            </div>
            {row.confidence !== undefined && <Tag color={row.confidence >= .85 ? 'green' : 'orange'}>OCR {Math.round(row.confidence * 100)}%</Tag>}
          </article>)}
        </div>
        <div className="action-row"><Button type="primary" icon={<UploadCloud size={18} />} loading={busy} onClick={() => void commitCandidates()}>确认并入库</Button></div>
      </section>}

      <section className="section-band">
        <Typography.Title level={3}>最近导入</Typography.Title>
        {!history.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无导入记录" /> : <Table size="small" rowKey="id" pagination={false} dataSource={history.slice(0, 10)} columns={[
          { title: '时间', dataIndex: 'created_at', render: (value) => dayjs(value).format('YYYY-MM-DD HH:mm') },
          { title: '类型', dataIndex: 'type' }, { title: '文件', dataIndex: 'filename', ellipsis: true }, { title: '记录', dataIndex: 'record_count' }, { title: '状态', dataIndex: 'status', render: (value) => <Tag color="green">{value}</Tag> },
        ]} />}
      </section>
    </div>
  )
}
