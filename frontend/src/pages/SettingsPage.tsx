import { useEffect, useState } from 'react'
import { Button, Empty, Form, Input, InputNumber, Modal, Popconfirm, Select, Switch, Table, Tag, Typography, message } from 'antd'
import { Pencil, Plus, Trash2, UserPlus } from 'lucide-react'
import dayjs from 'dayjs'
import { api } from '../api'
import { useAccount } from '../account'
import { useAuth } from '../auth'

interface LocalUser { id: number; username: string; email?: string; role: string; is_active: boolean; created_at: string; last_login_at?: string }
interface AuthSettings { registration_enabled: boolean; smtp_host?: string; smtp_port: number; smtp_username?: string; smtp_password?: string; smtp_from?: string; smtp_starttls: boolean; smtp_ssl: boolean; verification_code_minutes: number; smtp_password_set?: boolean; captcha_enabled: boolean; captcha_provider: string; captcha_site_key?: string; captcha_secret_key?: string; captcha_secret_key_set?: boolean }
const usernameRules = [{ required: true, message: '请输入用户名' }, { min: 3, max: 80, message: '用户名长度应为 3-80 个字符' }, { pattern: /^[A-Za-z0-9_.-]+$/, message: '用户名只能包含英文、数字、下划线、点和短横线' }]
const passwordRules = [{ required: true, message: '请输入密码' }, { min: 10, max: 200, message: '密码长度应为 10-200 个字符' }, { pattern: /^(?=.*[A-Za-z])(?=.*\d).+$/, message: '密码至少 10 位，并同时包含字母和数字' }]
const optionalPasswordRules = [{ min: 10, max: 200, message: '密码长度应为 10-200 个字符' }, { pattern: /^(?=.*[A-Za-z])(?=.*\d).+$/, message: '密码至少 10 位，并同时包含字母和数字' }]

