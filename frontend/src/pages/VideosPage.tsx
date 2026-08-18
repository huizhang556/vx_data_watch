import { useEffect, useMemo, useState } from 'react'
import { Alert, DatePicker, Empty, Progress, Segmented, Skeleton, Table, Typography } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import ReactECharts from 'echarts-for-react'
import { api, query } from '../api'
import { useAccount } from '../account'
import { disableUnavailableDate, useAvailableDates } from '../dateRange'
import type { VideoRangeAnalytics, VideoRow } from '../types'

const periodOptions = [
  { label: '单日', value: 1 }, { label: '近 3 天', value: 3 }, { label: '近 7 天', value: 7 },
  { label: '近 15 天', value: 15 }, { label: '近 30 天', value: 30 },
]

export default function VideosPage() {
  const { account } = useAccount()
  const availableDates = useAvailableDates(account?.id)
  const [endDate, setEndDate] = useState<Dayjs>(dayjs().subtract(1, 'day'))
  const [startDate, setStartDate] = useState<Dayjs>(() => dayjs().subtract(1, 'day'))
  const [days, setDays] = useState(1)
  const [data, setData] = useState<VideoRangeAnalytics | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    if (!account) { setData(null); return }
    const start = startDate.format('YYYY-MM-DD')
    const end = endDate.format('YYYY-MM-DD')
    setLoading(true); setError('')
    api<VideoRangeAnalytics>(`/api/analytics/videos?${query({ account_id: account.id, start_date: start, end_date: end })}`)
      .then(setData).catch((cause) => setError(cause instanceof Error ? cause.message : '加载失败')).finally(() => setLoading(false))
  }, [account, startDate, endDate, days])

  const pieOption = useMemo(() => {
    const top = data?.videos.slice(0, 10) || []
    const other = (data?.videos.slice(10) || []).reduce((sum, row) => sum + row.plays, 0)
    const rows = [...top.map((row) => ({ name: row.title, value: row.plays })), ...(other ? [{ name: '其他视频', value: other }] : [])]
    return {
      animation: false,
      tooltip: { trigger: 'item', formatter: '{b}<br/>{c} 次 ({d}%)' },
      legend: { type: 'scroll', orient: 'vertical', right: 0, top: 20, bottom: 20, width: '38%' },
      series: [{ type: 'pie', radius: ['40%', '70%'], center: ['31%', '50%'], minAngle: 2, data: rows,
        label: { show: false }, emphasis: { label: { show: true, formatter: '{b}\n{d}%' } },
      }],
    }
  }, [data])

  if (!account) return <Empty description="请先创建视频号账号" />
  return (
    <div className="page">
      <div className="page-heading dashboard-heading">
        <div><Typography.Title level={2}>视频贡献</Typography.Title><Typography.Text type="secondary">按所选时间新增播放量汇总 · 数据范围：{startDate.format('YYYY-MM-DD')} 至 {endDate.format('YYYY-MM-DD')}</Typography.Text></div>
        <div className="date-controls"><Segmented value={periodOptions.some((item) => item.value === days) ? days : 0} onChange={(value) => { const nextDays = Number(value); if (!nextDays) { setDays(0); return }; setDays(nextDays); setStartDate(endDate.subtract(nextDays - 1, 'day')) }} options={[...periodOptions, { label: '自定义', value: 0 }]} /><DatePicker disabledDate={(value) => disableUnavailableDate(value, availableDates)} aria-label="开始日期" placeholder="开始日期" allowClear={false} value={startDate} onChange={(value) => { if (!value) return; const next = value.isAfter(endDate, 'day') ? endDate : value; setStartDate(next); setDays(endDate.diff(next, 'day') + 1) }} /><DatePicker disabledDate={(value) => disableUnavailableDate(value, availableDates)} aria-label="结束日期" placeholder="结束日期" allowClear={false} value={endDate} onChange={(value) => { if (!value) return; const next = value.isBefore(startDate, 'day') ? startDate : value; setEndDate(next); setDays(next.diff(startDate, 'day') + 1) }} /></div>
      </div>
      {error && <Alert type="error" showIcon message={error} />}
      {!loading && data && data.days_with_data < days && <Alert type="warning" showIcon message="当前数据量不足" description={`当前数据库仅有 ${data.days_with_data}/${days} 天数据，所选时间段的逐视频统计可能不完整，请先导入缺少日期的数据。`} />}
      {loading ? <Skeleton active /> : !data?.videos.length ? <Empty description="所选时间暂无逐视频数据" /> : <>
        <section className="reconcile-strip">
          <div><span>账号总量</span><strong>{data.reconciliation?.account_total.toLocaleString()}</strong></div>
          <div><span>明细合计</span><strong>{data.reconciliation?.video_total.toLocaleString()}</strong></div>
          <div><span>未归属流量</span><strong>{data.reconciliation?.difference.toLocaleString()}</strong></div>
          <div><span>覆盖率</span><strong>{data.reconciliation?.coverage ?? 0}%</strong></div>
        </section>
        <section className="section-band"><div className="section-heading"><Typography.Title level={3}>播放贡献构成</Typography.Title><Typography.Text type="secondary">前 10 条单列，其余合并</Typography.Text></div><ReactECharts option={pieOption} style={{ height: 380 }} notMerge /></section>
        <div className="desktop-table">
          <Table<VideoRow> rowKey="id" dataSource={data.videos} pagination={{ pageSize: 20, showSizeChanger: false }} columns={[
            { title: '视频', dataIndex: 'title', ellipsis: true },
            { title: '发布时间', dataIndex: 'published_at', width: 170, render: (value) => value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '未知' },
            { title: '新增播放', dataIndex: 'plays', width: 110, sorter: (a, b) => a.plays - b.plays, defaultSortOrder: 'descend', render: (value) => value.toLocaleString() },
            { title: '所选期占比', dataIndex: 'share', width: 180, render: (value) => <Progress percent={value} size="small" /> },
            { title: '点赞', dataIndex: 'likes', width: 80, render: (value) => value ?? '暂无' },
            { title: '评论', dataIndex: 'comments', width: 80, render: (value) => value ?? '暂无' },
            { title: '分享', dataIndex: 'shares', width: 80, render: (value) => value ?? '暂无' },
          ]} />
        </div>
        <div className="mobile-video-list">
          {data.videos.map((video, index) => <article key={video.id} className="video-item"><div className="rank">{index + 1}</div><div className="video-body"><strong>{video.title}</strong><span>{video.plays.toLocaleString()} 次播放 · {video.share}%</span><Progress percent={video.share} showInfo={false} size="small" /></div></article>)}
        </div>
      </>}
    </div>
  )
}
