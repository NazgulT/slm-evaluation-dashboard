import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ScatterChart,
  Scatter,
  ZAxis,
  Cell,
} from 'recharts'

const COLORS = ['#f59e0b', '#10b981', '#3b82f6', '#ef4444']

function aggregateByModel(results) {
  const byModel = {}
  for (const r of results) {
    const m = r.model || 'unknown'
    if (!byModel[m]) byModel[m] = { model: m, ttft_ms: 0, tps: 0, latency_ms: 0, norm_tps: 0, count: 0 }
    byModel[m].ttft_ms += Number(r.ttft_ms) || 0
    byModel[m].tps += Number(r.tokens_per_second) || 0
    byModel[m].latency_ms += Number(r.total_latency_ms) || 0
    byModel[m].norm_tps += Number(r.normalised_tps) || 0
    byModel[m].count += 1
  }
  return Object.values(byModel).map((x) => ({
    model: x.model,
    ttft_ms: Math.round((x.ttft_ms / x.count) * 10) / 10,
    tokens_per_second: Math.round((x.tps / x.count) * 10) / 10,
    total_latency_ms: Math.round((x.latency_ms / x.count) * 10) / 10,
    normalised_tps: x.count ? Math.round((x.norm_tps / x.count) * 1000) / 1000 : null,
  }))
}

function scatterData(results) {
  const byModel = {}
  for (const r of results) {
    const m = r.model || 'unknown'
    if (!byModel[m]) byModel[m] = { latency: 0, tps: 0, n: 0 }
    byModel[m].latency += Number(r.total_latency_ms) || 0
    byModel[m].tps += Number(r.tokens_per_second) || 0
    byModel[m].n += 1
  }
  return Object.entries(byModel).map(([model], i) => ({
    name: model,
    x: Math.round((byModel[model].latency / byModel[model].n) * 10) / 10,
    y: Math.round((byModel[model].tps / byModel[model].n) * 10) / 10,
    fill: COLORS[i % COLORS.length],
  }))
}

function buildComparisonData(results, comparisonResults, comparisonLabel) {
  const local = aggregateByModel(results)
  const uploaded = aggregateByModel(comparisonResults)
  const models = [...new Set([...local.map((r) => r.model), ...uploaded.map((r) => r.model)])].sort()
  const localMap = Object.fromEntries(local.map((r) => [r.model, r]))
  const uploadedMap = Object.fromEntries(uploaded.map((r) => [r.model, r]))
  const label = comparisonLabel || 'Uploaded'
  return models.map((m) => ({
    model: m,
    'This machine': localMap[m]?.tokens_per_second ?? null,
    [label]: uploadedMap[m]?.tokens_per_second ?? null,
  }))
}

export default function PerformanceChart({ results, comparisonResults = [], comparisonLabel = '' }) {
  const barData = aggregateByModel(results)
  const scatter = scatterData(results)
  const comparisonData = comparisonResults.length > 0 ? buildComparisonData(results, comparisonResults, comparisonLabel) : []

  if (!results.length) {
    return (
      <div className="rounded-lg border border-stone-700 bg-stone-900/50 p-8 text-center text-stone-500">
        No results yet. Run Phase 1 to see performance charts.
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <div className="rounded-lg border border-stone-700 bg-stone-900/50 p-4">
        <h3 className="mb-4 text-sm font-medium text-stone-400">Grouped bar — TTFT, TPS, Latency by model</h3>
        <ResponsiveContainer width="100%" height={320}>
          <BarChart data={barData} margin={{ top: 20, right: 30, left: 20, bottom: 60 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#44403c" />
            <XAxis dataKey="model" stroke="#a8a29e" angle={-20} textAnchor="end" height={60} />
            <YAxis stroke="#a8a29e" />
            <Tooltip
              contentStyle={{ backgroundColor: '#1c1917', border: '1px solid #44403c', borderRadius: 8 }}
              labelStyle={{ color: '#fafaf9' }}
            />
            <Legend />
            <Bar dataKey="ttft_ms" name="TTFT (ms)" fill="#f59e0b" radius={[4, 4, 0, 0]} />
            <Bar dataKey="tokens_per_second" name="TPS" fill="#10b981" radius={[4, 4, 0, 0]} />
            <Bar dataKey="total_latency_ms" name="Latency (ms)" fill="#3b82f6" radius={[4, 4, 0, 0]} />
            <Bar dataKey="normalised_tps" name="Normalised TPS" fill="#a855f7" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {comparisonData.length > 0 && (
        <div className="rounded-lg border border-stone-700 bg-stone-900/50 p-4">
          <h3 className="mb-4 text-sm font-medium text-stone-400">
            Comparison — TPS on this machine vs uploaded results (same model, different hardware)
          </h3>
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={comparisonData} margin={{ top: 20, right: 30, left: 20, bottom: 60 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#44403c" />
              <XAxis dataKey="model" stroke="#a8a29e" angle={-20} textAnchor="end" height={60} />
              <YAxis stroke="#a8a29e" label={{ value: 'TPS', angle: -90, position: 'insideLeft', fill: '#a8a29e' }} />
              <Tooltip
                contentStyle={{ backgroundColor: '#1c1917', border: '1px solid #44403c', borderRadius: 8 }}
              />
              <Legend />
              <Bar dataKey="This machine" fill="#10b981" radius={[4, 4, 0, 0]} />
              <Bar dataKey={comparisonLabel || 'Uploaded'} fill="#f59e0b" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="rounded-lg border border-stone-700 bg-stone-900/50 p-4">
        <h3 className="mb-4 text-sm font-medium text-stone-400">Scatter — Latency (X) vs TPS (Y), one dot per model</h3>
        <ResponsiveContainer width="100%" height={320}>
          <ScatterChart margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#44403c" />
            <XAxis type="number" dataKey="x" name="Latency (ms)" stroke="#a8a29e" />
            <YAxis type="number" dataKey="y" name="TPS" stroke="#a8a29e" />
            <ZAxis range={[100, 400]} />
            <Tooltip
              contentStyle={{ backgroundColor: '#1c1917', border: '1px solid #44403c', borderRadius: 8 }}
              formatter={(_, __, p) => [p.payload.name, `Latency: ${p.payload.x} ms, TPS: ${p.payload.y}`]}
            />
            <Scatter data={scatter} name="models">
              {scatter.map((_, i) => (
                <Cell key={i} fill={scatter[i].fill} />
              ))}
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