export default function SettingsPage() {
  const { accounts, reloadAccounts } = useAccount()
  const { user } = useAuth()
  const [open, setOpen] = useState(false)
  const [userOpen, setUserOpen] = useState(false)
  const [editUserOpen, setEditUserOpen] = useState(false)
  const [editingUser, setEditingUser] = useState<LocalUser | null>(null)
  const [users, setUsers] = useState<LocalUser[]>([])
  const [authSettings, setAuthSettings] = useState<AuthSettings | null>(null)
  const [testRecipient, setTestRecipient] = useState('')
  const [loading, setLoading] = useState(false)
  const loadUsers = () => user.role === 'admin' ? api<LocalUser[]>('/api/users').then(setUsers) : Promise.resolve()
  const [authForm] = Form.useForm<AuthSettings>()
  const [captchaForm] = Form.useForm<AuthSettings>()
  const loadAuthSettings = () => user.role === 'admin' ? api<AuthSettings>('/api/settings/auth').then((value) => { setAuthSettings(value); authForm.setFieldsValue(value); captchaForm.setFieldsValue(value) }) : Promise.resolve()
  useEffect(() => {
    if (user.role === 'admin') { void loadUsers(); void loadAuthSettings() }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const saveAuthSettings = async (values: Partial<AuthSettings>, notify = true, successMessage = '邮箱与注册配置已保存') => {
    setLoading(true)
    try {
      const saved = await api<AuthSettings>('/api/settings/auth', { method: 'PUT', body: JSON.stringify(values) })
      setAuthSettings(saved)
      authForm.setFieldsValue(saved)
      captchaForm.setFieldsValue(saved)
      if (notify) message.success(successMessage)
      return saved
    } catch (cause) {
      if (notify) message.error(cause instanceof Error ? cause.message : '保存邮箱配置失败')
      throw cause
    } finally { setLoading(false) }
  }
  const testAuthSMTP = async () => {
    if (!testRecipient.trim()) { message.warning('请输入测试收件邮箱'); return }
    setLoading(true)
    try {
      // 测试接口读取数据库配置，因此先保存当前表单中的 SMTP 配置。
      const smtpValues = await authForm.validateFields([
        'registration_enabled', 'smtp_host', 'smtp_port', 'smtp_username', 'smtp_password',
        'smtp_from', 'smtp_starttls', 'smtp_ssl', 'verification_code_minutes',
      ])
      await saveAuthSettings({ ...authForm.getFieldsValue(), ...smtpValues }, false)
      await api('/api/settings/auth/test', { method: 'POST', body: JSON.stringify({ recipient: testRecipient.trim() }) })
      message.success('测试邮件已发送，请检查收件箱')
    } catch (cause) { message.error(cause instanceof Error ? cause.message : '测试邮件发送失败') }
    finally { setLoading(false) }
  }
  const saveCaptchaSettings = async (values: AuthSettings) => {
    // 人机验证使用独立表单，但后端配置存储仍是一个加密配置对象。
    // 以已保存的邮箱配置作为基线，避免提交人机验证时覆盖 SMTP 设置。
    await saveAuthSettings(values, true, '人机验证配置已保存')
  }
  const createAccount = async (values: { name: string; description?: string }) => {
    setLoading(true)
    try { await api('/api/accounts', { method: 'POST', body: JSON.stringify(values) }); await reloadAccounts(); setOpen(false); message.success('视频号账号已创建') }
    catch (cause) { message.error(cause instanceof Error ? cause.message : '创建失败') }
    finally { setLoading(false) }
  }
  const createUser = async (values: { username: string; email: string; password: string; role: string }) => {
    setLoading(true)
    try { await api('/api/users', { method: 'POST', body: JSON.stringify(values) }); await loadUsers(); setUserOpen(false); message.success('本地用户已创建') }
    catch (cause) { message.error(cause instanceof Error ? cause.message : '创建失败') }
    finally { setLoading(false) }
  }
  const updateUser = async (values: { email?: string; password?: string; role?: string; is_active?: boolean }) => {
    if (!editingUser) return
    setLoading(true)
    try { await api(`/api/users/${editingUser.id}`, { method: 'PATCH', body: JSON.stringify(values) }); await loadUsers(); setEditUserOpen(false); message.success('用户信息已保存') }
    catch (cause) { message.error(cause instanceof Error ? cause.message : '保存用户失败') }
    finally { setLoading(false) }
  }
  const deleteUser = async (row: LocalUser) => {
    try { await api(`/api/users/${row.id}`, { method: 'DELETE' }); await loadUsers(); message.success('用户已删除') }
    catch (cause) { message.error(cause instanceof Error ? cause.message : '删除用户失败') }
  }
  return (
    <div className="page">
      <div className="page-heading"><div><Typography.Title level={2}>系统设置</Typography.Title><Typography.Text type="secondary">账号、数据安全与备份</Typography.Text></div></div>
      <section className="section-band auth-settings-section">
        <div className="section-heading"><div><Typography.Title level={3}>邮箱与注册</Typography.Title><Typography.Text type="secondary">注册验证码和密码重置使用此 SMTP 配置，密码会加密保存。</Typography.Text></div></div>
        {user.role === 'admin' && <Form form={authForm} layout="vertical" onFinish={saveAuthSettings} initialValues={{ smtp_port: 587, smtp_starttls: true, smtp_ssl: false, verification_code_minutes: 10 }} requiredMark={false} className="auth-settings-form">
          <Form.Item name="registration_enabled" label="允许邮箱注册" valuePropName="checked"><Switch /></Form.Item>
          <Form.Item name="smtp_host" label="SMTP 服务器" rules={[{ required: true, message: '请输入 SMTP 服务器地址' }]}><Input placeholder="例如 smtp.qq.com" /></Form.Item>
          <Form.Item name="smtp_port" label="SMTP 端口" rules={[{ required: true, message: '请输入端口' }, { type: 'number', min: 1, max: 65535, message: '端口范围为 1-65535' }]}><InputNumber min={1} max={65535} style={{ width: 190 }} /></Form.Item>
          <Form.Item name="smtp_username" label="SMTP 用户名"><Input autoComplete="off" /></Form.Item>
          <Form.Item name="smtp_password" label={authSettings?.smtp_password_set ? 'SMTP 密码（留空保持原密码）' : 'SMTP 密码'} rules={authSettings?.smtp_password_set ? optionalPasswordRules : passwordRules}><Input.Password autoComplete="new-password" /></Form.Item>
          <Form.Item name="smtp_from" label="发件人地址" rules={[{ required: true, message: '请输入发件人邮箱' }, { type: 'email', message: '请输入有效的发件人邮箱' }]}><Input placeholder="noreply@example.com" /></Form.Item>
          <Form.Item name="smtp_starttls" label="连接方式" valuePropName="value"><Select options={[{ value: true, label: 'STARTTLS（587）' }, { value: false, label: 'SSL（465）' }]} /></Form.Item>
          <Form.Item name="smtp_ssl" label="SSL 连接（465）"><Select options={[{ value: true, label: '开启' }, { value: false, label: '关闭' }]} /></Form.Item>
          <Form.Item name="verification_code_minutes" label="验证码有效期（分钟）" rules={[{ required: true, message: '请输入验证码有效期' }, { type: 'number', min: 1, max: 60, message: '有效期范围为 1-60 分钟' }]}><InputNumber min={1} max={60} style={{ width: 190 }} /></Form.Item>
          <div className="settings-actions"><Button type="primary" htmlType="submit" loading={loading}>保存邮箱配置</Button><Input value={testRecipient} onChange={(event) => setTestRecipient(event.target.value)} placeholder="测试收件邮箱" /><Button onClick={() => void testAuthSMTP()} loading={loading}>发送测试邮件</Button></div>
        </Form>}
        {user.role === 'admin' && <Form form={captchaForm} layout="vertical" onFinish={saveCaptchaSettings} requiredMark={false} className="captcha-settings-form">
          <Typography.Title level={3}>人机验证</Typography.Title><Typography.Text type="secondary">登录、注册和重置密码的人机验证配置</Typography.Text>
          <Form.Item name="captcha_enabled" label="启用人机验证" valuePropName="checked"><Switch /></Form.Item>
          <Form.Item name="captcha_provider" label="验证服务商"><Select options={[{ value: 'turnstile', label: 'Cloudflare Turnstile' }]} /></Form.Item>
          <Form.Item name="captcha_site_key" label="站点密钥" rules={[{ required: true, message: '请输入 Turnstile 站点密钥' }]}><Input /></Form.Item>
          <Form.Item name="captcha_secret_key" label={authSettings?.captcha_secret_key_set ? '私密密钥（留空保持原密钥）' : '私密密钥'} rules={authSettings?.captcha_secret_key_set ? [] : [{ required: true, message: '请输入 Turnstile 私密密钥' }]}><Input.Password autoComplete="new-password" /></Form.Item>
          <Button type="primary" htmlType="submit" loading={loading}>保存人机验证配置</Button>
        </Form>}
      </section>
      <section className="section-band">
        <div className="section-heading"><Typography.Title level={3}>视频号账号</Typography.Title>{user.role !== 'viewer' && <Button type="primary" icon={<Plus size={18} />} onClick={() => setOpen(true)}>新增账号</Button>}</div>
        {!accounts.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有视频号账号" /> : <div className="account-list">{accounts.map((account) => <article key={account.id}><div className="account-icon">号</div><div><strong>{account.name}</strong><span>{account.description || '暂无备注'}</span></div><Tag color="green">使用中</Tag></article>)}</div>}
      </section>
      <section className="section-band">
        <div className="section-heading"><div><Typography.Title level={3}>本地用户</Typography.Title><Typography.Text type="secondary">当前用户：{user.username}（{user.role}）</Typography.Text></div>{user.role === 'admin' && <Button type="primary" icon={<UserPlus size={18} />} onClick={() => setUserOpen(true)}>新增用户</Button>}</div>
        {user.role === 'admin' && <Table size="small" rowKey="id" pagination={false} dataSource={users} columns={[{ title: '用户名', dataIndex: 'username' }, { title: '注册邮箱', dataIndex: 'email', render: (value) => value || '未绑定' }, { title: '角色', dataIndex: 'role', render: (value) => <Tag>{value}</Tag> }, { title: '状态', dataIndex: 'is_active', render: (value) => <Tag color={value ? 'green' : 'default'}>{value ? '启用' : '停用'}</Tag> }, { title: '注册时间', dataIndex: 'created_at', render: (value) => dayjs(value).format('YYYY-MM-DD HH:mm') }, { title: '最近登录', dataIndex: 'last_login_at', render: (value) => value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '从未登录' }, { title: '操作', render: (_, row) => <><Button type="text" icon={<Pencil size={16} />} onClick={() => { setEditingUser(row); setEditUserOpen(true) }} /><Popconfirm title="删除用户" description={`确定删除 ${row.username} 吗？`} okText="删除" cancelText="取消" okButtonProps={{ danger: true }} onConfirm={() => void deleteUser(row)}><Button type="text" danger icon={<Trash2 size={16} />} /></Popconfirm></> }]} />}
      </section>
      <Modal title="新增视频号账号" open={open} onCancel={() => setOpen(false)} footer={null} destroyOnHidden><Form layout="vertical" onFinish={createAccount} requiredMark={false}><Form.Item name="name" label="账号名称" rules={[{ required: true }]}><Input maxLength={120} /></Form.Item><Form.Item name="description" label="备注"><Input.TextArea maxLength={500} rows={3} /></Form.Item><Button block type="primary" htmlType="submit" loading={loading}>创建</Button></Form></Modal>
      <Modal title="新增本地用户" open={userOpen} onCancel={() => setUserOpen(false)} footer={null} destroyOnHidden><Form layout="vertical" onFinish={createUser} initialValues={{ role: 'viewer' }} requiredMark={false}><Form.Item name="username" label="用户名" rules={usernameRules}><Input autoComplete="username" /></Form.Item><Form.Item name="email" label="注册邮箱" rules={[{ required: true, type: 'email', message: '请输入有效的注册邮箱' }]}><Input autoComplete="email" /></Form.Item><Form.Item name="password" label="初始密码" rules={passwordRules}><Input.Password autoComplete="new-password" /></Form.Item><Form.Item name="role" label="角色"><Select options={[{ value: 'admin', label: '管理员' }, { value: 'editor', label: '编辑者' }, { value: 'viewer', label: '只读者' }]} /></Form.Item><Button block type="primary" htmlType="submit" loading={loading}>创建用户</Button></Form></Modal>
      <Modal title="编辑用户" open={editUserOpen} onCancel={() => setEditUserOpen(false)} footer={null} destroyOnHidden><Form layout="vertical" onFinish={updateUser} initialValues={{ email: editingUser?.email, role: editingUser?.role, is_active: editingUser?.is_active }} requiredMark={false}><Form.Item name="email" label="注册邮箱" rules={[{ required: true, type: 'email', message: '请输入有效的注册邮箱' }]}><Input type="email" /></Form.Item><Form.Item name="password" label="新密码（留空不修改）" rules={optionalPasswordRules}><Input.Password autoComplete="new-password" /></Form.Item><Form.Item name="role" label="角色"><Select options={[{ value: 'admin', label: '管理员' }, { value: 'editor', label: '编辑者' }, { value: 'viewer', label: '只读者' }]} /></Form.Item><Form.Item name="is_active" label="账号状态"><Select options={[{ value: true, label: '启用' }, { value: false, label: '停用' }]} /></Form.Item><Button block type="primary" htmlType="submit" loading={loading}>保存用户修改</Button></Form></Modal>
    </div>
  )
}
