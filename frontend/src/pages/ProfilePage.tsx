import { Avatar, Card, Descriptions, Typography } from 'antd'
import { useAuth } from '../auth'
import dayjs from 'dayjs'

export default function ProfilePage() {
  const { user } = useAuth()
  return <div className="page">
    <div className="page-heading"><div><Typography.Title level={2}>个人资料</Typography.Title><Typography.Text type="secondary">查看当前登录用户信息</Typography.Text></div></div>
    <Card className="tool-section profile-card" bordered>
      <div className="profile-summary"><Avatar size={72} src={user.avatar && user.avatar !== 'default' ? user.avatar : undefined}>{user.username.slice(0, 1).toUpperCase()}</Avatar><div><Typography.Title level={3}>{user.username}</Typography.Title><Typography.Text type="secondary">{user.role}</Typography.Text></div></div>
      <Descriptions bordered column={1} items={[
        { key: 'username', label: '用户名', children: user.username },
        { key: 'email', label: '注册邮箱', children: user.email || '未绑定' },
        { key: 'role', label: '角色', children: user.role },
        { key: 'status', label: '状态', children: user.is_active === false ? '停用' : '启用' },
        { key: 'id', label: '用户编号', children: user.id },
        { key: 'created', label: '注册时间', children: user.created_at ? dayjs(user.created_at).format('YYYY-MM-DD HH:mm') : '未知' },
        { key: 'login', label: '最近登录', children: user.last_login_at ? dayjs(user.last_login_at).format('YYYY-MM-DD HH:mm') : '从未登录' },
      ]} />
    </Card>
  </div>
}
