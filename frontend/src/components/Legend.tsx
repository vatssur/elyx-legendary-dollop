import {
  ActivityType,
  ScheduleBlockType,
  ACTIVITY_COLORS,
  ACTIVITY_EMOJI,
  ACTIVITY_LABELS,
  BLOCK_TYPE_COLORS,
} from '../types'
import './Legend.css'

const LEGEND_ITEMS = [
  ...Object.values(ActivityType).map(type => ({
    key: type,
    emoji: ACTIVITY_EMOJI[type] ?? '📋',
    label: ACTIVITY_LABELS[type] ?? type,
    color: ACTIVITY_COLORS[type] ?? '#666',
  })),
  {
    key: 'PREP',
    emoji: ACTIVITY_EMOJI[ScheduleBlockType.PREP] ?? '🔧',
    label: 'Prep',
    color: BLOCK_TYPE_COLORS[ScheduleBlockType.PREP] ?? '#78909C',
  },
  {
    key: 'TRANSIT',
    emoji: ACTIVITY_EMOJI[ScheduleBlockType.TRANSIT] ?? '🚗',
    label: 'Transit',
    color: BLOCK_TYPE_COLORS[ScheduleBlockType.TRANSIT] ?? '#607D8B',
  },
  {
    key: 'TRAVEL',
    emoji: '✈️',
    label: 'Travel Day',
    color: BLOCK_TYPE_COLORS[ScheduleBlockType.TRAVEL_DAY] ?? '#00BCD4',
  },
]

export function Legend() {
  return (
    <div className="legend-bar" id="schedule-legend">
      {LEGEND_ITEMS.map(item => (
        <div key={item.key} className="legend-item">
          <span
            className="legend-dot"
            style={{ backgroundColor: item.color }}
          />
          <span className="legend-emoji">{item.emoji}</span>
          <span className="legend-label">{item.label}</span>
        </div>
      ))}
    </div>
  )
}
