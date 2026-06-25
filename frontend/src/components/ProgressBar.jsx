import { useEffect, useRef, useState } from 'react'
import axios from 'axios'

const POLL_INTERVAL = 1500

/**
 * hidden=true  → renders nothing but keeps polling (so onPartialReady / onComplete still fire
 *                 while the parent shows partial results)
 * onPartialReady → called once when stages_complete >= 3 (GroupBy done, data available)
 * onComplete     → called when status === 'complete' with (analysis, colMeta)
 */
export default function ProgressBar({ jobId, onComplete, onPartialReady, hidden }) {
  const [progress, setProgress] = useState(0)
  const [message, setMessage] = useState('Starting…')
  const [error, setError] = useState(null)
  const timerRef = useRef(null)
  const partialFiredRef = useRef(false)

  useEffect(() => {
    let cancelled = false

    async function poll() {
      try {
        const { data } = await axios.get(`/status/${jobId}`)
        if (cancelled) return

        setProgress(data.progress)
        setMessage(data.message)

        if (data.status === 'error') {
          setError(data.message || 'Processing failed.')
          return
        }

        // Fire partial-ready once as soon as stage 3 (GroupBy) finishes
        if (
          !partialFiredRef.current &&
          data.stages_complete >= 3 &&
          data.status === 'processing'
        ) {
          partialFiredRef.current = true
          onPartialReady?.()
        }

        if (data.status === 'complete') {
          const [analysisRes, colRes] = await Promise.all([
            axios.get(`/analysis/${jobId}`),
            axios.get(`/columns/${jobId}`),
          ])
          if (!cancelled) onComplete(analysisRes.data, colRes.data)
          return
        }

        timerRef.current = setTimeout(poll, POLL_INTERVAL)
      } catch (e) {
        if (!cancelled) setError('Lost connection to server. Please refresh.')
      }
    }

    poll()
    return () => {
      cancelled = true
      clearTimeout(timerRef.current)
    }
  }, [jobId])

  // When hidden: don't render any UI but keep effects running so polling continues
  if (hidden) return null

  const pct = Math.round(progress * 100)

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] animate-fade-in">
      <div className="w-full max-w-xl bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-8 h-8 border-3 border-blue-600 border-t-transparent rounded-full animate-spin" style={{ borderWidth: 3 }} />
          <span className="text-gray-700 font-medium text-lg">Analysing your dataset…</span>
        </div>

        {/* Progress bar */}
        <div className="w-full bg-gray-100 rounded-full h-5 overflow-hidden mb-3">
          <div
            className="h-full bg-blue-600 stripe-bg rounded-full transition-all duration-700 ease-out animate-progress-stripe"
            style={{ width: `${pct}%` }}
          />
        </div>

        <div className="flex justify-between text-sm text-gray-500">
          <span>{message}</span>
          <span className="font-semibold text-blue-600">{pct}%</span>
        </div>

        {/* Stage steps */}
        <div className="mt-6 grid grid-cols-5 gap-1">
          {[
            { label: 'Dedup',     threshold: 0.20 },
            { label: 'Profile',   threshold: 0.45 },
            { label: 'Compress',  threshold: 0.70 },
            { label: 'Normalise', threshold: 0.85 },
            { label: 'Done',      threshold: 1.00 },
          ].map(({ label, threshold }) => (
            <div key={label} className="flex flex-col items-center gap-1">
              <div className={`w-3 h-3 rounded-full border-2 transition-colors
                ${progress >= threshold
                  ? 'bg-blue-600 border-blue-600'
                  : progress >= threshold - 0.25
                    ? 'bg-blue-200 border-blue-400 animate-pulse'
                    : 'bg-gray-200 border-gray-300'}`}
              />
              <span className="text-xs text-gray-400">{label}</span>
            </div>
          ))}
        </div>

        {error && (
          <div className="mt-4 bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm">
            {error}
          </div>
        )}
      </div>
    </div>
  )
}
