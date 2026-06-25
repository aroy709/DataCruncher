const ROLE_COLORS = {
  grouping_key:      'bg-blue-100 text-blue-800',
  numeric_aggregate: 'bg-green-100 text-green-800',
  string_collapse:   'bg-amber-100 text-amber-800',
}

const ROLE_LABELS = {
  grouping_key:      'Grouping Key',
  numeric_aggregate: 'Aggregated',
  string_collapse:   'Collapsed',
}

export default function AnalysisReport({ analysis, onAccept, onCustomise }) {
  const {
    grouping_keys = [],
    exact_duplicates_removed = 0,
    aggregations = [],
    string_normalizations = [],
    col_profiles = [],
    stages = [],
    original_count = 0,
    compressed_count = 0,
    compression_ratio = 0,
    deep_compress_applied = false,
  } = analysis

  return (
    <div className="max-w-4xl mx-auto animate-fade-in space-y-6">
      {/* Hero summary */}
      <div className="bg-gradient-to-r from-blue-600 to-blue-700 text-white rounded-2xl p-6 shadow">
        <h2 className="text-2xl font-bold mb-1">Analysis Complete</h2>
        <p className="text-blue-100 mb-4">Here's what the algorithm found and how it compressed your data.</p>
        <div className="grid grid-cols-3 gap-4">
          <Stat label="Original rows" value={original_count.toLocaleString()} />
          <Stat label="Compressed to" value={compressed_count.toLocaleString()} />
          <Stat label="Reduction" value={`${compression_ratio}%`} highlight />
        </div>
      </div>

      {/* Stage pipeline */}
      <Section title="Processing Stages">
        <div className="flex items-start gap-0">
          {stages.map((s, i) => (
            <div key={i} className="flex-1 flex flex-col items-center text-center px-2">
              <div className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold mb-2
                ${i === 0 ? 'bg-gray-200 text-gray-600' : 'bg-blue-600 text-white'}`}>
                {i + 1}
              </div>
              <span className="text-xs font-semibold text-gray-700">{s.stage}</span>
              <span className="text-xs text-gray-400 mt-0.5">{s.rows_after.toLocaleString()} rows</span>
              {i < stages.length - 1 && (
                <div className="absolute translate-x-16 translate-y-4 text-gray-300 text-lg">→</div>
              )}
            </div>
          ))}
        </div>
      </Section>

      {/* Exact duplicates */}
      <Section title="Stage 1 — Exact Deduplication">
        <InfoRow
          icon="🔁"
          label="Exact duplicate rows removed"
          value={exact_duplicates_removed.toLocaleString()}
          note="Rows that were completely identical across all columns."
        />
      </Section>

      {/* Grouping keys */}
      <Section title="Stage 2 — Column Profiling & Grouping Keys">
        <p className="text-sm text-gray-500 mb-3">
          Columns with ≤5% unique values were chosen as <strong>grouping keys</strong> — all rows sharing
          the same combination of these values are merged into one record.
        </p>
        <div className="space-y-2">
          {col_profiles.map(c => (
            <div key={c.column} className="flex items-center gap-3 bg-gray-50 rounded-lg px-4 py-2.5 text-sm">
              <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${ROLE_COLORS[c.role] || 'bg-gray-100 text-gray-600'}`}>
                {ROLE_LABELS[c.role] || c.role}
              </span>
              <span className="font-mono font-medium text-gray-800 flex-1">{c.column}</span>
              <span className="text-gray-400 text-xs">{(c.cardinality_ratio * 100).toFixed(2)}% unique</span>
              <span className="text-gray-500 text-xs max-w-xs truncate">{c.reason}</span>
            </div>
          ))}
        </div>
      </Section>

      {/* Aggregations */}
      {aggregations.length > 0 && (
        <Section title="Stage 3 — Numeric Aggregation">
          <p className="text-sm text-gray-500 mb-3">
            Numeric columns were <strong>summed</strong> across rows within each group.
          </p>
          <div className="flex flex-wrap gap-2">
            {aggregations.map(a => (
              <span key={a.column} className="px-3 py-1.5 bg-green-50 border border-green-200 text-green-800 text-xs font-mono rounded-full">
                {a.column} → {a.method}
              </span>
            ))}
          </div>
        </Section>
      )}

      {/* String normalization */}
      {string_normalizations.length > 0 && (
        <Section title="Stage 4 — String Normalisation">
          <p className="text-sm text-gray-500 mb-3">
            String columns were collapsed to the <strong>most frequent value</strong> within each group.
            Original variants are kept in a <code>_variants</code> column.
          </p>
          <div className="space-y-2">
            {string_normalizations.map(s => (
              <div key={s.column} className="flex items-center gap-3 text-sm bg-amber-50 rounded-lg px-4 py-2">
                <span className="font-mono text-amber-800 font-medium">{s.column}</span>
                <span className="text-gray-400">→</span>
                <span className="text-gray-600">most frequent value</span>
                <span className="text-gray-400 text-xs ml-auto">variants → <code>{s.variants_column}</code></span>
              </div>
            ))}
          </div>
        </Section>
      )}

      {deep_compress_applied && (
        <Section title="Stage 5 — KMeans Clustering (Deep Compress)">
          <p className="text-sm text-gray-500">
            Dataset was still large after grouping, so numeric columns were clustered using MiniBatch KMeans.
            Each cluster was then collapsed, providing additional compression.
          </p>
        </Section>
      )}

      {/* Action buttons */}
      <div className="flex gap-4 justify-end pt-2">
        <button
          onClick={onCustomise}
          className="px-5 py-2.5 border border-gray-300 text-gray-700 rounded-xl hover:bg-gray-50 font-medium text-sm transition-colors"
        >
          Customise grouping & filters
        </button>
        <button
          onClick={onAccept}
          className="px-6 py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 font-semibold text-sm shadow transition-colors"
        >
          Accept &amp; view results →
        </button>
      </div>
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div className="bg-white border border-gray-200 rounded-2xl p-6">
      <h3 className="text-base font-semibold text-gray-800 mb-4">{title}</h3>
      {children}
    </div>
  )
}

function Stat({ label, value, highlight }) {
  return (
    <div className={`rounded-xl p-3 ${highlight ? 'bg-white/20' : 'bg-white/10'}`}>
      <div className={`text-2xl font-bold ${highlight ? 'text-yellow-300' : 'text-white'}`}>{value}</div>
      <div className="text-blue-200 text-xs mt-0.5">{label}</div>
    </div>
  )
}

function InfoRow({ icon, label, value, note }) {
  return (
    <div className="flex items-start gap-3 bg-gray-50 rounded-xl p-4">
      <span className="text-2xl">{icon}</span>
      <div className="flex-1">
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium text-gray-700">{label}</span>
          <span className="text-sm font-bold text-blue-600">{value}</span>
        </div>
        {note && <p className="text-xs text-gray-400 mt-0.5">{note}</p>}
      </div>
    </div>
  )
}
