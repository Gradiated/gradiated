import type { CSSProperties } from 'react'

import { measurements, type Measurements } from './measurementData'
import { laterComparisons } from './laterComparisons'
import './measurement-chart.css'

const history = [...measurements, ...Object.values(laterComparisons).map(point => ({ ...point, label: point.title }))]
export const experimentNumbers = ['Baseline', '1', '2', '3', '4', '5', '6a', '6b', '7', '8', '9', '10', '11', '12', '13', ...Object.values(laterComparisons).map((_, i) => String(14 + i))]

const metrics = [
  { key: 'ttftMs', label: 'Time to first token', unit: 'ms', ticks: [0, 100, 200], precision: 2 },
  { key: 'decodeTps', label: 'Decode speed', unit: 'tokens/s', ticks: [0, 700, 1400], precision: 1 },
  { key: 'joulesPerToken', label: 'Module energy', unit: 'J/token', ticks: [0, 0.0125, 0.025], precision: 5 },
] as const satisfies ReadonlyArray<{
  key: keyof Measurements
  label: string
  unit: string
  ticks: readonly [number, number, number]
  precision: number
}>

type Metric = (typeof metrics)[number]

function verticalPosition(metric: Metric, value: number) {
  const [min, , max] = metric.ticks
  const fraction = (value - min) / (max - min)
  return `${(1 - fraction) * 100}%`
}

export function experimentPosition(index: number) {
  return `${5 + (index / (history.length - 1)) * 90}%`
}

function format(metric: Metric, reading: Measurements) {
  return reading[metric.key].toFixed(metric.precision)
}

function experimentLabel(index: number) {
  return index === 0 ? experimentNumbers[0] : `Experiment ${experimentNumbers[index]}`
}

export function MeasurementChart({
  step,
  overview = false,
}: {
  step: number
  overview?: boolean
}) {
  const current = history[step]
  if (!current) return null

  const candidates = history.slice(0, step + 1)
  const control = current.control

  return (
    <figure className="fpga-measurements" aria-label="Measured on one KV260">
      {!overview && (
        <figcaption className="fpga-measurements-caption">
          {experimentLabel(step)}{current.value ? "" : " · Board measurements pending"}
        </figcaption>
      )}
      <div className="fpga-measurements-readings">
        {metrics.map(metric => (
          <div key={metric.key} data-metric={metric.key}>
            <span className="fpga-measurements-symbol" aria-hidden="true" /> {metric.label}
            <div><strong>{current.value ? format(metric, current.value) : '—'}</strong> {metric.unit}</div>
            {control && <span className="fpga-measurements-sr">Starting circuit for this comparison: {format(metric, control)} {metric.unit}</span>}
          </div>
        ))}
      </div>
      <div className="fpga-measurements-grid" aria-hidden="true">
        {metrics.map(metric => (
          <div className="fpga-measurements-scale" data-metric={metric.key} key={metric.key}>
            <b>{metric.unit}</b>
            {metric.ticks.map(tick => (
              <span key={tick} style={{ top: verticalPosition(metric, tick) }}>
                {tick.toLocaleString('en-GB', { maximumFractionDigits: 4 })}
              </span>
            ))}
          </div>
        ))}
        <div className="fpga-measurements-plot">
          {!overview && (
            <div className="fpga-measurements-cursor" style={{ left: experimentPosition(step) }} />
          )}
          {metrics.map(metric => candidates.map(({ runId, value }, index) => value && (
            <span
              key={`${metric.key}-${runId}-${index}`}
              className={'fpga-measurements-point' + (index === step ? ' is-current' : '')}
              data-metric={metric.key}
              style={{
                '--x': experimentPosition(index),
                '--y': verticalPosition(metric, value[metric.key]),
              } as CSSProperties}
            />
          )))}
        </div>
        <div className="fpga-measurements-axis" aria-hidden="true">
          {experimentNumbers.map((number, index) => (
            <span
              key={number}
              className="fpga-measurements-tick"
              data-current={step === index}
              data-endpoint={index === 0 || index === experimentNumbers.length - 1}
              data-phone-tick={
                (index % 4 === 0 && Math.abs(index - step) > 2) ||
                (index === experimentNumbers.length - 2 && step === experimentNumbers.length - 1)
              }
              style={{ left: experimentPosition(index) }}
            >
              {index === 0 ? 'B' : number}
            </span>
          ))}
        </div>
      </div>
      <div className="fpga-measurements-sr">
        <table>
          <caption>KV260 measurements in experiment order. Time to first token is the average wait across the timed mixed-prompt replies. Decode speed counts the remaining tokens across all replies and divides by the time taken to produce them. Energy per output token includes all the energy used at the K26 module’s supply during the mixed-prompt blocks, including pauses and checks.</caption>
          <thead>
            <tr>
              <th scope="col">Run</th>
              {metrics.map(metric => <th scope="col" key={metric.key}>{metric.label} ({metric.unit})</th>)}
            </tr>
          </thead>
          <tbody>
            {candidates.map(({ label, value }, index) => (
              <tr key={label}>
                <th scope="row">{experimentLabel(index)}, {label}</th>
                {metrics.map(metric => <td key={metric.key}>{value ? format(metric, value) : 'Pending'}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  )
}
