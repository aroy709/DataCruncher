import { useState } from 'react'
import axios from 'axios'

const AGG_OPTIONS = ['sum', 'mean', 'min', 'max', 'most_frequent', 'concatenate']
const FILTER_OPS = [
  { value: 'eq', label: '= equals' },
  { value: 'neq', label: '≠ not equals' },
  { value: 'contains', label: '⊃ contains' },
  { value: 'gt', label: '> greater than' },
  { value: 'lt', label: '< less than' },
]

export default function CustomisePanel({ jobId, colMeta, onDone }) {
  const columns = colMeta?.columns || []
  const initialKeys = colMeta?.current_grouping_keys || []

  const [groupingKeys, setGroupingKeys] = useState(new Set(initialKeys))
  const [aggregations, setAggregations] = useState({})
  const [filters, setFilters] = useState([])
  const [running, setRunning] = useState(false)
  const [error, setError] = useState(null)
  const [progress, setProgress] = useState(null)

  function toggleKey(col) {
    setGroupingKeys(prev => {
      const next = new Set(prev)
      next.has(col) ? next.delete(col) : next.add(col)
      return next
    })
  }

  function setAgg(col, method) {
    setAggregations(prev => ({ ...prev, [col]: method }))
  }

  function addFilter() {
    setFilters(prev => [...prev, { column: columns[0]?.name || '', op: 'eq', value: '' }])
  }

  function updateFilter(i, key, val) {
    setFilters(prev => prev.map((f, idx) => idx === i ? { ...f, [key]: val } : f))
  }

  function removeFilter(i) {
    setFilters(prev => prev.filter((_, idx) => idx !== i))
  }

  async function handleRerun() {
    setRunning(true)
    setError(null)
    setProgress('Queuing re-analysis…')
    try {
      await axios.post(`/reanalyze/${jobId}`, {
        grouping_keys: [...groupingKeys],
        aggregations,
        filters: filters.filter(f => f.column && f.value),
      })

      // Poll until done
      let done = false
      while (!done) {
        await new Promise(r => setTimeout(r, 1000))
        const { data } = await axios.get(`/status/${jobId}`)
        setProgress(`${data.message} (${Math.round(data.progress * 100)}%)`)
        if (data.status === 'complete') { done = true; onDone() }
        else if (data.status === 'error') { setError(data.message); break }
      }
    } catch (e) {
      setError(e.response?.data?.detail || 'Re-analysis failed.')
    } finally {
      setRunning(false)
      setProgress(null)
    }
  }

  const nonKeys = columns.filter(c => !groupingKeys.has(c.name))

  return (
    <div className="max-w-4xl mx-auto animate-fade-in space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Customise Analysis</h2>
          <p className="text-gray-500 text-sm mt-1">Choose which columns to group by, how to aggregate the rest, and apply row filters.</p>
        </div>
      </div>

      {/* Grouping keys */}
      <Card title="Grouping Keys" subtitle="Rows that share the same combination of these values will be merged into one.">
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {columns.map(c => (
            <label key={c.name} className={`flex items-center gap-2.5 px-3 py-2.5 rounded-xl border cursor-pointer transition-colors
              ${groupingKeys.has(c.name)
                ? 'border-blue-500 bg-blue-50 text-blue-800'
                : 'border-gray-200 bg-white text-gray-700 hover:border-gray-300'}`}>
              <input
                type="checkbox"
                checked={groupingKeys.has(c.name)}
                onChange={() => toggleKey(c.name)}
                className="accent-blue-600"
              />
              <span className="text-sm font-mono truncate">{c.name}</span>
              <span className="ml-auto text-xs text-gray-400">{c.unique_count.toLocaleString()} uniq</span>
            </label>
          ))}
        </div>
      </Card>

      {/* Aggregation per non-key column */}
      {nonKeys.length > 0 && (
        <Card title="Column Aggregation" subtitle="For non-grouping columns, choose how values are combined within each group.">
          <div className="space-y-2">
            {nonKeys.map(c => {
              const defaultAgg = c.is_numeric ? 'sum' : 'most_frequent'
              const selected = aggregations[c.name] || defaultAgg
              return (
                <div key={c.name} className="flex items-center gap-3 bg-gray-50 rounded-lg px-3 py-2">
                  <span className="text-sm font-mono text-gray-700 w-40 truncate">{c.name}</span>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${c.is_numeric ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'}`}>
                    {c.is_numeric ? 'numeric' : 'text'}
                  </span>
                  <select
                    value={selected}
                    onChange={e => setAgg(c.name, e.target.value)}
                    className="ml-auto text-sm border border-gray-300 rounded-lg px-2 py-1 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    {AGG_OPTIONS.map(o => (
                      <option key={o} value={o}>{o}</option>
                    ))}
                  </select>
                </div>
              )
            })}
          </div>
        </Card>
      )}

      {/* Filters */}
      <Card title="Row Filters" subtitle="Filter out rows before compression is applied.">
        {filters.length === 0 && (
          <p className="text-sm text-gray-400 mb-3">No filters added. All rows will be included.</p>
        )}
        <div className="space-y-2 mb-3">
          {filters.map((f, i) => (
            <div key={i} className="flex items-center gap-2 bg-gray-50 rounded-xl p-2">
              <select
                value={f.column}
                onChange={e => updateFilter(i, 'column', e.target.value)}
                className="text-sm border border-gray-300 rounded-lg px-2 py-1.5 bg-white focus:outline-none"
              >
                {columns.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
              </select>
              <select
                value={f.op}
                onChange={e => updateFilter(i, 'op', e.target.value)}
                className="text-sm border border-gray-300 rounded-lg px-2 py-1.5 bg-white focus:outline-none"
              >
                {FILTER_OPS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
              <input
                value={f.value}
                onChange={e => updateFilter(i, 'value', e.target.value)}
                placeholder="value"
                className="text-sm border border-gray-300 rounded-lg px-2 py-1.5 flex-1 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                onClick={() => removeFilter(i)}
                className="text-red-400 hover:text-red-600 text-lg leading-none px-1"
              >×</button>
            </div>
          ))}
        </div>
        <button
          onClick={addFilter}
          className="text-sm text-blue-600 hover:text-blue-800 font-medium flex items-center gap-1"
        >
          <span className="text-lg leading-none">+</span> Add filter
        </button>
      </Card>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm">{error}</div>
      )}

      {progress && (
        <div className="bg-blue-50 border border-blue-200 text-blue-700 rounded-xl px-4 py-3 text-sm">{progress}</div>
      )}

      <div className="flex justify-end gap-3 pt-2">
        <button
          onClick={handleRerun}
          disabled={running || groupingKeys.size === 0}
          className="px-6 py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 font-semibold text-sm shadow disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
        >
          {running && <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />}
          Re-run Analysis
        </button>
      </div>
    </div>
  )
}

function Card({ title, subtitle, children }) {
  return (
    <div className="bg-white border border-gray-200 rounded-2xl p-6">
      <h3 className="text-base font-semibold text-gray-800 mb-0.5">{title}</h3>
      {subtitle && <p className="text-xs text-gray-400 mb-4">{subtitle}</p>}
      {children}
    </div>
  )
}
