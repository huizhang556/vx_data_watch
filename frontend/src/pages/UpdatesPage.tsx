import { Typography } from 'antd'
import OnlineUpdateSection from '../components/OnlineUpdateSection'

export default function UpdatesPage() {
  return <div className="page"><div className="page-heading"><div><Typography.Title level={2}>在线更新</Typography.Title><Typography.Text type="secondary">检测 Docker Hub 版本并安全更新应用</Typography.Text></div></div><OnlineUpdateSection /></div>
}
