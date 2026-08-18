import { useEffect, useMemo, useState } from 'react'
import { Alert, DatePicker, Empty, Segmented, Skeleton, Statistic, Typography } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import ReactECharts from 'echarts-for-react'
import { useNavigate } from 'react-router-dom'
import { api, query } from '../api'
import { useAccount } from '../account'
import { disableUnavailableDate, useAvailableDates } from '../dateRange'
import type { RangeAnalytics } from '../types'

type MetricKey = 'plays' | 'likes' | 'comments' | 'shares' | 'follows' | 'recommendations'

const metrics: Array<{ key: MetricKey; label: string; color: string }> = [
  { key: 'plays', label: '播放', color: '#1677ff' },
  { key: 'likes', label: '点赞', color: '#d4380d' },
  { key: 'comments', label: '评论', color: '#722ed1' },
  { key: 'shares', label: '分享', color: '#d48806' },
  { key: 'follows', label: '关注', color: '#08979c' },
  { key: 'recommendations', label: '收藏', color: '#389e0d' },
]

const periodOptions = [
  { label: '单日', value: 1 },
  { label: '近 3 天', value: 3 },
  { label: '近 7 天', value: 7 },
  { label: '近 15 天', value: 15 },
  { label: '近 30 天', value: 30 },
]

function compareMarkup(current: number | null, previous: number | null | undefined) {
  if (current === null || previous === null || previous === undefined) return '<span class="trend-na">暂无数据</span>'
  if (current === previous) return '<span class="trend-flat">→</span>'
  const delta = previous === 0 ? null : Math.abs((current - previous) / previous * 100)
  const suffix = delta === null ? '' : ` ${delta.toFixed(1)}%`
  return current > previous
    ? `<span class="trend-up">↑${suffix}</span>`
    : `<span class="trend-down">↓${suffix}</span>`
}

