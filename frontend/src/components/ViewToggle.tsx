import './ViewToggle.css'

type ViewType = 'week' | 'month'

interface ViewToggleProps {
  current: ViewType
  onChange: (view: ViewType) => void
}

const VIEWS: { key: ViewType; label: string }[] = [
  { key: 'week', label: 'Week' },
  { key: 'month', label: 'Month' },
]

export function ViewToggle({ current, onChange }: ViewToggleProps) {
  return (
    <div className="view-toggle" id="view-toggle">
      {VIEWS.map(v => (
        <button
          key={v.key}
          className={`view-btn ${current === v.key ? 'active' : ''}`}
          onClick={() => onChange(v.key)}
        >
          {v.label}
        </button>
      ))}
    </div>
  )
}
