import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import MetricsTable from './MetricsTable'

const COLORS = { pass: '#10b981', retry: '#f59e0b', fail: '#ef4444' }

function buildPieData(summary) {
  return Object.entries(summary || {}).map(([model, counts]) => ({
    model,
    pass: counts.pass ?? 0,
    retry: counts.retry ?? 0,
    fail: counts.fail ?? 0,
  }))
}

function pieSeriesForModel(modelData) {
  return [
    { name: 'Pass', value: modelData.pass, color: COLORS.pass },
    { name: 'Retry', value: modelData.retry, color: COLORS.retry },
    { name: 'Fail', value: modelData.fail, color: COLORS.fail },
  ].filter((d) => d.value > 0)
}

export default function ValidationPanel({ results, summary }) {
  const pieData = buildPieData(summary)
  const hasSummary = pieData.some((d) => d.pass + d.retry + d.fail > 0)

  return (
    <div className="space-y-8">
      {hasSummary ? (
        <div className="rounded-lg border border-stone-700 bg-stone-900/50 p-4">
          <h3 className="mb-4 text-sm font-medium text-stone-400">Pass / Retry / Fail per model</h3>
          <div className="flex flex-wrap justify-start gap-8">
            {pieData.map((modelData) => {
              const series = pieSeriesForModel(modelData)
              if (!series.length) return null
              return (
                <div key={modelData.model} className="flex flex-col items-center">
                  <ResponsiveContainer width={180} height={180}>
                    <PieChart>
                      <Pie
                        data={series}
                        dataKey="value"
                        nameKey="name"
                        cx="50%"
                        cy="50%"
                        innerRadius={40}
                        outerRadius={70}
                        paddingAngle={2}
                        label={({ name, value }) => `${name}: ${value}`}
                      >
                        {series.map((_, i) => (
                          <Cell key={i} fill={series[i].color} />
                        ))}
                      </Pie>
                      <Tooltip
                        contentStyle={{ backgroundColor: '#1c1917', border: '1px solid #44403c', borderRadius: 8 }}
                      />
                      <Legend />
                    </PieChart>
                  </ResponsiveContainer>
                  <span className="mt-2 text-sm font-medium text-stone-400">{modelData.model}</span>
                </div>
              )
            })}
          </div>
        </div>
      ) : (
        <div className="rounded-lg border border-stone-700 bg-stone-900/50 p-6 text-center text-stone-500">
          No validation summary yet. Run Phase 2 to see pass/retry/fail distribution.
        </div>
      )}

      <div>
        <h3 className="mb-2 text-sm font-medium text-stone-400">Results table (with Valid JSON & Retry Used)</h3>
        <MetricsTable results={results} showValidation={true} />
      </div>
    </div>
  )
}