export default function DashboardPage() {
  const { account } = useAccount()
  const availableDates = useAvailableDates(account?.id)
  const navigate = useNavigate()
  const [endDate, setEndDate] = useState<Dayjs>(dayjs().subtract(1, 'day'))
  const [startDate, setStartDate] = useState<Dayjs>(() => dayjs().subtract(1, 'day'))
  const [days, setDays] = useState(1)
  const [data, setData] = useState<RangeAnalytics | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [rangeWarning, setRangeWarning] = useState('')
  const [aiHistory, setAiHistory] = useState<{ id: number; start_date: string; end_date: string; created_at: string } | null>(null)

  useEffect(() => {
    if (!account) { setData(null); return }
    const start = startDate.format('YYYY-MM-DD')
    const end = endDate.format('YYYY-MM-DD')
    setLoading(true); setError('')
    api<RangeAnalytics>(`/api/analytics/range?${query({ account_id: account.id, start_date: start, end_date: end })}`)
      .then((snapshot) => {
        setData(snapshot)
        setRangeWarning(snapshot.days_with_data < days
          ? `当前数据库仅有 ${snapshot.days_with_data}/${days} 天数据，当前时间段的数据不足，部分统计结果可能不完整。请先导入缺少日期的数据。`
          : '')
      })
      .catch((cause) => setError(cause instanceof Error ? cause.message : '加载失败'))
      .finally(() => setLoading(false))
  }, [account, startDate, endDate, days])

  useEffect(() => {
    if (!account) { setAiHistory(null); return }
    const start = startDate.format('YYYY-MM-DD')
    const end = endDate.format('YYYY-MM-DD')
    api<Array<{ id: number; start_date: string; end_date: string; created_at: string }>>(`/api/ai/reports?${query({ account_id: account.id })}`)
      .then((rows) => setAiHistory(rows.find((row) => row.start_date === start && row.end_date === end) || null))
      .catch(() => setAiHistory(null))
  }, [account, startDate, endDate, days])

  const previousByDate = useMemo(() => new Map(
    data?.previous_trend.map((row) => [row.date, row]) || [],
  ), [data])

  const trendOption = useMemo(() => ({
    animation: false,
    color: metrics.map((item) => item.color),
    tooltip: {
      trigger: 'axis', confine: true,
      formatter: (params: Array<{ dataIndex: number }>) => {
        const index = params[0]?.dataIndex ?? 0
        const row = data?.trend[index]
        if (!row) return ''
        const previous = previousByDate.get(dayjs(row.date).subtract(days, 'day').format('YYYY-MM-DD'))
        const rows = [
          ...metrics.map((metric) => ({ label: metric.label, current: row[metric.key], previous: previous?.[metric.key] })),
          { label: '转发', current: null, previous: null },
        ]
        const order = ['播放', '点赞', '评论', '分享', '关注', '转发', '收藏']
        rows.sort((a, b) => order.indexOf(a.label) - order.indexOf(b.label))
        return `<div class="trend-tooltip"><strong>${row.date}</strong>${rows.map((item) =>
          `<div><span>${item.label}：${item.current === null ? '暂无数据' : Number(item.current).toLocaleString()}</span>${compareMarkup(item.current, item.previous)}</div>`
        ).join('')}</div>`
      },
    },
    legend: { top: 0, type: 'scroll', data: metrics.map((item) => item.label) },
    grid: { left: 52, right: 48, top: 50, bottom: 38 },
    xAxis: { type: 'category', data: data?.trend.map((row) => dayjs(row.date).format('MM-DD')) || [] },
    yAxis: [
      { type: 'value', name: '播放', splitLine: { lineStyle: { color: '#edf0ee' } } },
      { type: 'value', name: '互动', splitLine: { show: false } },
    ],
    series: metrics.map((metric) => ({
      name: metric.label, type: 'line', smooth: true, symbolSize: 6,
      yAxisIndex: metric.key === 'plays' ? 0 : 1,
      data: data?.trend.map((row) => row[metric.key]) || [], connectNulls: false,
    })),
  }), [data, days, previousByDate])

  const pieOption = useMemo(() => ({
    animation: false,
    color: metrics.slice(1).map((item) => item.color),
    tooltip: { trigger: 'item', formatter: '{b}<br/>{c} ({d}%)' },
    legend: { type: 'scroll', bottom: 0 },
    series: [{ type: 'pie', radius: ['42%', '68%'], center: ['50%', '44%'],
      data: metrics.slice(1).map((metric) => ({ name: metric.label, value: data?.totals[metric.key] ?? 0 })),
      label: { formatter: '{b}\n{d}%' },
    }],
  }), [data])

  const barOption = useMemo(() => ({
    animation: false,
    color: ['#1677ff', '#b8c2cc'],
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { top: 0, data: ['本期', '上期'] },
    grid: { left: 56, right: 18, top: 44, bottom: 38 },
    xAxis: { type: 'category', data: metrics.map((item) => item.label) },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: '#edf0ee' } } },
    series: [
      { name: '本期', type: 'bar', data: metrics.map((item) => data?.totals[item.key] ?? null) },
      { name: '上期', type: 'bar', data: metrics.map((item) => data?.previous_totals[item.key] ?? null) },
    ],
  }), [data])

  if (!account) return <Empty description="请先在系统设置中创建视频号账号" />
  const hasData = Boolean(data?.trend.length)
  return (
    <div className="page">
      <div className="page-heading dashboard-heading">
        <div><Typography.Title level={2}>数据概览</Typography.Title><Typography.Text type="secondary">{account.name} · 数据范围：{startDate.format('YYYY-MM-DD')} 至 {endDate.format('YYYY-MM-DD')}</Typography.Text></div>
        <div className="date-controls">
          <Segmented value={periodOptions.some((item) => item.value === days) ? days : 0} onChange={(value) => { const nextDays = Number(value); if (!nextDays) { setDays(0); return }; setDays(nextDays); setStartDate(endDate.subtract(nextDays - 1, 'day')) }} options={[...periodOptions, { label: '自定义', value: 0 }]} />
          <DatePicker disabledDate={(value) => disableUnavailableDate(value, availableDates)} aria-label="开始日期" placeholder="开始日期" allowClear={false} value={startDate} onChange={(value) => { if (!value) return; const next = value.isAfter(endDate, 'day') ? endDate : value; setStartDate(next); setDays(endDate.diff(next, 'day') + 1) }} />
          <DatePicker disabledDate={(value) => disableUnavailableDate(value, availableDates)} aria-label="结束日期" placeholder="结束日期" allowClear={false} value={endDate} onChange={(value) => { if (!value) return; const next = value.isBefore(startDate, 'day') ? startDate : value; setEndDate(next); setDays(next.diff(startDate, 'day') + 1) }} />
        </div>
      </div>
      {error && <Alert type="error" showIcon message={error} />}
      {rangeWarning && <Alert type="warning" showIcon message="当前数据量不足" description={rangeWarning} />}
      {loading ? <Skeleton active /> : !hasData ? <Empty description="所选时间暂无数据" /> : <>
        <section className="metric-grid" aria-label="指标汇总">
          {metrics.map((metric) => <div className="metric-card" key={metric.key}>
            <Statistic title={metric.label} value={data?.totals[metric.key] ?? '暂无数据'} />
          </div>)}
          <div className="metric-card"><Statistic title="转发" value="暂无数据" /></div>
        </section>
        <section className="section-band">
          <div className="section-heading"><Typography.Title level={3}>指标趋势</Typography.Title><Typography.Text type="secondary">{data?.start_date} 至 {data?.end_date}</Typography.Text></div>
          <ReactECharts option={trendOption} style={{ height: 360 }} notMerge />
        </section>
        <section className="chart-grid">
          <div className="chart-panel"><Typography.Title level={3}>互动构成</Typography.Title><ReactECharts option={pieOption} style={{ height: 320 }} notMerge /></div>
          <div className="chart-panel"><Typography.Title level={3}>本期与上期</Typography.Title><ReactECharts option={barOption} style={{ height: 320 }} notMerge /></div>
        </section>
        {aiHistory && <section className="section-band ai-history-match">
          <div className="section-heading"><div><Typography.Title level={3}>AI 分析报告记录</Typography.Title><Typography.Text type="secondary">已找到当前查询时间段对应的分析报告</Typography.Text></div></div>
          <div className="history-list"><article><div><strong>查询范围：{aiHistory.start_date} 至 {aiHistory.end_date}</strong><time>查询时间：{dayjs(aiHistory.created_at).format('YYYY-MM-DD HH:mm')}</time></div><button className="link-button" type="button" onClick={() => navigate('/ai', { state: { historyId: aiHistory.id } })}>查看 AI 分析</button></article></div>
        </section>}
      </>}
    </div>
  )
}
