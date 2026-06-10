import { useCallback, useEffect } from 'react'
import { format } from 'date-fns'
import type { CalendarEvent } from '../types'
import {
  ACTIVITY_EMOJI,
  ACTIVITY_LABELS,
  ScheduleBlockType,
} from '../types'
import './ActivityDetail.css'

interface ActivityDetailProps {
  event: CalendarEvent
  onClose: () => void
}

export function ActivityDetail({ event, onClose }: ActivityDetailProps) {
  const { resource } = event

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    },
    [onClose]
  )

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  const emoji = resource.activityType
    ? (ACTIVITY_EMOJI[resource.activityType] ?? '📋')
    : (ACTIVITY_EMOJI[resource.blockType] ?? '📋')

  const typeLabel = resource.activityType
    ? (ACTIVITY_LABELS[resource.activityType] ?? resource.activityType)
    : resource.blockType

  const blockTypeLabel = resource.blockType === ScheduleBlockType.PREP
    ? 'Preparation'
    : resource.blockType === ScheduleBlockType.TRANSIT
    ? 'Transit'
    : 'Activity'

  return (
    <div className="detail-overlay" onClick={onClose} id="activity-detail-modal">
      <div className="detail-card" onClick={e => e.stopPropagation()}>
        <button className="detail-close" onClick={onClose} aria-label="Close">
          ×
        </button>

        <div className="detail-header">
          <span className="detail-emoji">{emoji}</span>
          <div className="detail-header-text">
            <h2 className="detail-title">{event.title}</h2>
            <div className="detail-badges">
              <span className="detail-type-badge">{typeLabel}</span>
              <span className="detail-block-badge">{blockTypeLabel}</span>
              {resource.isRemote && (
                <span className="detail-badge remote">📹 Remote</span>
              )}
            </div>
          </div>
        </div>

        <div className="detail-body">
          <div className="detail-row">
            <span className="detail-label">📅 Date</span>
            <span className="detail-value">
              {format(event.start, 'EEEE, MMM d, yyyy')}
            </span>
          </div>

          <div className="detail-row">
            <span className="detail-label">🕐 Time</span>
            <span className="detail-value">
              {format(event.start, 'h:mm a')} – {format(event.end, 'h:mm a')}
            </span>
          </div>

          <div className="detail-row">
            <span className="detail-label">📍 Location</span>
            <span className="detail-value">{resource.location || 'Home'}</span>
          </div>

          {resource.facilitatorName && (
            <div className="detail-row">
              <span className="detail-label">👤 Facilitator</span>
              <span className="detail-value">{resource.facilitatorName}</span>
            </div>
          )}

          {resource.notes && (
            <div className="detail-row detail-row-full">
              <span className="detail-label">📝 Notes</span>
              <span className="detail-value detail-notes">{resource.notes}</span>
            </div>
          )}

          {resource.metricsToCollect.length > 0 && (
            <div className="detail-row detail-row-full">
              <span className="detail-label">📊 Metrics</span>
              <div className="detail-metrics">
                {resource.metricsToCollect.map(m => (
                  <span key={m} className="metric-chip">{m}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
