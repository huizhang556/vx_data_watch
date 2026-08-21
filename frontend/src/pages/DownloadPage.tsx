import { Card, Empty, Typography } from 'antd'
import { Download, Settings2 } from 'lucide-react'

export default function DownloadPage({ mode = 'content' }: { mode?: 'config' | 'content' }) {
  const isConfig = mode === 'config'
  return <div className="page">
    <div className="page-heading"><div><Typography.Title level={2}>{isConfig ? '下载配置' : '下载内容'}</Typography.Title><Typography.Text type="secondary">{isConfig ? '配置视频下载任务和保存策略' : '查看和管理已提交的视频下载内容'}</Typography.Text></div></div>
    <Card className="tool-section" bordered>
      <Empty image={isConfig ? <Settings2 size={40} strokeWidth={1.5} /> : <Download size={40} strokeWidth={1.5} />} description={isConfig ? '下载配置功能即将开放' : '暂无下载内容'} />
    </Card>
  </div>
}
