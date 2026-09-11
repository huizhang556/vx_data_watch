import { Typography } from 'antd'
import { useLocation } from 'react-router-dom'
import OnlineUpdateSection from '../components/OnlineUpdateSection'

export default function UpdatesPage() {
  const location = useLocation()
  const autoStart = Boolean((location.state as { autoStart?: boolean } | null)?.autoStart)
  return <div className="page"><div className="page-heading"><div><Typography.Title level={2}>在线更新</Typography.Title><Typography.Text type="secondary">检测正式版本并安全更新应用</Typography.Text></div></div><OnlineUpdateSection autoStart={autoStart} /></div>
}
