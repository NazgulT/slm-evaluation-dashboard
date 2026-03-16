import { useState, useMemo, useEffect } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { getPrompts } from './api'

const LINE_COLORS = ['#f59e0b', '#10b981', '#3b82f6', '#ef4444', '#a855f7']

/**
 * Build line chart data: for each temperature, one point per model (mean Jaccard).
 * by_model_prompt = { model: { prompt_id: [ rows ] } }
 * We need: X = temperature, Y = mean Jaccard; one line per model.
 * Option: aggregate over all prompts per (model, temperature) to get one Y per model per temp.
 */
function buildLineData(variance) {
  const { results } = variance
  if (!results.length) return []

  const byModelTemp = {}
  for (const r of results) {
    const model = r.model || 'unknown'
    const temp = Number(r.temperature)
    if (Number.isNaN(temp)) continue
    const key = `${model}\t${temp}`
    if (!byModelTemp[key]) byModelTemp[key] = { model, temperature: temp, sum: 0, n: 0 }
    byModelTemp[key].sum += Number(r.jaccard_similarity) || 0
    byModelTemp[key].n += 1
  }

  const temps = [...new Set(Object.values(byModelTemp).map((x) => x.temperature))].sort((a, b) => a - b)
  const models = [...new Set(Object.values(byModelTemp).map((x) => x.model))]

  return temps.map((temperature) => {
    const point = { temperature }
    for (const model of models) {
      const key = `${model}\t${temperature}`
      const cell = byModelTemp[key]
      point[model] = cell && cell.n ? Math.round((cell.sum / cell.n) * 1000) / 1000 : null
    }
    return point
  })
}

export default function TemperatureChart({ variance }) {
  const lineData = useMemo(() => buildLineData(variance), [variance])
  const models = useMemo(() => {
    if (!variance.results?.length) return []
    return [...new Set(variance.results.map((r) => r.model).filter(Boolean))].sort()
  }, [variance.results])
  const prompts = useMemo(() => {
    if (!variance.results?.length) return []
    return [...new Set(variance.results.map((r) => r.prompt_id).filter(Boolean))].sort()
  }, [variance.results])

  const [selectedModel, setSelectedModel] = useState(models[0] || '')
  const [selectedPrompt, setSelectedPrompt] = useState(prompts[0] || '')

  const [promptMeta, setPromptMeta] = useState([])

  useEffect(() => {
    let mounted = true
    getPrompts()
      .then((data) => {
        if (!mounted) return
        const list = Array.isArray(data?.prompts) ? data.prompts : []
        setPromptMeta(list)
      })
      .catch(() => {})
    return () => {
      mounted = false
    }
  }, [])

  const promptMap = useMemo(() => {
    const map = {}
    for (const p of promptMeta) {
      if (p?.id) map[p.id] = p
    }
    return map
  }, [promptMeta])

  const selectedPromptMeta = selectedPrompt ? promptMap[selectedPrompt] : undefined

  const comparisonRuns = useMemo(() => {
    if (!selectedModel || !selectedPrompt || !variance.by_model_prompt[selectedModel]?.[selectedPrompt]) return { low: [], high: [] }
    const rows = variance.by_model_prompt[selectedModel][selectedPrompt]
    const low = rows.filter((r) => Number(r.temperature) === 0).sort((a, b) => (a.run_index || 0) - (b.run_index || 0))
    const high = rows.filter((r) => Number(r.temperature) === 1.4).sort((a, b) => (a.run_index || 0) - (b.run_index || 0))
    return { low, high }
  }, [variance.by_model_prompt, selectedModel, selectedPrompt])

  const hasLineData = lineData.length > 0 && models.length > 0

  return (
    <div className="space-y-8">
      <div className="rounded-lg border border-stone-700 bg-stone-900/50 p-4">
        <h3 className="mb-4 text-sm font-medium text-stone-400">
          Line chart — Temperature (X) vs mean Jaccard similarity (Y), one line per model
        </h3>
        {hasLineData ? (
          <ResponsiveContainer width="100%" height={360}>
            <LineChart data={lineData} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#44403c" />
              <XAxis dataKey="temperature" type="number" stroke="#a8a29e" />
              <YAxis stroke="#a8a29e" domain={[0, 1]} />
              <Tooltip
                contentStyle={{ backgroundColor: '#1c1917', border: '1px solid #44403c', borderRadius: 8 }}
              />
              <Legend />
              {models.map((model, i) => (
                <Line
                  key={model}
                  type="monotone"
                  dataKey={model}
                  stroke={LINE_COLORS[i % LINE_COLORS.length]}
                  strokeWidth={2}
                  dot={{ r: 4 }}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="py-12 text-center text-stone-500">No temperature data yet. Run Phase 3 to see variance.</div>
        )}
      </div>

      <div className="rounded-lg border border-stone-700 bg-stone-900/50 p-4">
        <h3 className="mb-4 text-sm font-medium text-stone-400">
          Response comparison — runs at temp 0.0 vs 1.4 for selected model and prompt
        </h3>
        <div className="mb-4 flex flex-wrap gap-4">
          <label className="flex items-center gap-2 text-sm text-stone-400">
            Model
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="rounded border border-stone-600 bg-stone-800 px-2 py-1 text-stone-200"
            >
              <option value="">—</option>
              {models.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
          <div className="flex flex-1 flex-col gap-2 text-sm text-stone-400">
            <label className="flex items-center gap-2">
              Prompt
              <select
                value={selectedPrompt}
                onChange={(e) => setSelectedPrompt(e.target.value)}
                className="rounded border border-stone-600 bg-stone-800 px-2 py-1 text-stone-200"
              >
                <option value="">—</option>
                {prompts.map((p) => {
                  const meta = promptMap[p]
                  const label = meta?.category ? `${p} (${meta.category})` : p
                  return (
                    <option key={p} value={p}>
                      {label}
                    </option>
                  )
                })}
              </select>
            </label>
            {selectedPromptMeta && (
              <p className="max-w-2xl text-xs text-stone-400">
                <span className="font-medium text-stone-300">Prompt text:</span>{' '}
                <span className="whitespace-pre-wrap break-words">{selectedPromptMeta.text}</span>
              </p>
            )}
          </div>
        </div>
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          <div>
            <h4 className="mb-2 text-xs font-medium uppercase text-stone-500">Temperature 0.0</h4>
            <div className="space-y-3">
              {comparisonRuns.low.length ? (
                comparisonRuns.low.map((row, i) => (
                  <div
                    key={i}
                    className="rounded border border-stone-600 bg-stone-800/50 p-3 text-sm text-stone-300"
                  >
                    <span className="text-stone-500">Run {row.run_index}</span>
                    <p className="mt-1 whitespace-pre-wrap break-words">{row.response_text || '—'}</p>
                  </div>
                ))
              ) : (
                <p className="text-stone-500">No runs at 0.0 for this selection.</p>
              )}
            </div>
          </div>
          <div>
            <h4 className="mb-2 text-xs font-medium uppercase text-stone-500">Temperature 1.4</h4>
            <div className="space-y-3">
              {comparisonRuns.high.length ? (
                comparisonRuns.high.map((row, i) => (
                  <div
                    key={i}
                    className="rounded border border-stone-600 bg-stone-800/50 p-3 text-sm text-stone-300"
                  >
                    <span className="text-stone-500">Run {row.run_index}</span>
                    <p className="mt-1 whitespace-pre-wrap break-words">{row.response_text || '—'}</p>
                  </div>
                ))
              ) : (
                <p className="text-stone-500">No runs at 1.4 for this selection.</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
