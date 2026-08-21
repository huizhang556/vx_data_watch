import { Card, Descriptions, Typography } from 'antd'
import { useAuth } from '../auth'

export default function ProfilePage() {
  const { user } = useAuth()
  return <div className="page">
    <div className="page-heading"><div><Typography.Title level={2}>个人资料</Typography.Title><Typography.Text type="secondary">查看当前登录用户信息</Typography.Text></div></div>
    <Card className="tool-section" bordered>
      <Descriptions bordered column={1} items={[
        { key: 'username', label: '用户名', children: user.username },
        { key: 'role', label: '角色', children: user.role },
        { key: 'id', label: '用户编号', children: user.id },
      ]} />
    </Card>
  </div>
}
