import { useState } from 'react'
import { Button, Card, Descriptions, Form, Input, Typography, Upload, message } from 'antd'
import { Edit3, RotateCcw, Save, X } from 'lucide-react'
import dayjs from 'dayjs'
import { api } from '../api'
import { useAuth } from '../auth'
import type { User } from '../types'
import { UserAvatar } from '../components/UserAvatar'

const usernameRules = [
  { required: true, message: '请输入用户名' },
  { min: 3, message: '用户名至少需要 3 个字符' },
  { pattern: /^[A-Za-z0-9_.-]+$/, message: '用户名只能包含英文、数字、下划线、点和短横线' },
]

type ProfileValues = { username: string; email?: string; avatar?: string }
const avatarValue = (value?: string) => value && value !== 'default' ? value : 'default'

export default function ProfilePage() {
  const { user, updateUser } = useAuth()
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [form] = Form.useForm<ProfileValues>()
  const avatar = Form.useWatch('avatar', form)
  const draftUsername = Form.useWatch('username', form)

  const beginEdit = () => {
    form.setFieldsValue({ username: user.username, email: user.email || '', avatar: avatarValue(user.avatar) })
    setEditing(true)
  }
  const cancelEdit = () => { form.resetFields(); setEditing(false) }
  const restoreDefaultAvatar = () => form.setFieldValue('avatar', 'default')

  const save = async (values: ProfileValues) => {
    const current = { username: user.username, email: user.email || '', avatar: avatarValue(user.avatar) }
    const next = { username: values.username.trim(), email: values.email?.trim() || '', avatar: avatarValue(values.avatar) }
    if (next.username === current.username && next.email === current.email && next.avatar === current.avatar) {
      message.info('没有需要保存的修改')
      return
    }
    setBusy(true)
    try {
      const saved = await api<User>('/api/auth/profile', { method: 'PUT', body: JSON.stringify({ username: next.username, email: next.email || null, avatar: next.avatar }) })
      updateUser(saved)
      setEditing(false)
      message.success('个人资料已保存')
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : '个人资料保存失败')
    } finally { setBusy(false) }
  }

  const readAvatar = (file: File) => {
    if (!file.type.startsWith('image/')) { message.error('只能上传图片'); return false }
    if (file.size > 1_500_000) { message.error('头像不能超过 1.5 MB'); return false }
    const reader = new FileReader()
    reader.onload = () => form.setFieldValue('avatar', String(reader.result))
    reader.readAsDataURL(file)
    return false
  }

  const avatarPicker = editing
    ? <Upload accept="image/*" showUploadList={false} beforeUpload={readAvatar}><button type="button" className="profile-avatar-button" title="点击上传头像" aria-label="点击上传头像"><UserAvatar size={72} username={draftUsername || user.username} avatar={avatar} role={user.role} level={user.level} /></button></Upload>
    : <UserAvatar size={72} username={user.username} avatar={user.avatar} role={user.role} level={user.level} />

  const actionButtons = <div className="profile-summary-actions">
    {editing && <Button type="text" icon={<RotateCcw size={16} />} onClick={restoreDefaultAvatar}>恢复默认</Button>}
    {editing ? <Button icon={<X size={16} />} onClick={cancelEdit}>取消编辑</Button> : <Button icon={<Edit3 size={16} />} onClick={beginEdit}>编辑</Button>}
    {editing && <Button type="primary" icon={<Save size={16} />} loading={busy} onClick={() => void form.submit()}>保存</Button>}
  </div>

  return <div className="page">
    <div className="page-heading"><div><Typography.Title level={2}>个人资料</Typography.Title><Typography.Text type="secondary">查看和编辑当前登录用户信息</Typography.Text></div></div>
    <Card className="tool-section profile-card" bordered>
      <Form form={form} layout="vertical" onFinish={save}>
        <div className="profile-summary">
          {avatarPicker}
          <div className="profile-summary-details">
            {editing ? <Form.Item name="username" label="用户名" rules={usernameRules}><Input /></Form.Item> : <><Typography.Title level={3}>{user.username}</Typography.Title><Typography.Text type="secondary">{user.role}</Typography.Text></>}
            {editing && <Typography.Text type="secondary">角色：{user.role}</Typography.Text>}
          </div>
          {actionButtons}
        </div>
        {editing
          ? <div className="profile-edit-fields"><Form.Item name="email" label="注册邮箱" rules={[{ type: 'email', message: '请输入有效邮箱' }]}><Input type="email" /></Form.Item><Typography.Text type="secondary">邮箱必须唯一，不能与其他用户重复。</Typography.Text></div>
          : <Descriptions bordered column={1} items={[{ key: 'username', label: '用户名', children: user.username }, { key: 'email', label: '注册邮箱', children: user.email || '未绑定' }, { key: 'role', label: '角色', children: user.role }, { key: 'level', label: '等级', children: user.role === 'admin' ? '管理员' : user.level === 2 ? '超级会员' : user.level === 1 ? '会员用户' : '普通用户' }, { key: 'status', label: '状态', children: user.is_active === false ? '停用' : '启用' }, { key: 'id', label: '用户编号', children: user.id }, { key: 'created', label: '注册时间', children: user.created_at ? dayjs(user.created_at).format('YYYY-MM-DD HH:mm') : '未知' }, { key: 'login', label: '最近登录', children: user.last_login_at ? dayjs(user.last_login_at).format('YYYY-MM-DD HH:mm') : '从未登录' }]} />}
      </Form>
    </Card>
  </div>
}
