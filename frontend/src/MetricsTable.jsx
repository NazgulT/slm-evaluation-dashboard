import { useState, useMemo } from 'react'

const NUMERIC_KEYS = ['ttft_ms', 'tokens_per_second', 'total_latency_ms', 'token_count', 'normalised_tps']

function sortBy(results, key, dir) {
  return [...results].sort((a, b) => {
    const va = a[key]
    const vb = b[key]
    if (NUMERIC_KEYS.includes(key)) {
      const na = Number(va)
      const nb = Number(vb)
      if (Number.isNaN(na) && Number.isNaN(nb)) return 0
      if (Number.isNaN(na)) return 1
      if (Number.isNaN(nb)) return -1
      return dir === 'asc' ? na - nb : nb - na
    }
    const sa = String(va ?? '')
    const sb = String(vb ?? '')
    return dir === 'asc' ? sa.localeCompare(sb) : sb.localeCompare(sa)
  })
}

export default function MetricsTable({ results, showValidation = false }) {
  const [sortKey, setSortKey] = useState('model')
  const [sortDir, setSortDir] = useState('asc')
  const [modelFilter, setModelFilter] = useState('')
  const [promptFilter, setPromptFilter] = useState('')

  const models = useMemo(() => [...new Set(results.map((r) => r.model).filter(Boolean))].sort(), [results])
  const prompts = useMemo(() => [...new Set(results.map((r) => r.prompt_id).filter(Boolean))].sort(), [results])

  const filtered = useMemo(() => {
    let out = results
    if (modelFilter) out = out.filter((r) => r.model === modelFilter)
    if (promptFilter) out = out.filter((r) => r.prompt_id === promptFilter)
    return out
  }, [results, modelFilter, promptFilter])

  const sorted = useMemo(() => sortBy(filtered, sortKey, sortDir), [filtered, sortKey, sortDir])

  const toggleSort = (key) => {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else setSortKey(key)
  }

  const cols = [
    'model',
    'prompt_id',
    'prompt_category',
    'ttft_ms',
    'tokens_per_second',
    'total_latency_ms',
    'token_count',
    'normalised_tps',
    'machine_id',
  ]
  if (showValidation) cols.push('valid_json', 'retry_used')
  cols.push('error')

  if (!results.length) {
    return (
      <div className="rounded-lg border border-stone-700 bg-stone-900/50 p-6 text-center text-stone-500">
        No results to display.
      </div>
    )
  }

  return (
    <div className="mt-6 space-y-4">
      <div className="flex flex-wrap gap-4">
        <label className="flex items-center gap-2 text-sm text-stone-400">
          Model
          <select
            value={modelFilter}
            onChange={(e) => setModelFilter(e.target.value)}
            className="rounded border border-stone-600 bg-stone-800 px-2 py-1 text-stone-200"
          >
            <option value="">All</option>
            {models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm text-stone-400">
          Prompt
          <select
            value={promptFilter}
            onChange={(e) => setPromptFilter(e.target.value)}
            className="rounded border border-stone-600 bg-stone-800 px-2 py-1 text-stone-200"
          >
            <option value="">All</option>
            {prompts.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="overflow-x-auto rounded-lg border border-stone-700">
        <table className="w-full text-left text-sm">
          <thead className="bg-stone-800/80 text-stone-400">
            <tr>
              {cols.map((key) => (
                <th
                  key={key}
                  className="cursor-pointer select-none border-b border-stone-600 px-4 py-3 font-medium hover:text-stone-200"
                  onClick={() => toggleSort(key)}
                >
                  {key.replace(/_/g, ' ')}
                  {sortKey === key && (sortDir === 'asc' ? ' ↑' : ' ↓')}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-700">
            {sorted.map((row, i) => (
              <tr key={i} className="bg-stone-900/50 hover:bg-stone-800/50">
                {cols.map((key) => (
                  <td key={key} className="px-4 py-2 text-stone-300">
                    {key === 'valid_json' || key === 'retry_used' ? (
                      <Badge value={row[key]} type={key} />
                    ) : (
                      formatCell(row[key], key)
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function formatCell(val, key) {
  if (val == null || val === '') return '—'
  if (NUMERIC_KEYS.includes(key)) {
    const n = Number(val)
    if (Number.isNaN(n)) return val
    if (key === 'token_count') return n
    return typeof n === 'number' ? n.toFixed(2) : val
  }
  const s = String(val)
  return s.length > 80 ? s.slice(0, 80) + '…' : s
}

function Badge({ value, type }) {
  const v = ['true', '1', 'yes'].includes(String(value).toLowerCase())
  const isRetry = type === 'retry_used'
  let color = 'bg-stone-600 text-stone-300'
  if (isRetry) color = v ? 'bg-amber-600/30 text-amber-300' : 'bg-stone-600 text-stone-400'
  else color = v ? 'bg-emerald-600/30 text-emerald-300' : 'bg-red-600/30 text-red-300'
  return <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${color}`}>{v ? 'Yes' : 'No'}</span>
}
