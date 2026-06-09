import { useMemo, useState } from 'react'
import type { UnscheduledActivity } from '../types'
import { ActivityType, ACTIVITY_EMOJI, ACTIVITY_COLORS } from '../types'
import './UnscheduledPanel.css'

interface UnscheduledPanelProps {
  items: UnscheduledActivity[]
  onClose: () => void
}

interface GroupedItem {
  date: string
  items: UnscheduledActivity[]
}

export function UnscheduledPanel({ items, onClose }: UnscheduledPanelProps) {
  const [filterType, setFilterType] = useState<ActivityType | 'ALL'>('ALL')
  const [expandedDates, setExpandedDates] = useState<Set<string>>(new Set())

  const filtered = useMemo(() => {
    if (filterType === 'ALL') return items
    return items.filter(i => i.activity_type === filterType)
  }, [items, filterType])

  const grouped = useMemo(() => {
    const map = new Map<string, UnscheduledActivity[]>()
    for (const item of filtered) {
      const existing = map.get(item.target_date)
      if (existing) {
        existing.push(item)
      } else {
        map.set(item.target_date, [item])
      }
    }
    const result: GroupedItem[] = []
    for (const [date, dateItems] of map.entries()) {
      result.push({ date, items: dateItems })
    }
    return result.sort((a, b) => a.date.localeCompare(b.date))
  }, [filtered])

  const toggleDate = (date: string) => {
    setExpandedDates(prev => {
      const next = new Set(prev)
      if (next.has(date)) {
        next.delete(date)
      } else {
        next.add(date)
      }
      return next
    })
  }

  const typeCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const item of items) {
      counts[item.activity_type] = (counts[item.activity_type] ?? 0) + 1
    }
    return counts
  }, [items])

  return (
    <aside className="unscheduled-panel" id="unscheduled-panel">
      <div className="panel-header">
        <h3 className="panel-title">
          Skipped Activities
          <span className="panel-count">{filtered.length}</span>
        </h3>
        <button className="panel-close" onClick={onClose} aria-label="Close panel">
          ×
        </button>
      </div>

      {/* Filter chips */}
      <div className="panel-filters">
        <button
          className={`filter-chip ${filterType === 'ALL' ? 'active' : ''}`}
          onClick={() => setFilterType('ALL')}
        >
          All ({items.length})
        </button>
        {Object.values(ActivityType).map(type => {
          const count = typeCounts[type]
          if (!count) return null
          return (
            <button
              key={type}
              className={`filter-chip ${filterType === type ? 'active' : ''}`}
              onClick={() => setFilterType(type)}
              style={{
                '--chip-color': ACTIVITY_COLORS[type],
              } as React.CSSProperties}
            >
              {ACTIVITY_EMOJI[type]} {count}
            </button>
          )
        })}
      </div>

      {/* Grouped list */}
      <div className="panel-list">
        {grouped.map(group => {
          const isExpanded = expandedDates.has(group.date)
          const displayDate = new Date(group.date + 'T12:00:00')
          const dateLabel = displayDate.toLocaleDateString('en-US', {
            weekday: 'short',
            month: 'short',
            day: 'numeric',
          })

          return (
            <div key={group.date} className="date-group">
              <button
                className="date-group-header"
                onClick={() => toggleDate(group.date)}
              >
                <span className="date-label">{dateLabel}</span>
                <span className="date-count">{group.items.length}</span>
                <span className={`expand-arrow ${isExpanded ? 'expanded' : ''}`}>
                  ›
                </span>
              </button>

              {isExpanded && (
                <div className="date-group-items">
                  {group.items.map((item, idx) => {
                    const emoji = ACTIVITY_EMOJI[item.activity_type] ?? '📋'
                    const color = ACTIVITY_COLORS[item.activity_type] ?? '#666'
                    return (
                      <div
                        key={`${item.activity_id}-${idx}`}
                        className="skipped-item"
                        style={{ '--item-color': color } as React.CSSProperties}
                      >
                        <span className="skipped-emoji">{emoji}</span>
                        <div className="skipped-info">
                          <span className="skipped-name">{item.activity_name}</span>
                          <span className="skipped-reason">{item.reason}</span>
                          {item.adjustment && (
                            <span className="skipped-adjustment">
                              💡 {item.adjustment}
                            </span>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </aside>
  )
}
