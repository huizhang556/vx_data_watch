import { useEffect, useState } from 'react'
import { Alert, Button, Empty, Form, Input, Modal, Select, Space, Table, Tag, Typography, message } from 'antd'
import { CloudDownload, DatabaseBackup, Download, KeyRound, Plus, RefreshCw, ShieldCheck, UserPlus } from 'lucide-react'
import dayjs from 'dayjs'
import { api, setCsrfToken } from '../api'
import { useAccount } from '../account'
import { useAuth } from '../auth'
import type { SystemUpdateStatus, SystemVersionInfo } from '../types'

interface Backup { filename: string; size: number; modified_at: string }
interface LocalUser { id: number; username: string; role: string; is_active: boolean; created_at: string }

export default function SettingsPage() {
  const { accounts, reloadAccounts } = useAccount()
  const { user } = useAuth()
  const [open, setOpen] = useState(false)
  const [userOpen, setUserOpen] = useState(false)
  const [passwordOpen, setPasswordOpen] = useState(false)
  const [backups, setBackups] = useState<Backup[]>([])
  const [users, setUsers] = useState<LocalUser[]>([])
  const [loading, setLoading] = useState(false)
  const [versionInfo, setVersionInfo] = useState<SystemVersionInfo | null>(null)
  const [versionError, setVersionError] = useState('')
  const [versionLoading, setVersionLoading] = useState(false)
  const [targetVersion, setTargetVersion] = useState<string>()
  const [updateStatus, setUpdateStatus] = useState<SystemUpdateStatus | null>(null)
  const [updateStarting, setUpdateStarting] = useState(false)
  const loadBackups = () => api<Backup[]>('/api/backups').then(setBackups)
  const loadUsers = () => user.role === 'admin' ? api<LocalUser[]>('/api/users').then(setUsers) : Promise.resolve()
  const loadVersions = async () => {
    setVersionLoading(true); setVersionError('')
    try {
      const result = await api<SystemVersionInfo>('/api/system/versions')
      setVersionInfo(result)
      setTargetVersion((current) => result.versions.some((row) => row.version === current) ? current : result.versions[0]?.version)
    } catch (cause) { setVersionError(cause instanceof Error ? cause.message : '无法获取版本信息') }
    finally { setVersionLoading(false) }
  }
  const loadUpdateStatus = async () => {
    try { setUpdateStatus(await api<SystemUpdateStatus>('/api/system/update-status')) }
    catch { /* The app may be temporarily unavailable while its container restarts. */ }
  }
  useEffect(() => {
    if (user.role === 'admin') { void loadBackups(); void loadUsers(); void loadVersions(); void loadUpdateStatus() }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!updateStatus || !['queued', 'pulling', 'restarting', 'verifying', 'rolling_back'].includes(updateStatus.state)) return
    const timer = window.setInterval(() => void loadUpdateStatus(), 2000)
    return () => window.clearInterval(timer)
  }, [updateStatus?.state]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const pendingId = window.sessionStorage.getItem('vx_update_id')
    if (updateStatus?.state !== 'success' || !pendingId || pendingId !== updateStatus.id) return
    const timer = window.setTimeout(() => { window.sessionStorage.removeItem('vx_update_id'); window.location.reload() }, 1500)
    return () => window.clearTimeout(timer)
  }, [updateStatus?.id, updateStatus?.state])
  const createAccount = async (values: { name: string; description?: string }) => {
    setLoading(true)
    try { await api('/api/accounts', { method: 'POST', body: JSON.stringify(values) }); await reloadAccounts(); setOpen(false); message.success('视频号账号已创建') }
    catch (cause) { message.error(cause instanceof Error ? cause.message : '创建失败') }
    finally { setLoading(false) }
  }
  const backup = async () => {
    setLoading(true)
    try { await api('/api/backups', { method: 'POST' }); await loadBackups(); message.success('加密备份已创建并完成完整性检查') }
    catch (cause) { message.error(cause instanceof Error ? cause.message : '备份失败') }
    finally { setLoading(false) }
  }
  const createUser = async (values: { username: string; password: string; role: string }) => {
    setLoading(true)
    try { await api('/api/users', { method: 'POST', body: JSON.stringify(values) }); await loadUsers(); setUserOpen(false); message.success('本地用户已创建') }
    catch (cause) { message.error(cause instanceof Error ? cause.message : '创建失败') }
    finally { setLoading(false) }
  }
  const changePassword = async (values: { current_password: string; new_password: string }) => {
    setLoading(true)
    try { const result = await api<{ csrf_token: string }>('/api/auth/change-password', { method: 'POST', body: JSON.stringify(values) }); setCsrfToken(result.csrf_token); setPasswordOpen(false); message.success('密码已修改，其他会话已撤销') }
    catch (cause) { message.error(cause instanceof Error ? cause.message : '修改失败') }
    finally { setLoading(false) }
  }
  const startUpdate = () => {
    if (!targetVersion) return
    Modal.confirm({
      title: `更新到 ${targetVersion}？`,
      content: '系统会先创建加密备份，再拉取镜像并重启应用。重启期间页面可能短暂断开，请不要关闭 Docker。',
      okText: '备份并更新', cancelText: '取消',
      onOk: async () => {
        setUpdateStarting(true)
        try {
          const result = await api<SystemUpdateStatus>('/api/system/update', { method: 'POST', body: JSON.stringify({ version: targetVersion }) })
          if (result.id) window.sessionStorage.setItem('vx_update_id', result.id)
          setUpdateStatus(result); message.success('更新任务已提交')
        } catch (cause) { message.error(cause instanceof Error ? cause.message : '更新任务提交失败') }
        finally { setUpdateStarting(false) }
      },
    })
  }
  const updateActive = !!updateStatus && ['queued', 'pulling', 'restarting', 'verifying', 'rolling_back'].includes(updateStatus.state)
  const statusType = updateStatus?.state === 'failed' ? 'error' : updateStatus?.state === 'success' ? 'success' : 'info'
  return (
    <div className="page">
      <div className="page-heading"><div><Typography.Title level={2}>系统设置</Typography.Title><Typography.Text type="secondary">账号、数据安全与备份</Typography.Text></div></div>
      <section className="section-band">
        <div className="section-heading"><Typography.Title level={3}>视频号账号</Typography.Title>{user.role !== 'viewer' && <Button type="primary" icon={<Plus size={18} />} onClick={() => setOpen(true)}>新增账号</Button>}</div>
        {!accounts.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有视频号账号" /> : <div className="account-list">{accounts.map((account) => <article key={account.id}><div className="account-icon">号</div><div><strong>{account.name}</strong><span>{account.description || '暂无备注'}</span></div><Tag color="green">使用中</Tag></article>)}</div>}
      </section>
      <section className="section-band">
        <div className="section-heading"><div><Typography.Title level={3}>本地用户</Typography.Title><Typography.Text type="secondary">当前用户：{user.username}（{user.role}）</Typography.Text></div><div><Button icon={<KeyRound size={18} />} onClick={() => setPasswordOpen(true)}>修改密码</Button>{user.role === 'admin' && <Button type="primary" icon={<UserPlus size={18} />} onClick={() => setUserOpen(true)} style={{ marginLeft: 8 }}>新增用户</Button>}</div></div>
        {user.role === 'admin' && <Table size="small" rowKey="id" pagination={false} dataSource={users} columns={[{ title: '用户名', dataIndex: 'username' }, { title: '角色', dataIndex: 'role', render: (value) => <Tag>{value}</Tag> }, { title: '状态', dataIndex: 'is_active', render: (value) => <Tag color={value ? 'green' : 'default'}>{value ? '启用' : '停用'}</Tag> }, { title: '创建时间', dataIndex: 'created_at', render: (value) => dayjs(value).format('YYYY-MM-DD HH:mm') }]} />}
      </section>
      <section className="section-band">
        <div className="section-heading"><div><Typography.Title level={3}>加密备份</Typography.Title><Typography.Text type="secondary">使用 SQLite 在线备份 API，不复制正在写入的数据库</Typography.Text></div>{user.role === 'admin' && <Button icon={<DatabaseBackup size={18} />} loading={loading} onClick={() => void backup()}>创建备份</Button>}</div>
        {!backups.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无备份" /> : <Table size="small" rowKey="filename" pagination={false} dataSource={backups} columns={[
          { title: '文件', dataIndex: 'filename', ellipsis: true },
          { title: '大小', dataIndex: 'size', render: (value) => `${(value / 1024).toFixed(1)} KB` },
          { title: '时间', dataIndex: 'modified_at', render: (value) => dayjs(value).format('YYYY-MM-DD HH:mm') },
          { title: '', render: (_, row) => <Button type="text" icon={<Download size={18} />} title="下载备份" href={`/api/backups/${encodeURIComponent(row.filename)}`} /> },
        ]} />}
      </section>
      {user.role === 'admin' && <section className="section-band">
        <div className="section-heading"><div><Typography.Title level={3}>在线更新</Typography.Title><Typography.Text type="secondary">从 Docker Hub 检测正式版本并重启应用</Typography.Text></div><Button icon={<RefreshCw size={18} />} loading={versionLoading} onClick={() => void loadVersions()}>检测更新</Button></div>
        {versionError && <Alert type="error" showIcon message="版本检测失败" description={versionError} />}
        {versionInfo && <div className="update-panel">
          <div className="version-summary"><div><span>当前版本</span><strong>v{versionInfo.current_version}</strong></div><div><span>最新版本</span><strong>{versionInfo.latest_version ? `v${versionInfo.latest_version}` : '暂未发布'}</strong></div><div><span>镜像仓库</span><strong>{versionInfo.repository}</strong></div></div>
          {!versionInfo.update_supported ? <Alert type="warning" showIcon message="当前为源码部署" description="可以在线检测版本，但自动拉取和重启只在 Docker Compose 部署中启用。源码部署请在终端执行 git pull 后重新启动。" /> : versionInfo.versions.length ? <div className="update-actions"><Select aria-label="目标版本" value={targetVersion} onChange={setTargetVersion} options={versionInfo.versions.map((row) => ({ value: row.version, label: `v${row.version}${row.version === versionInfo.latest_version ? '（最新）' : ''}` }))} /><Button type="primary" icon={<CloudDownload size={18} />} loading={updateStarting || updateActive} disabled={!targetVersion} onClick={startUpdate}>更新并重启</Button></div> : <Alert type="success" showIcon message={versionInfo.latest_version ? '当前已经是最新版本' : '镜像仓库暂时没有正式版本标签'} />}
          {updateStatus && updateStatus.state !== 'idle' && <Alert className="update-status" type={statusType} showIcon message={updateStatus.message || '正在处理更新'} description={<Space wrap><span>{updateStatus.target_version ? `目标版本：v${updateStatus.target_version}` : ''}</span>{updateStatus.state === 'success' && <span>页面即将刷新</span>}</Space>} />}
        </div>}
      </section>}
      <section className="security-note"><ShieldCheck size={24} /><div><strong>本地安全模式</strong><p>密码使用 Argon2id，AI Key 使用 AES-256-GCM。主密钥保存在数据目录的独立受限文件中，请与备份一同妥善保管。</p></div></section>
      <Alert type="warning" showIcon message="恢复备份需要停止应用" description="使用项目 README 中的命令行恢复步骤，避免覆盖正在使用的数据库。" />
      <Modal title="新增视频号账号" open={open} onCancel={() => setOpen(false)} footer={null} destroyOnHidden><Form layout="vertical" onFinish={createAccount} requiredMark={false}><Form.Item name="name" label="账号名称" rules={[{ required: true }]}><Input maxLength={120} /></Form.Item><Form.Item name="description" label="备注"><Input.TextArea maxLength={500} rows={3} /></Form.Item><Button block type="primary" htmlType="submit" loading={loading}>创建</Button></Form></Modal>
      <Modal title="新增本地用户" open={userOpen} onCancel={() => setUserOpen(false)} footer={null} destroyOnHidden><Form layout="vertical" onFinish={createUser} initialValues={{ role: 'viewer' }} requiredMark={false}><Form.Item name="username" label="用户名" rules={[{ required: true }, { min: 3 }]}><Input /></Form.Item><Form.Item name="password" label="初始密码" rules={[{ required: true }, { min: 10 }]}><Input.Password autoComplete="new-password" /></Form.Item><Form.Item name="role" label="角色"><Select options={[{ value: 'admin', label: '管理员' }, { value: 'editor', label: '编辑者' }, { value: 'viewer', label: '只读者' }]} /></Form.Item><Button block type="primary" htmlType="submit" loading={loading}>创建用户</Button></Form></Modal>
      <Modal title="修改密码" open={passwordOpen} onCancel={() => setPasswordOpen(false)} footer={null} destroyOnHidden><Form layout="vertical" onFinish={changePassword} requiredMark={false}><Form.Item name="current_password" label="当前密码" rules={[{ required: true }]}><Input.Password autoComplete="current-password" /></Form.Item><Form.Item name="new_password" label="新密码" rules={[{ required: true }, { min: 10 }]}><Input.Password autoComplete="new-password" /></Form.Item><Button block type="primary" htmlType="submit" loading={loading}>修改并撤销其他会话</Button></Form></Modal>
    </div>
  )
}
