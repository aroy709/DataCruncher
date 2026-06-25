export default function Pagination({ page, total, limit, onChange }) {
  const totalPages = Math.ceil(total / limit)
  if (totalPages <= 1) return null

  const start = (page - 1) * limit + 1
  const end = Math.min(page * limit, total)

  function pages() {
    const p = []
    if (totalPages <= 7) {
      for (let i = 1; i <= totalPages; i++) p.push(i)
    } else {
      p.push(1)
      if (page > 3) p.push('...')
      for (let i = Math.max(2, page - 1); i <= Math.min(totalPages - 1, page + 1); i++) p.push(i)
      if (page < totalPages - 2) p.push('...')
      p.push(totalPages)
    }
    return p
  }

  return (
    <div className="flex items-center justify-between py-2">
      <p className="text-sm text-gray-500">
        Showing <span className="font-medium">{start.toLocaleString()}–{end.toLocaleString()}</span> of{' '}
        <span className="font-medium">{total.toLocaleString()}</span> rows
      </p>

      <div className="flex items-center gap-1">
        <PageBtn onClick={() => onChange(page - 1)} disabled={page === 1} label="←" />
        {pages().map((p, i) =>
          p === '...'
            ? <span key={`e${i}`} className="px-2 text-gray-400">…</span>
            : <PageBtn key={p} onClick={() => onChange(p)} active={p === page} label={String(p)} />
        )}
        <PageBtn onClick={() => onChange(page + 1)} disabled={page === totalPages} label="→" />
      </div>
    </div>
  )
}

function PageBtn({ onClick, disabled, active, label }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`w-9 h-9 rounded-lg text-sm font-medium transition-colors
        ${active ? 'bg-blue-600 text-white' :
          disabled ? 'text-gray-300 cursor-not-allowed' :
          'text-gray-700 hover:bg-gray-100'}`}
    >
      {label}
    </button>
  )
}
