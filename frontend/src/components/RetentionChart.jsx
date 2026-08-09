import { useMemo, useState } from 'react'

/**
 * Retention over time: a line for daily recall accuracy, with review volume as
 * a separate panel beneath it sharing the x-axis.
 *
 * Two panels rather than one chart with two y-scales — a dual-axis plot lets
 * the reader infer a relationship from whatever crossing point the scales
 * happen to produce.
 *
 * Colors are validated against the gray-900 card surface: the indigo sits in
 * the dark-mode lightness band and clears 3:1, and the volume columns are
 * deliberately achromatic so they read as context, not a second series.
 */
const LINE = '#6366f1'      // indigo-500
const VOLUME = '#64748b'    // slate-500, de-emphasis
const TARGET = '#10b981'    // emerald-500, reference annotation only
const SURFACE = '#111827'   // gray-900 — the card behind the chart

const TARGET_ACCURACY = 85

// Viewbox units; the SVG scales to its container via preserveAspectRatio.
const W = 720
const H_ACC = 150
const H_VOL = 46
const GAP = 26
const PAD = { top: 12, right: 14, bottom: 18, left: 34 }

function formatDay(iso) {
  const [, m, d] = iso.split('-')
  return `${Number(m)}/${Number(d)}`
}

export default function RetentionChart({ data }) {
  const [hover, setHover] = useState(null)

  const geometry = useMemo(() => {
    if (!data?.length) return null
    const plotW = W - PAD.left - PAD.right
    // A single point would divide by zero; park it in the middle instead.
    const step = data.length > 1 ? plotW / (data.length - 1) : 0
    const x = (i) => PAD.left + (data.length > 1 ? i * step : plotW / 2)
    const yAcc = (v) => PAD.top + (1 - v / 100) * H_ACC
    const maxVol = Math.max(...data.map(d => d.reviewed), 1)
    const volTop = PAD.top + H_ACC + GAP
    const barW = Math.max(2, Math.min(14, step * 0.6 || 14))

    return {
      yAcc, volTop, barW, maxVol,
      points: data.map((d, i) => ({ ...d, cx: x(i), cy: yAcc(d.accuracy) })),
      hVol: (v) => Math.max(1, (v / maxVol) * H_VOL),
    }
  }, [data])

  if (!geometry) {
    return (
      <div className="text-sm text-gray-500 py-8 text-center">
        No graded reviews yet — study a few cards and the trend shows up here.
      </div>
    )
  }

  const { yAcc, volTop, barW, maxVol, points, hVol } = geometry
  const totalH = PAD.top + H_ACC + GAP + H_VOL + PAD.bottom
  const line = points.map((p, i) => `${i ? 'L' : 'M'}${p.cx.toFixed(1)},${p.cy.toFixed(1)}`).join(' ')
  const last = points[points.length - 1]
  const active = hover != null ? points[hover] : null

  // Label roughly six x-ticks regardless of range, always including the ends.
  const tickEvery = Math.max(1, Math.ceil(points.length / 6))

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${W} ${totalH}`}
        className="w-full h-auto"
        role="img"
        aria-label="Daily recall accuracy and review volume over time"
        onMouseLeave={() => setHover(null)}
      >
        {/* Accuracy gridlines — hairline, solid, recessive */}
        {[0, 25, 50, 75, 100].map(v => (
          <g key={v}>
            <line
              x1={PAD.left} x2={W - PAD.right} y1={yAcc(v)} y2={yAcc(v)}
              stroke="#1f2937" strokeWidth="1"
            />
            <text
              x={PAD.left - 7} y={yAcc(v) + 3.5} textAnchor="end"
              className="fill-gray-600" style={{ fontSize: 10, fontVariantNumeric: 'tabular-nums' }}
            >
              {v}
            </text>
          </g>
        ))}

        {/* 85% target — an annotation, labelled so it isn't read as data */}
        <line
          x1={PAD.left} x2={W - PAD.right} y1={yAcc(TARGET_ACCURACY)} y2={yAcc(TARGET_ACCURACY)}
          stroke={TARGET} strokeWidth="1" opacity="0.55"
        />
        <text
          x={W - PAD.right} y={yAcc(TARGET_ACCURACY) - 5} textAnchor="end"
          className="fill-gray-500" style={{ fontSize: 9.5 }}
        >
          85% target
        </text>

        {/* Accuracy line + endpoint marker */}
        <path d={line} fill="none" stroke={LINE} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        <circle cx={last.cx} cy={last.cy} r="4" fill={LINE} stroke={SURFACE} strokeWidth="2" />

        {/* Endpoint value — the one direct label; the axis carries the rest.
            Anchored to end at the point so it can't overflow the right edge. */}
        <text
          x={last.cx} y={last.cy - 9} textAnchor="end"
          className="fill-gray-300" style={{ fontSize: 11, fontWeight: 600 }}
        >
          {Math.round(last.accuracy)}%
        </text>

        {/* Volume columns — separate panel, own scale, shared x */}
        {points.map((p, i) => {
          const h = hVol(p.reviewed)
          return (
            <rect
              key={p.date}
              x={p.cx - barW / 2} y={volTop + H_VOL - h}
              width={barW} height={h} rx="2"
              fill={VOLUME} opacity={hover == null || hover === i ? 0.85 : 0.4}
            />
          )
        })}
        {/* The volume panel is its own scale, so it carries its own ticks. */}
        <text
          x={PAD.left - 7} y={volTop + 7} textAnchor="end"
          className="fill-gray-600" style={{ fontSize: 9.5, fontVariantNumeric: 'tabular-nums' }}
        >
          {maxVol}
        </text>
        <text
          x={PAD.left - 7} y={volTop + H_VOL} textAnchor="end"
          className="fill-gray-600" style={{ fontSize: 9.5 }}
        >
          0
        </text>

        {/* X labels */}
        {points.map((p, i) => (
          (i % tickEvery === 0 || i === points.length - 1) && (
            <text
              key={p.date} x={p.cx} y={totalH - 5} textAnchor="middle"
              className="fill-gray-600" style={{ fontSize: 9.5, fontVariantNumeric: 'tabular-nums' }}
            >
              {formatDay(p.date)}
            </text>
          )
        ))}

        {/* Crosshair + oversized hit targets (the marks are too small to aim at) */}
        {active && (
          <line
            x1={active.cx} x2={active.cx} y1={PAD.top} y2={volTop + H_VOL}
            stroke="#374151" strokeWidth="1"
          />
        )}
        {active && (
          <circle cx={active.cx} cy={active.cy} r="4.5" fill={LINE} stroke={SURFACE} strokeWidth="2" />
        )}
        {points.map((p, i) => (
          <rect
            key={`hit-${p.date}`}
            x={p.cx - Math.max(barW, 12) / 2} y={PAD.top}
            width={Math.max(barW, 12)} height={H_ACC + GAP + H_VOL}
            fill="transparent"
            onMouseEnter={() => setHover(i)}
          />
        ))}
      </svg>

      {active && (
        <div className="mt-1 text-xs text-gray-400 flex flex-wrap gap-x-3 gap-y-0.5 justify-center">
          <span className="text-gray-300">{active.date}</span>
          <span>{Math.round(active.accuracy)}% recalled</span>
          <span>{active.reviewed} reviewed</span>
          {active.hard > 0 && <span>{active.hard} hard</span>}
        </div>
      )}
    </div>
  )
}
