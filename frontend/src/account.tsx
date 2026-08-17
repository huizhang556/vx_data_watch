import { createContext, useContext } from 'react'
import type { Account } from './types'

export interface AccountContextValue {
  accounts: Account[]
  account: Account | null
  setAccountId: (id: number) => void
  reloadAccounts: () => Promise<void>
}
export const AccountContext = createContext<AccountContextValue | null>(null)

export function useAccount() {
  const value = useContext(AccountContext)
  if (!value) throw new Error('AccountContext is missing')
  return value
}
