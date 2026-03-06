const STATUS_CONFIG = {
  COMPLETO: { label: 'Completo',  cls: 'badge-success'  },
  PARCIAL:  { label: 'Parcial',   cls: 'badge-warning'  },
  AUSENTE:  { label: 'Ausente',   cls: 'badge-danger'   },
  CRITICO:  { label: 'Crítico',   cls: 'badge-critical' },
}

export default function ScoreBadge({ status }) {
  const cfg = STATUS_CONFIG[status] || { label: status, cls: 'badge-secondary' }
  return <span className={`badge ${cfg.cls}`}>{cfg.label}</span>
}

export function ScoreBar({ score }) {
  const pct = Math.round((score || 0) * 100)
  const color = pct >= 80 ? '#48bb78' : pct >= 50 ? '#ed8936' : '#e53e3e'
  return (
    <div className="score-bar-wrapper">
      <div className="score-bar-track">
        <div className="score-bar-fill" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
      <span className="score-bar-label">{pct}%</span>
    </div>
  )
}
