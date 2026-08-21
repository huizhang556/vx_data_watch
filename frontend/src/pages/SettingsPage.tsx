import { useEffect, useState } from 'react'
import { Alert, Button, Empty, Form, Input, Modal, Select, Table, Tag, Typography, message } from 'antd'
import { DatabaseBackup, Download, KeyRound, Plus, ShieldCheck, UserPlus, UserRound } from 'lucide-react'
import dayjs from 'dayjs'
import { api, setCsrfToken } from '../api'
import { useAccount } from '../account'
import { useAuth } from '../auth'

interface Backup { filename: string; size: number; modified_at: string }
interface LocalUser { id: number; username: string; role: string; is_active: boolean; created_at: string }

export default function SettingsPage() {
  const { accounts, reloadAccounts } = useAccount()
  const { user } = useAuth()
  const [open, setOpen] = useState(false)
  const [userOpen, setUserOpen] = useState(false)
  const [passwordOpen, setPasswordOpen] = useState(false)
  const [usernameOpen, setUsernameOpen] = useState(false)
  const [backups, setBackups] = useState<Backup[]>([])
  const [users, setUsers] = useState<LocalUser[]>([])
  const [loading, setLoading] = useState(false)
  const loadBackups = () => api<Backup[]>('/api/backups').then(setBackups)
  const loadUsers = () => user.role === 'admin' ? api<LocalUser[]>('/api/users').then(setUsers) : Promise.resolve()
  useEffect(() => {
    if (user.role === 'admin') { void loadBackups(); void loadUsers() }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
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
  const changeUsername = async (values: { username: string }) => {
    setLoading(true)
    try { await api('/api/auth/username', { method: 'POST', body: JSON.stringify(values) }); setUsernameOpen(false); message.success('用户名已修改') }
    catch (cause) { message.error(cause instanceof Error ? cause.message : '修改失败') }
    finally { setLoading(false) }
  }
  return (
    <div className="page">
      <div className="page-heading"><div><Typography.Title level={2}>系统设置</Typography.Title><Typography.Text type="secondary">账号、数据安全与备份</Typography.Text></div></div>
      <section className="section-band">
        <div className="section-heading"><Typography.Title level={3}>视频号账号</Typography.Title>{user.role !== 'viewer' && <Button type="primary" icon={<Plus size={18} />} onClick={() => setOpen(true)}>新增账号</Button>}</div>
        {!accounts.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有视频号账号" /> : <div className="account-list">{accounts.map((account) => <article key={account.id}><div className="account-icon">号</div><div><strong>{account.name}</strong><span>{account.description || '暂无备注'}</span></div><Tag color="green">使用中</Tag></article>)}</div>}
      </section>
      <section className="section-band">
        <div className="section-heading"><div><Typography.Title level={3}>本地用户</Typography.Title><Typography.Text type="secondary">当前用户：{user.username}（{user.role}）</Typography.Text></div><div><Button icon={<UserRound size={18} />} onClick={() => setUsernameOpen(true)}>修改用户名</Button><Button icon={<KeyRound size={18} />} onClick={() => setPasswordOpen(true)} style={{ marginLeft: 8 }}>修改密码</Button>{user.role === 'admin' && <Button type="primary" icon={<UserPlus size={18} />} onClick={() => setUserOpen(true)} style={{ marginLeft: 8 }}>新增用户</Button>}</div></div>
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
      <section className="security-note"><ShieldCheck size={24} /><div><strong>本地安全模式</strong><p>密码使用 Argon2id，AI Key 使用 AES-256-GCM。主密钥保存在数据目录的独立受限文件中，请与备份一同妥善保管。</p></div></section>
      <Alert type="warning" showIcon message="恢复备份需要停止应用" description="使用项目 README 中的命令行恢复步骤，避免覆盖正在使用的数据库。" />
      <Modal title="新增视频号账号" open={open} onCancel={() => setOpen(false)} footer={null} destroyOnHidden><Form layout="vertical" onFinish={createAccount} requiredMark={false}><Form.Item name="name" label="账号名称" rules={[{ required: true }]}><Input maxLength={120} /></Form.Item><Form.Item name="description" label="备注"><Input.TextArea maxLength={500} rows={3} /></Form.Item><Button block type="primary" htmlType="submit" loading={loading}>创建</Button></Form></Modal>
      <Modal title="新增本地用户" open={userOpen} onCancel={() => setUserOpen(false)} footer={null} destroyOnHidden><Form layout="vertical" onFinish={createUser} initialValues={{ role: 'viewer' }} requiredMark={false}><Form.Item name="username" label="用户名" rules={[{ required: true }, { min: 3 }]}><Input /></Form.Item><Form.Item name="password" label="初始密码" rules={[{ required: true }, { min: 10 }]}><Input.Password autoComplete="new-password" /></Form.Item><Form.Item name="role" label="角色"><Select options={[{ value: 'admin', label: '管理员' }, { value: 'editor', label: '编辑者' }, { value: 'viewer', label: '只读者' }]} /></Form.Item><Button block type="primary" htmlType="submit" loading={loading}>创建用户</Button></Form></Modal>
      <Modal title="修改密码" open={passwordOpen} onCancel={() => setPasswordOpen(false)} footer={null} destroyOnHidden><Form layout="vertical" onFinish={changePassword} requiredMark={false}><Form.Item name="current_password" label="当前密码" rules={[{ required: true }]}><Input.Password autoComplete="current-password" /></Form.Item><Form.Item name="new_password" label="新密码" rules={[{ required: true }, { min: 10 }]}><Input.Password autoComplete="new-password" /></Form.Item><Button block type="primary" htmlType="submit" loading={loading}>修改并撤销其他会话</Button></Form></Modal>
      <Modal title="修改用户名" open={usernameOpen} onCancel={() => setUsernameOpen(false)} footer={null} destroyOnHidden><Form layout="vertical" onFinish={changeUsername} initialValues={{ username: user.username }} requiredMark={false}><Form.Item name="username" label="新用户名" rules={[{ required: true }, { min: 3 }]}><Input autoComplete="username" /></Form.Item><Button block type="primary" htmlType="submit" loading={loading}>保存</Button></Form></Modal>
    </div>
  )
}
