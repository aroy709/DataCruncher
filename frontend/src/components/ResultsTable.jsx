function cellBg(col, value) {
  if (col === '_record_count') {
    const n = Number(value)
    if (n >= 100) return 'bg-red-100 text-red-800 font-bold'
    if (n >= 20)  return 'bg-amber-100 text-amber-800 font-semibold'
    if (n > 1)    return 'bg-blue-50 text-blue-700'
  }
  return ''
}

export default function ResultsTable({ columns, data }) {
  if (!columns || !data) return null

  return (
    <div className="bg-white border border-gray-200 rounded-2xl overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              {columns.map(col => (
                <th
                  key={col}
                  className={`px-4 py-3 text-left font-semibold whitespace-nowrap text-xs uppercase tracking-wide
                    ${col === '_record_count' ? 'text-blue-700' : 'text-gray-500'}`}
                >
                  {col === '_record_count' ? '# Merged' : col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {data.map((row, ri) => (
              <tr key={ri} className="hover:bg-gray-50 transition-colors">
                {columns.map(col => {
                  const val = row[col]
                  const display = val === null || val === undefined ? '—' : String(val)
                  const extra = cellBg(col, val)
                  return (
                    <td
                      key={col}
                      className={`px-4 py-2.5 whitespace-nowrap max-w-xs truncate ${extra || 'text-gray-700'}`}
                      title={display}
                    >
                      <span className={extra ? `px-2 py-0.5 rounded-full text-xs ${extra}` : ''}>
                        {display}
                      </span>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.length === 0 && (
        <div className="text-center py-12 text-gray-400 text-sm">No records to display.</div>
      )}
    </div>
  )
}
