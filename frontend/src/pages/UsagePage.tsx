import { Card, Table, Typography } from 'antd'

const rows = [
  { level: '0 - 普通用户', chat: 'AI 速问 20 次/日', analysis: '数据分析 5 次/日', download: '下载 5 个视频/日' },
  { level: '1 - 会员用户', chat: 'AI 速问 50 次/日', analysis: '数据分析 10 次/日', download: '下载 20 个视频/日' },
  { level: '2 - 超级会员', chat: 'AI 速问 100 次/日', analysis: '数据分析 20 次/日', download: '下载 50 个视频/日' },
  { level: '3 - 管理员', chat: '不限制', analysis: '不限制', download: '不限制' },
]

export default function UsagePage() {
  return <div className="page"><div className="page-heading"><div><Typography.Title level={2}>等级说明</Typography.Title><Typography.Text type="secondary">不同用户等级的每日使用额度</Typography.Text></div></div><Card><Table rowKey="level" pagination={false} dataSource={rows} columns={[{ title: '用户等级', dataIndex: 'level' }, { title: 'AI 速问', dataIndex: 'chat' }, { title: '数据分析', dataIndex: 'analysis' }, { title: '视频下载', dataIndex: 'download' }]} /><Typography.Paragraph type="secondary" style={{ marginTop: 16 }}>下载配置中的 Cookies 由每位用户自行填写和保存。视频分析暂不支持视频文件内容识别。</Typography.Paragraph></Card></div>
}
