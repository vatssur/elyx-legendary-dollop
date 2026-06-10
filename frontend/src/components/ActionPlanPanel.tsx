import { useMemo, useState } from 'react'
import type { ActionPlanActivity } from '../hooks/useActionPlan'
import {
  ActivityType,
  ACTIVITY_COLORS,
  ACTIVITY_EMOJI,
  ACTIVITY_LABELS,
  FrequencyPeriod,
} from '../types'
import './ActionPlanPanel.css'

interface ActionPlanPanelProps {
  activities: ActionPlanActivity[]
  loading: boolean
  onClose: () => void
}

const FREQ_LABEL: Record<FrequencyPeriod, string> = {
  [FrequencyPeriod.DAILY]: 'day',
  [FrequencyPeriod.WEEKLY]: 'week',
  [FrequencyPeriod.MONTHLY]: 'month',
}

const ENERGY_LABEL = (cost: number) => {
  if (cost <= 2) return { label: 'Low', color: '#4CAF50' }
  if (cost <= 4) return { label: 'Med', color: '#FF9800' }
  return { label: 'High', color: '#F44336' }
}

export function ActionPlanPanel({ activities, loading, onClose }: ActionPlanPanelProps) {
  const [filterType, setFilterType] = useState<ActivityType | 'ALL'>('ALL')
  const [search, setSearch] = useState('')
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const filtered = useMemo(() => {
    let list = activities
    if (filterType !== 'ALL') list = list.filter(a => a.activity_type === filterType)
    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter(a =>
        a.name.toLowerCase().includes(q) || a.subtype.toLowerCase().includes(q)
      )
    }
    return list.sort((a, b) => a.priority - b.priority)
  }, [activities, filterType, search])

  const typeCounts = useMemo(() => {
    const counts: Partial<Record<ActivityType, number>> = {}
    for (const a of activities) {
      counts[a.activity_type] = (counts[a.activity_type] ?? 0) + 1
    }
    return counts
  }, [activities])

  return (
    <aside className="action-plan-panel" id="action-plan-panel" aria-label="Action Plan">
      {/* ── Header ─────────────────────────────────── */}
      <div className="ap-header">
        <div className="ap-header-top">
          <div className="ap-title-row">
            <span className="ap-title-icon">📋</span>
            <h3 className="ap-title">Action Plan</h3>
            <span className="ap-badge">{activities.length}</span>
          </div>
          <button className="ap-close" onClick={onClose} aria-label="Close action plan">×</button>
        </div>
        <p className="ap-subtitle">25 curated activities for the next 3 months</p>

        {/* Search */}
        <div className="ap-search-wrapper">
          <span className="ap-search-icon">🔍</span>
          <input
            id="action-plan-search"
            className="ap-search"
            type="text"
            placeholder="Search activities…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
          {search && (
            <button className="ap-search-clear" onClick={() => setSearch('')} aria-label="Clear search">
              ×
            </button>
          )}
        </div>
      </div>

      {/* ── Type filter chips ───────────────────────── */}
      <div className="ap-filters">
        <button
          className={`ap-chip ${filterType === 'ALL' ? 'active' : ''}`}
          onClick={() => setFilterType('ALL')}
        >
          All ({activities.length})
        </button>
        {(Object.values(ActivityType) as ActivityType[]).map(type => {
          const count = typeCounts[type]
          if (!count) return null
          return (
            <button
              key={type}
              className={`ap-chip ${filterType === type ? 'active' : ''}`}
              style={{ '--chip-color': ACTIVITY_COLORS[type] } as React.CSSProperties}
              onClick={() => setFilterType(type === filterType ? 'ALL' : type)}
            >
              {ACTIVITY_EMOJI[type]} {count}
            </button>
          )
        })}
      </div>

      {/* ── Activity list ───────────────────────────── */}
      <div className="ap-list">
        {loading ? (
          <div className="ap-loading">
            <div className="ap-spinner" />
            <span>Loading plan…</span>
          </div>
        ) : filtered.length === 0 ? (
          <div className="ap-empty">No activities match your filter</div>
        ) : (
          filtered.map(act => {
            const color = ACTIVITY_COLORS[act.activity_type]
            const emoji = ACTIVITY_EMOJI[act.activity_type]
            const isExpanded = expandedId === act.id
            const freq = `${act.frequency_times}× / ${FREQ_LABEL[act.frequency_period]}`
            const energy = ENERGY_LABEL(act.energy_cost)
            const hasBackups = act.backup_activity_ids.length > 0

            return (
              <div key={act.id} className="ap-item" style={{ '--act-color': color } as React.CSSProperties}>
                <button
                  className={`ap-item-header ${isExpanded ? 'expanded' : ''}`}
                  onClick={() => setExpandedId(isExpanded ? null : act.id)}
                  aria-expanded={isExpanded}
                >
                  <span className="ap-item-emoji">{emoji}</span>
                  <div className="ap-item-main">
                    <span className="ap-item-name">{act.name}</span>
                    <div className="ap-item-meta">
                      <span className="ap-meta-pill ap-meta-freq">{freq}</span>
                      <span className="ap-meta-pill ap-meta-dur">⏱ {act.duration_minutes}m</span>
                      {act.is_necessary && (
                        <span className="ap-meta-pill ap-meta-required">Required</span>
                      )}
                    </div>
                  </div>
                  <span className="ap-item-chevron">{isExpanded ? '▾' : '▸'}</span>
                </button>

                {isExpanded && (
                  <div className="ap-item-detail">
                    {act.details && (
                      <p className="ap-detail-text">{act.details}</p>
                    )}
                    <div className="ap-detail-grid">
                      <div className="ap-detail-row">
                        <span className="ap-detail-label">Type</span>
                        <span className="ap-detail-value" style={{ color }}>
                          {ACTIVITY_LABELS[act.activity_type]}
                        </span>
                      </div>
                      <div className="ap-detail-row">
                        <span className="ap-detail-label">Subtype</span>
                        <span className="ap-detail-value ap-subtype">{act.subtype}</span>
                      </div>
                      <div className="ap-detail-row">
                        <span className="ap-detail-label">Location</span>
                        <span className="ap-detail-value">
                          {act.location_name}
                          {act.remote_capable && (
                            <span className="ap-remote-tag"> · Remote ✓</span>
                          )}
                        </span>
                      </div>
                      <div className="ap-detail-row">
                        <span className="ap-detail-label">Energy</span>
                        <span className="ap-detail-value" style={{ color: energy.color }}>
                          {energy.label}
                        </span>
                      </div>
                      <div className="ap-detail-row">
                        <span className="ap-detail-label">Priority</span>
                        <span className="ap-detail-value">#{act.priority}</span>
                      </div>
                      <div className="ap-detail-row">
                        <span className="ap-detail-label">Backups</span>
                        <span className="ap-detail-value">
                          {hasBackups
                            ? `${act.backup_activity_ids.length} alternative${act.backup_activity_ids.length > 1 ? 's' : ''}`
                            : <span className="ap-no-backup">None</span>
                          }
                        </span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )
          })
        )}
      </div>
    </aside>
  )
}
