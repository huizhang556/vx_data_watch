import { useState } from 'react'
import { Avatar, Button, Card, Descriptions, Form, Input, Space, Upload, Typography, message } from 'antd'
import { Edit3, Save, Upload as UploadIcon, X } from 'lucide-react'
import dayjs from 'dayjs'
import { api } from '../api'
import { useAuth } from '../auth'
import type { User } from '../types'

const usernameRules = [{ required: true, message: '请输入用户名' }, { min: 3, message: '用户名至少需要 3 个字符' }, { pattern: /^[A-Za-z0-9_.-]+$/, message: '用户名只能包含英文、数字、下划线、点和短横线' }]

export default function ProfilePage() {
  const { user, updateUser } = useAuth()
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [form] = Form.useForm<{ username: string; email?: string; avatar?: string }>()
  const avatar = Form.useWatch('avatar', form)
  const draftUsername = Form.useWatch('username', form)
  const beginEdit = () => { form.setFieldsValue({ username: user.username, email: user.email || '', avatar: user.avatar !== 'default' ? user.avatar : undefined }); setEditing(true) }
  const save = async (values: { username: string; email?: string; avatar?: string }) => {
    setBusy(true)
    try { const next = await api<User>('/api/auth/profile', { method: 'PUT', body: JSON.stringify({ ...values, email: values.email || null, avatar: values.avatar || 'default' }) }); updateUser(next); setEditing(false); message.success('个人资料已保存') }
    catch (cause) { message.error(cause instanceof Error ? cause.message : '保存失败') }
    finally { setBusy(false) }
  }
  const readAvatar = (file: File) => { if (!file.type.startsWith('image/')) { message.error('只能上传图片'); return false } if (file.size > 1_500_000) { message.error('头像不能超过 1.5 MB'); return false } const reader = new FileReader(); reader.onload = () => form.setFieldValue('avatar', String(reader.result)); reader.readAsDataURL(file); return false }
  const avatarPicker = <Upload accept="image/*" showUploadList={false} beforeUpload={readAvatar}><button type="button" className="profile-avatar-button" title="点击上传头像" aria-label="点击上传头像"><Avatar size={72} src={avatar && avatar !== 'default' ? avatar : undefined}>{(draftUsername || user.username).slice(0, 1).toUpperCase()}</Avatar></button></Upload>
  return <div className="page">
    <div className="page-heading"><div><Typography.Title level={2}>个人资料</Typography.Title><Typography.Text type="secondary">查看和编辑当前登录用户信息</Typography.Text></div><Button icon={editing ? <X size={16} /> : <Edit3 size={16} />} onClick={() => editing ? setEditing(false) : beginEdit()}>{editing ? '取消' : '编辑'}</Button></div>
    <Card className="tool-section profile-card" bordered>
      {editing ? <Form form={form} layout="vertical" onFinish={save}>
        <div className="profile-summary">{avatarPicker}<div><Form.Item name="username" label="用户名" rules={usernameRules}><Input /></Form.Item><Typography.Text type="secondary">角色：{user.role}</Typography.Text></div></div>
        <Form.Item name="email" label="注册邮箱" rules={[{ type: 'email', message: '请输入有效邮箱' }]}><Input type="email" /></Form.Item>
        <Form.Item name="avatar" label="自定义头像"><Space><Upload accept="image/*" showUploadList={false} beforeUpload={readAvatar}><Button icon={<UploadIcon size={15} />}>选择图片</Button></Upload>{avatar && <Button type="link" onClick={() => form.setFieldValue('avatar', 'default')}>恢复默认</Button>}</Space></Form.Item>
        <Button type="primary" htmlType="submit" icon={<Save size={16} />} loading={busy}>保存</Button>
      </Form> : <><div className="profile-summary"><Avatar size={72} src={user.avatar && user.avatar !== 'default' ? user.avatar : undefined}>{user.username.slice(0, 1).toUpperCase()}</Avatar><div><Typography.Title level={3}>{user.username}</Typography.Title><Typography.Text type="secondary">{user.role}</Typography.Text></div></div><Descriptions bordered column={1} items={[{ key: 'username', label: '用户名', children: user.username }, { key: 'email', label: '注册邮箱', children: user.email || '未绑定' }, { key: 'role', label: '角色', children: user.role }, { key: 'status', label: '状态', children: user.is_active === false ? '停用' : '启用' }, { key: 'id', label: '用户编号', children: user.id }, { key: 'created', label: '注册时间', children: user.created_at ? dayjs(user.created_at).format('YYYY-MM-DD HH:mm') : '未知' }, { key: 'login', label: '最近登录', children: user.last_login_at ? dayjs(user.last_login_at).format('YYYY-MM-DD HH:mm') : '从未登录' }]} /></>}
    </Card>
  </div>
}
