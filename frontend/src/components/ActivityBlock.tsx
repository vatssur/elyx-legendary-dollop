import type { EventProps } from 'react-big-calendar'
import type { CalendarEvent } from '../types'
import { ScheduleBlockType, ACTIVITY_EMOJI } from '../types'
import './ActivityBlock.css'

export function ActivityBlock({ event }: EventProps<CalendarEvent>) {
  const { resource } = event
  const isTravel = resource.blockType === ScheduleBlockType.TRAVEL_DAY
  const isPrep = resource.blockType === ScheduleBlockType.PREP
  const isTransit = resource.blockType === ScheduleBlockType.TRANSIT

  const emoji =
    resource.activityType
      ? (ACTIVITY_EMOJI[resource.activityType] ?? '')
      : (ACTIVITY_EMOJI[resource.blockType] ?? '')

  if (isTravel) {
    return (
      <div className="event-block travel-block">
        <span className="event-emoji">✈️</span>
        <span className="event-title">{resource.travelDestination ?? 'Travel'}</span>
        {resource.travelAdherence && (
          <span className="travel-adherence">{resource.travelAdherence}</span>
        )}
      </div>
    )
  }

  return (
    <div className={`event-block ${isPrep ? 'prep-block' : ''} ${isTransit ? 'transit-block' : ''}`}>
      <span className="event-emoji">{emoji}</span>
      <span className="event-title">{event.title}</span>
      {resource.isRemote && <span className="event-badge remote" title="Remote">📹</span>}
    </div>
  )
}
