import { Alert, Button, Card, Checkbox, Input, Progress, Select, Space, Spin, Table, Typography, message } from 'antd'
import { CheckCircle2, Download, Eraser, ListPlus, Pause, Play, Settings2, ShieldCheck, Trash2, XCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../api'

type DownloadSettings = {
  quality: 'best' | '2160' | '1440' | '1080' | '720' | '480' | '360'
  download_type: 'video_audio' | 'video' | 'audio'
  save_thumbnail: boolean
  transcode_enabled: boolean
  transcode_quality: 'fast' | 'balanced' | 'high'
  keep_original: boolean
  cookies_enabled: boolean
  cookies_set: boolean
}

type DownloadTask = { id: number; url: string; title: string; duration: string; estimated_size: string; status: string; progress: number; error?: string | null }

const defaults: DownloadSettings = {
  quality: '1080', download_type: 'video_audio', save_thumbnail: true,
  transcode_enabled: false, transcode_quality: 'balanced', keep_original: true,
  cookies_enabled: true, cookies_set: false,
}

export default function DownloadPage({ mode = 'content' }: { mode?: 'config' | 'content' }) {
  const isConfig = mode === 'config'
  const [settings, setSettings] = useState<DownloadSettings>(defaults)
  const [cookies, setCookies] = useState('')
  const [loading, setLoading] = useState(isConfig)
  const [saving, setSaving] = useState(false)
  const [cookieTesting, setCookieTesting] = useState(false)
  const [links, setLinks] = useState('')
  const [tasks, setTasks] = useState<DownloadTask[]>([])
  const [taskLoading, setTaskLoading] = useState(false)

  useEffect(() => {
    if (!isConfig) return
    void api<DownloadSettings>('/api/download/settings').then((result) => setSettings(result)).catch((cause) => message.error(cause instanceof Error ? cause.message : '无法读取下载配置')).finally(() => setLoading(false))
  }, [isConfig])
  useEffect(() => {
    if (isConfig) return
    const load = () => void api<DownloadTask[]>('/api/download/tasks').then(setTasks).catch((cause) => message.error(cause instanceof Error ? cause.message : '无法读取下载队列'))
    load()
    const timer = window.setInterval(load, 2500)
    return () => window.clearInterval(timer)
  }, [isConfig])

  const update = <K extends keyof DownloadSettings>(key: K, value: DownloadSettings[K]) => setSettings((current) => ({ ...current, [key]: value }))
  const save = async () => {
    setSaving(true)
    try {
      const result = await api<DownloadSettings>('/api/download/settings', { method: 'PUT', body: JSON.stringify({ ...settings, cookies: cookies.trim() || null }) })
      setSettings(result); setCookies(''); message.success('下载配置已保存')
    } catch (cause) { message.error(cause instanceof Error ? cause.message : '保存失败') }
    finally { setSaving(false) }
  }
  const testCookies = async () => {
    setCookieTesting(true)
    try { const result = await api<{ message: string }>('/api/download/cookies/test', { method: 'POST', body: JSON.stringify({ cookies }) }); message.success(result.message) }
    catch (cause) { message.error(cause instanceof Error ? cause.message : 'Cookies 测试失败') }
    finally { setCookieTesting(false) }
  }
  const clearCookies = async () => {
    setSaving(true)
    try { const result = await api<DownloadSettings>('/api/download/settings', { method: 'PUT', body: JSON.stringify({ ...settings, cookies: '' }) }); setSettings(result); setCookies(''); message.success('Cookies 已清除') }
    catch (cause) { message.error(cause instanceof Error ? cause.message : '清除失败') }
    finally { setSaving(false) }
  }
  const addTasks = async () => {
    const urls = links.split(/\r?\n/).map((url) => url.trim()).filter(Boolean)
    if (!urls.length) return
    setTaskLoading(true)
    try { const result = await api<DownloadTask[]>('/api/download/tasks', { method: 'POST', body: JSON.stringify({ urls }) }); setTasks((current) => [...result, ...current]); setLinks(''); message.success(`已添加 ${result.length} 个下载任务`) }
    catch (cause) { message.error(cause instanceof Error ? cause.message : '添加任务失败') }
    finally { setTaskLoading(false) }
  }
  const taskAction = async (task: DownloadTask, action: 'start' | 'cancel' | 'delete') => {
    try {
      if (action === 'delete') {
        await api<void>(`/api/download/tasks/${task.id}`, { method: 'DELETE' })
        setTasks((current) => current.filter((item) => item.id !== task.id))
      } else {
        const result = await api<DownloadTask>(`/api/download/tasks/${task.id}/${action}`, { method: 'POST' })
        setTasks((current) => current.map((item) => item.id === task.id ? result : item))
      }
    } catch (cause) { message.error(cause instanceof Error ? cause.message : '操作失败') }
  }
  const statusLabel: Record<string, string> = { queued: '排队中', downloading: '下载中', completed: '已完成', failed: '失败', cancelled: '已取消', paused: '已暂停' }
  const taskColumns = [
    { title: '序号', dataIndex: 'id', width: 70 },
    { title: '链接', dataIndex: 'url', ellipsis: true },
    { title: '标题', dataIndex: 'title', ellipsis: true },
    { title: '时长', dataIndex: 'duration', width: 90 },
    { title: '预计大小', dataIndex: 'estimated_size', width: 100 },
    { title: '状态', dataIndex: 'status', width: 100, render: (status: string, task: DownloadTask) => <span className={`download-status ${status}`}>{statusLabel[status] || status}{task.error && <Typography.Text type="danger" title={task.error}> *</Typography.Text>}</span> },
    { title: '进度', dataIndex: 'progress', width: 150, render: (progress: number) => <Progress percent={Math.round(progress)} size="small" /> },
  ]

  if (isConfig && loading) return <div className="page-loading"><Spin size="large" /></div>
  return <div className="page">
    <div className="page-heading"><div><Typography.Title level={2}>{isConfig ? '下载配置' : '下载内容'}</Typography.Title><Typography.Text type="secondary">{isConfig ? '配置视频下载任务和保存策略' : '查看和管理已提交的视频下载内容'}</Typography.Text></div></div>
    {!isConfig ? <div className="download-content">
      <Card className="download-content-group" title="探索与下载">
        <Button className="browser-launch" type="primary" icon={<Download size={17} />} onClick={() => window.open('https://www.youtube.com/', '_blank', 'noopener,noreferrer')}>启动 YouTube 内容浏览器</Button>
        <div className="download-link-row"><Typography.Text>手动/批量输入链接:</Typography.Text><Input.TextArea value={links} onChange={(event) => setLinks(event.target.value)} rows={4} placeholder="可直接在此粘贴视频或列表链接，每行一个" /><Button icon={<ListPlus size={16} />} loading={taskLoading} onClick={() => void addTasks()}>添加</Button></div>
      </Card>
      <Card className="download-content-group" title="下载队列">
        {tasks.length ? <Table rowKey="id" size="small" pagination={false} columns={taskColumns} dataSource={tasks} scroll={{ x: 900 }} /> : <div className="download-empty"><Download size={40} strokeWidth={1.5} /><Typography.Text>暂无下载任务</Typography.Text></div>}
      </Card>
      <Card className="download-content-group" title="下载操作">
        <div className="download-path-row"><Typography.Text>下载路径</Typography.Text><Input value="/app/data/downloads" readOnly /><Button disabled>浏览</Button></div>
        <Space wrap><Button type="primary" icon={<Play size={16} />} disabled={!tasks.some((task) => task.status === 'queued' || task.status === 'failed' || task.status === 'paused')} onClick={() => { const task = tasks.find((item) => ['queued', 'failed', 'paused'].includes(item.status)); if (task) void taskAction(task, 'start') }}>开始下载</Button><Button icon={<Pause size={16} />} disabled>暂停</Button><Button icon={<Play size={16} />} disabled>继续</Button><Button icon={<XCircle size={16} />} onClick={() => { const task = tasks.find((item) => ['queued', 'downloading'].includes(item.status)); if (task) void taskAction(task, 'cancel') }}>取消</Button><Button icon={<Trash2 size={16} />} onClick={() => { const task = tasks.find((item) => ['completed', 'failed', 'cancelled'].includes(item.status)); if (task) void taskAction(task, 'delete') }}>删除选中</Button><Button icon={<Eraser size={16} />} onClick={() => { tasks.filter((task) => ['completed', 'failed', 'cancelled'].includes(task.status)).forEach((task) => void taskAction(task, 'delete')) }}>清空列表</Button></Space>
      </Card>
    </div> : <div className="download-config">
      <Card className="download-config-group" title={<span><Settings2 size={18} /> 下载选项</span>}>
        <div className="download-settings-grid">
          <label>视频质量<Select value={settings.quality} onChange={(value) => update('quality', value)} options={[['best', '最佳质量'], ['2160', '2160p (4K)'], ['1440', '1440p'], ['1080', '1080p'], ['720', '720p'], ['480', '480p'], ['360', '360p']].map(([value, label]) => ({ value, label }))} /></label>
          <label>下载类型<Select value={settings.download_type} onChange={(value) => update('download_type', value)} options={[['video_audio', '视频+音频'], ['video', '仅视频'], ['audio', '仅音频']].map(([value, label]) => ({ value, label }))} /></label>
          <Checkbox checked={settings.save_thumbnail} onChange={(event) => update('save_thumbnail', event.target.checked)}>下载视频时同时保存封面图（高清）</Checkbox>
        </div>
      </Card>
      <Card className="download-config-group" title="视频兼容性转码">
        <Checkbox checked={settings.transcode_enabled} onChange={(event) => update('transcode_enabled', event.target.checked)}>下载完成后转为高兼容 MP4（H.264 + AAC）</Checkbox>
        <label className="download-inline-field">转码质量<Select disabled={!settings.transcode_enabled} value={settings.transcode_quality} onChange={(value) => update('transcode_quality', value)} options={[['fast', '快速'], ['balanced', '平衡（推荐）'], ['high', '高质量']].map(([value, label]) => ({ value, label }))} /></label>
        <Checkbox disabled={!settings.transcode_enabled} checked={settings.keep_original} onChange={(event) => update('keep_original', event.target.checked)}>转码成功后保留原文件</Checkbox>
        <Typography.Paragraph type="secondary">开启后会在视频下载完成后调用 ffmpeg 重新编码，提升播放器兼容性。</Typography.Paragraph>
      </Card>
      <Card className="download-config-group" title={<span><ShieldCheck size={18} /> Cookies 设置</span>}>
        <Checkbox checked={settings.cookies_enabled} onChange={(event) => update('cookies_enabled', event.target.checked)}>使用 Cookies（解决验证问题）</Checkbox>
        {settings.cookies_set && <Alert type="success" showIcon message="已保存一份加密 Cookies" />}
        <Input.TextArea value={cookies} onChange={(event) => setCookies(event.target.value)} disabled={!settings.cookies_enabled} rows={7} placeholder="请粘贴 Netscape 格式 Cookies 文本。Cookies 仅保存在本地并加密存储。" />
        <Space wrap><Button icon={<CheckCircle2 size={16} />} loading={cookieTesting} disabled={!cookies.trim()} onClick={() => void testCookies()}>测试 Cookies</Button><Button icon={<Eraser size={16} />} disabled={!settings.cookies_set && !cookies} onClick={() => void clearCookies()}>清除 Cookies</Button></Space>
        <Typography.Paragraph type="secondary">推荐使用浏览器扩展导出 YouTube 的 Netscape 格式 Cookies，再粘贴到这里。</Typography.Paragraph>
      </Card>
      <div className="download-config-actions"><Button type="primary" loading={saving} onClick={() => void save()}>保存下载配置</Button></div>
    </div>}
  </div>
}
