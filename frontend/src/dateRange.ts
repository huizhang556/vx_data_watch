import { useEffect, useState } from 'react'
import dayjs, { type Dayjs } from 'dayjs'
import { api, query } from './api'

export function useAvailableDates(accountId: number | undefined): string[] | null {
  const [dates, setDates] = useState<string[] | null>(null)
  useEffect(() => {
    if (!accountId) { setDates(null); return }
    setDates(null)
    api<{ dates: string[] }>(`/api/analytics/available-dates?${query({ account_id: accountId })}`)
      .then((payload) => setDates(payload.dates)).catch(() => setDates([]))
  }, [accountId])
  return dates
}

export function disableUnavailableDate(value: Dayjs, availableDates: string[] | null): boolean {
  if (value.isAfter(dayjs(), 'day')) return true
  return availableDates !== null && !availableDates.includes(value.format('YYYY-MM-DD'))
}

export function rangeHasAllDates(endDate: Dayjs, days: number, availableDates: string[] | null): boolean {
  if (availableDates === null) return true
  return Array.from({ length: days }, (_, index) => endDate.subtract(index, 'day').format('YYYY-MM-DD'))
    .every((date) => availableDates.includes(date))
}
