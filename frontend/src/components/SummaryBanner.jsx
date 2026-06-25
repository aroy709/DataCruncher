export default function SummaryBanner({ originalCount, compressedCount, compressionRatio, onCustomise }) {
  const saved = originalCount - compressedCount

  return (
    <div className="bg-white border border-gray-200 rounded-2xl p-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
      <div className="flex items-center gap-5">
        <div className="bg-green-100 rounded-xl p-3">
          <svg className="w-6 h-6 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <div>
          <p className="text-gray-900 font-semibold text-lg">
            Reduced{' '}
            <span className="text-gray-500">{originalCount.toLocaleString()}</span>
            {' '}rows →{' '}
            <span className="text-blue-600 font-bold">{compressedCount.toLocaleString()}</span>
            {' '}rows
          </p>
          <p className="text-gray-400 text-sm">
            {saved.toLocaleString()} rows merged &nbsp;·&nbsp;
            <span className="text-green-600 font-semibold">{compressionRatio}% compression</span>
          </p>
        </div>
      </div>
      <button
        onClick={onCustomise}
        className="text-sm border border-gray-300 px-4 py-2 rounded-xl text-gray-600 hover:bg-gray-50 transition-colors whitespace-nowrap"
      >
        Adjust grouping
      </button>
    </div>
  )
}
