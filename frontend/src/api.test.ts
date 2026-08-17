import { describe, expect, it } from 'vitest'
import { query } from './api'

describe('query', () => {
  it('encodes defined query values', () => {
    expect(query({ account_id: 2, metric_date: '2026-08-16', omitted: undefined }))
      .toBe('account_id=2&metric_date=2026-08-16')
  })
})
