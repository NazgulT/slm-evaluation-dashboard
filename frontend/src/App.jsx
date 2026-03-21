import { useState, useEffect, useCallback } from 'react'
import {
  getStatus,
  getResults,
  getValidationSummary,
  getVariance,
  getSystemProfile,
  triggerRun,
  triggerTemperatureRun,
} from './api'
import PerformanceChart from './PerformanceChart'
import MetricsTable from './MetricsTable'
import ValidationPanel from './ValidationPanel'
import TemperatureChart from './TemperatureChart'

const POLL_INTERVAL_MS = 3000

function parseUploadedCsv(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => {
      try {
        const text = (r.result || '').trim()
        const lines = text.split(/\r?\n/)
        if (!lines.length) return resolve([])
        const parseRow = (line) => {
          const vals = (line.match(/("(?:[^"]|"")*"|[^,]*)/g) || []).map((v) =>
            v.replace(/^"|"$/g, '').replace(/""/g, '"').trim()
          )
          return vals
        }
        const headers = parseRow(lines[0])
        const rows = []
        for (let i = 1; i < lines.length; i++) {
          const vals = parseRow(lines[i])
          const row = {}
          headers.forEach((h, j) => { row[h] = vals[j] ?? '' })
          rows.push(row)
        }
        resolve(rows)
      } catch (e) {
        reject(e)
      }
    }
    r.onerror = () => reject(new Error('Failed to read file'))
    r.readAsText(file)
  })
}

function downloadCsv(data, filename) {
  if (!data.length) return
  const headers = Object.keys(data[0])
  const csv = [headers.join(','), ...data.map((row) => headers.map((h) => JSON.stringify(row[h] ?? '')).join(','))].join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  a.click()
  URL.revokeObjectURL(a.href)
}

