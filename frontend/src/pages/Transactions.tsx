import { TransactionTable } from '../components/TransactionTable'

export function TransactionsPage() {
  return (
    <div className="h-[calc(100vh-3.5rem)] max-w-[1720px] mx-auto px-4 sm:px-6 lg:px-8 py-6 flex flex-col">
      <TransactionTable />
    </div>
  )
}