export default function App() {
  const [tab, setTab] = useState('phase1')
  const [status, setStatus] = useState({ status: 'idle' })
  const [results, setResults] = useState([])
  const [validationSummary, setValidationSummary] = useState({})
  const [variance, setVariance] = useState({ results: [], by_model_prompt: {} })
  const [systemBanner, setSystemBanner] = useState('')
  const [comparisonResults, setComparisonResults] = useState([])
  const [comparisonLabel, setComparisonLabel] = useState('')
  const [error, setError] = useState(null)
  const [runningPhase, setRunningPhase] = useState(null)

  const refresh = useCallback(async () => {
    setError(null)
    try {
      const [s, r, vsum, v, prof] = await Promise.all([
        getStatus(),
        getResults().then((d) => d.results || []),
        getValidationSummary().then((d) => d.summary || {}),
        getVariance().then((d) => ({ results: d.results || [], by_model_prompt: d.by_model_prompt || {} })),
        getSystemProfile().then((d) => d.banner || ''),
      ])
      setStatus(s)
      setResults(r)
      setValidationSummary(vsum)
      setVariance(v)
      setSystemBanner(prof)
    } catch (e) {
      setError(e.message)
    }
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, POLL_INTERVAL_MS)
    return () => clearInterval(id)
  }, [refresh])

  const handleRun = async (phase) => {
    setError(null)
    setRunningPhase(phase)
    try {
      if (phase === 3) await triggerTemperatureRun()
      else await triggerRun(phase)
      await refresh()
    } catch (e) {
      setError(e.message)
    } finally {
      setRunningPhase(null)
    }
  }

  const isRunning = status.status === 'running'

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-stone-700 bg-stone-900/80 px-6 py-4">
        <h1 className="text-xl font-semibold text-amber-400">SLM Evaluation Dashboard</h1>
        <div className="mt-2 flex flex-wrap items-center gap-4">
          <span className={`text-sm font-medium ${isRunning ? 'text-amber-400' : 'text-stone-400'}`}>
            Status: {status.status}
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => handleRun(1)}
              disabled={isRunning}
              className="rounded bg-stone-700 px-3 py-1.5 text-sm font-medium text-stone-200 hover:bg-stone-600 disabled:opacity-50"
            >
              Run Phase 1
            </button>
            <button
              onClick={() => handleRun(2)}
              disabled={isRunning}
              className="rounded bg-stone-700 px-3 py-1.5 text-sm font-medium text-stone-200 hover:bg-stone-600 disabled:opacity-50"
            >
              Run Phase 2
            </button>
            <button
              onClick={() => handleRun(3)}
              disabled={isRunning}
              className="rounded bg-stone-700 px-3 py-1.5 text-sm font-medium text-stone-200 hover:bg-stone-600 disabled:opacity-50"
            >
              Run Phase 3
            </button>
          </div>
        </div>
        {error && <p className="mt-2 text-sm text-red-400">{error}</p>}
      </header>

      {systemBanner && (
        <div className="border-b border-stone-700 bg-stone-800/60 px-6 py-2 text-center text-sm text-stone-500">
          {systemBanner}
        </div>
      )}

      <nav className="flex border-b border-stone-700 bg-stone-900/50">
        {[
          { id: 'phase1', label: 'Phase 1 — Performance' },
          { id: 'phase2', label: 'Phase 2 — Validation' },
          { id: 'phase3', label: 'Phase 3 — Temperature' },
        ].map(({ id, label }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`px-6 py-3 text-sm font-medium transition-colors ${
              tab === id ? 'border-b-2 border-amber-500 text-amber-400' : 'text-stone-400 hover:text-stone-200'
            }`}
          >
            {label}
          </button>
        ))}
      </nav>

      <main className="flex-1 overflow-auto p-6">
        {tab === 'phase1' && (
          <>
            <div className="mb-4 flex items-start justify-between gap-6">
              <div>
                <h2 className="text-lg font-medium text-stone-300">Inference performance</h2>
                <p className="mt-1 max-w-3xl text-sm text-stone-400">
                  Phase 1 measures how fast each model responds by tracking time to first token (TTFT),
                  overall tokens per second (TPS), and end-to-end latency for every prompt–model pair.
                  TTFT tells you how quickly a user sees any output, while TPS and latency describe sustained throughput.
                  Together these metrics give a concrete sense of which models feel snappy vs sluggish on your machine.
                </p>
              </div>
              <div className="flex items-center gap-3">
              <label className="flex items-center gap-2 text-sm text-stone-400">
                Compare with
                <input
                  type="file"
                  accept=".csv"
                  className="hidden"
                  onChange={async (e) => {
                    const f = e.target.files?.[0]
                    if (!f) return
                    try {
                      const rows = await parseUploadedCsv(f)
                      setComparisonResults(rows)
                      setComparisonLabel(f.name)
                    } catch (err) {
                      setError('Failed to parse uploaded CSV')
                    }
                    e.target.value = ''
                  }}
                />
                <span className="cursor-pointer rounded bg-stone-700 px-3 py-1.5 text-stone-200 hover:bg-stone-600">
                  Upload results.csv
                </span>
              </label>
              {comparisonResults.length > 0 && (
                <button
                  type="button"
                  onClick={() => { setComparisonResults([]); setComparisonLabel('') }}
                  className="text-xs text-stone-500 hover:text-stone-300"
                >
                  Clear
                </button>
              )}
              <button
                onClick={() => downloadCsv(results, 'results.csv')}
                disabled={!results.length}
                className="rounded bg-stone-700 px-3 py-1.5 text-sm text-stone-200 hover:bg-stone-600 disabled:opacity-50"
              >
                Download CSV
              </button>
            </div>
            </div>
            <PerformanceChart
              results={results}
              comparisonResults={comparisonResults}
              comparisonLabel={comparisonLabel}
            />
            <MetricsTable results={results} showValidation={false} />
          </>
        )}
        {tab === 'phase2' && (
          <>
            <div className="mb-4 flex items-start justify-between gap-6">
              <div>
                <h2 className="text-lg font-medium text-stone-300">Structured output validation</h2>
                <p className="mt-1 max-w-3xl text-sm text-stone-400">
                  Phase 2 checks whether models can reliably follow a strict JSON schema with
                  fields for answer, reasoning, and confidence. It records how often models succeed
                  on the first try, how often a single retry fixes malformed JSON, and how often
                  they still fail. This helps you compare models on robustness for tool-calling or
                  API-style use cases where well-formed structure matters more than raw speed.
                </p>
              </div>
              <button
                onClick={() => downloadCsv(results, 'results.csv')}
                disabled={!results.length}
                className="mt-1 rounded bg-stone-700 px-3 py-1.5 text-sm text-stone-200 hover:bg-stone-600 disabled:opacity-50"
              >
                Download CSV
              </button>
            </div>
            <ValidationPanel results={results} summary={validationSummary} />
          </>
        )}
        {tab === 'phase3' && (
          <>
            <div className="mb-4 flex items-start justify-between gap-6">
              <div>
                <h2 className="text-lg font-medium text-stone-300">Temperature variance</h2>
                <p className="mt-1 max-w-3xl text-sm text-stone-400">
                  Phase 3 explores how stable or chaotic each model becomes as you increase sampling
                  temperature. It runs the same prompt multiple times at several temperatures and
                  uses Jaccard similarity between token sets to summarise how different the outputs are.
                  High similarity means predictable, repeatable behaviour; low similarity highlights
                  more exploratory or creative regimes that may or may not be desirable for your use case.
                </p>
              </div>
              <button
                onClick={() => downloadCsv(variance.results, 'temperature_runs.csv')}
                disabled={!variance.results.length}
                className="mt-1 rounded bg-stone-700 px-3 py-1.5 text-sm text-stone-200 hover:bg-stone-600 disabled:opacity-50"
              >
                Download CSV
              </button>
            </div>
            <TemperatureChart variance={variance} />
          </>
        )}
      </main>
    </div>
  )
}
