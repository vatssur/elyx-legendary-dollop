import { useState, useMemo, useCallback, useRef } from 'react'
import { Calendar as BigCalendar, dateFnsLocalizer } from 'react-big-calendar'
import { format, parse, startOfWeek, getDay } from 'date-fns'
import { enUS } from 'date-fns/locale/en-US'
import 'react-big-calendar/lib/css/react-big-calendar.css'
import html2canvas from 'html2canvas'
import jsPDF from 'jspdf'

import { useSchedule } from './hooks/useSchedule'
import { useActionPlan } from './hooks/useActionPlan'
import { ActionPlanPanel } from './components/ActionPlanPanel'
import { ActivityBlock } from './components/ActivityBlock'
import { ActivityDetail } from './components/ActivityDetail'
import { UnscheduledPanel } from './components/UnscheduledPanel'
import { Legend } from './components/Legend'
import { ViewToggle } from './components/ViewToggle'
import type { CalendarEvent, CalendarEventResource } from './types'
import {
  ScheduleBlockType,
  ACTIVITY_COLORS,
  BLOCK_TYPE_COLORS,
} from './types'
import './App.css'

type ViewType = 'week' | 'month'

const locales = { 'en-US': enUS }

const localizer = dateFnsLocalizer({
  format,
  parse,
  startOfWeek: () => startOfWeek(new Date(), { weekStartsOn: 0 }),
  getDay,
  locales,
})

function getEventColor(resource: CalendarEventResource): string {
  if (resource.blockType === ScheduleBlockType.TRAVEL_DAY) {
    return BLOCK_TYPE_COLORS[ScheduleBlockType.TRAVEL_DAY] ?? '#00BCD4'
  }
  if (resource.blockType === ScheduleBlockType.PREP) {
    return BLOCK_TYPE_COLORS[ScheduleBlockType.PREP] ?? '#78909C'
  }
  if (resource.blockType === ScheduleBlockType.TRANSIT) {
    return BLOCK_TYPE_COLORS[ScheduleBlockType.TRANSIT] ?? '#607D8B'
  }
  if (resource.activityType) {
    return ACTIVITY_COLORS[resource.activityType] ?? '#666'
  }
  return '#666'
}

export default function App() {
  const { events, unscheduled, schedule, loading, error, refetch } = useSchedule()
  const { activities: actionPlan, loading: apLoading } = useActionPlan()
  const [currentView, setCurrentView] = useState<ViewType>('week')
  const [currentDate, setCurrentDate] = useState(() => new Date(2026, 5, 15))
  const [selectedEvent, setSelectedEvent] = useState<CalendarEvent | null>(null)
  const [showUnscheduled, setShowUnscheduled] = useState(false)
  const [showActionPlan, setShowActionPlan] = useState(false)
  const calendarRef = useRef<HTMLDivElement>(null)
  const [exporting, setExporting] = useState(false)

  const handleSelectEvent = useCallback((event: CalendarEvent) => {
    if (event.resource.blockType === ScheduleBlockType.TRAVEL_DAY) return
    setSelectedEvent(event)
  }, [])

  const handleNavigate = useCallback((newDate: Date) => {
    setCurrentDate(newDate)
  }, [])

  const eventPropGetter = useCallback(
    (event: CalendarEvent) => {
      const color = getEventColor(event.resource)
      const isTravel = event.resource.blockType === ScheduleBlockType.TRAVEL_DAY
      const isPrep = event.resource.blockType === ScheduleBlockType.PREP
      const isTransit = event.resource.blockType === ScheduleBlockType.TRANSIT

      return {
        style: {
          backgroundColor: isTravel
            ? color
            : `${color}cc`,
          color: '#fff',
          borderLeft: `3px solid ${color}`,
          opacity: isPrep || isTransit ? 0.75 : 1,
          fontSize: isPrep || isTransit ? '0.68rem' : '0.75rem',
        },
      }
    },
    []
  )

  const dayPropGetter = useCallback(
    (date: Date) => {
      if (!schedule) return {}
      const dateStr = format(date, 'yyyy-MM-dd')
      const day = schedule.days.find(d => d.date === dateStr)
      if (day?.is_travel_day) {
        return {
          style: {
            background: 'rgba(0, 188, 212, 0.06)',
          },
        }
      }
      return {}
    },
    [schedule]
  )

  const components = useMemo(() => ({
    event: ActivityBlock,
  }), [])

  const totalScheduled = schedule?.total_scheduled ?? 0
  const totalUnscheduled = schedule?.total_unscheduled ?? 0

  const handleExportPDF = useCallback(async () => {
    if (!calendarRef.current || !schedule) return
    setExporting(true)
    try {
      const el = calendarRef.current
      const originalHeight = el.style.height
      el.style.height = `${el.scrollHeight}px`
      const canvas = await html2canvas(el, {
        background: '#1a1a2e',
        useCORS: true,
        logging: false,
      })
      el.style.height = originalHeight
      const imgData = canvas.toDataURL('image/png')

      const pdf = new jsPDF('l', 'mm', 'a4')
      const pageW = pdf.internal.pageSize.getWidth()
      const pageH = pdf.internal.pageSize.getHeight()

      pdf.setFillColor(26, 26, 46)
      pdf.rect(0, 0, pageW, pageH, 'F')

      pdf.setTextColor(255, 255, 255)
      pdf.setFontSize(16)
      pdf.text('Health Schedule', pageW / 2, 14, { align: 'center' })

      pdf.setFontSize(9)
      const dateRange = `Week of ${format(currentDate, 'MMM d, yyyy')}`
      pdf.text(dateRange, pageW / 2, 21, { align: 'center' })

      pdf.setFontSize(8)
      const statsLine = `Scheduled: ${totalScheduled}  |  Skipped: ${totalUnscheduled}`
      pdf.text(statsLine, pageW / 2, 27, { align: 'center' })

      const imgW = pageW - 16
      const imgH = (canvas.height * imgW) / canvas.width
      const maxImgH = pageH - 34
      if (imgH > maxImgH) {
        const scale = maxImgH / imgH
        pdf.addImage(imgData, 'PNG', 8, 32, imgW * scale, imgH * scale)
      } else {
        pdf.addImage(imgData, 'PNG', 8, 32, imgW, imgH)
      }

      pdf.save('health-schedule.pdf')
    } finally {
      setExporting(false)
    }
  }, [schedule, currentDate, totalScheduled, totalUnscheduled])

  if (loading) {
    return (
      <div className="loading-screen">
        <div className="loading-spinner" />
        <h2 className="loading-title">Generating Schedule</h2>
        <p className="loading-subtitle">
          Allocating 86 activities across 91 days...
        </p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="error-screen">
        <div className="error-icon">⚠️</div>
        <h2 className="error-title">Connection Error</h2>
        <p className="error-message">{error}</p>
        <button className="error-retry" onClick={refetch}>
          Retry Connection
        </button>
        <p className="error-hint">
          Make sure the backend is running: <code>uvicorn main:app --reload</code>
        </p>
      </div>
    )
  }

  return (
    <div className={`app-layout ${showUnscheduled ? 'sidebar-open' : ''}`}>
      {/* ── Header ───────────────────────────────────── */}
      <header className="app-header" id="app-header">
        <div className="header-left">
          <h1 className="app-title">
            <span className="title-icon">🗓️</span>
            Health Schedule
          </h1>
          <div className="header-stats">
            <span className="stat stat-scheduled">
              <span className="stat-dot scheduled" />
              {totalScheduled} scheduled
            </span>
            <span className="stat stat-unscheduled">
              <span className="stat-dot unscheduled" />
              {totalUnscheduled} skipped
            </span>
          </div>
        </div>

        <div className="header-center">
          <button
            className="nav-btn"
            onClick={() => {
              const d = new Date(currentDate)
              if (currentView === 'week') d.setDate(d.getDate() - 7)
              else d.setMonth(d.getMonth() - 1)
              setCurrentDate(d)
            }}
            aria-label="Previous"
          >
            ‹
          </button>
          <span className="current-period">
            {currentView === 'week'
              ? `Week of ${format(currentDate, 'MMM d, yyyy')}`
              : format(currentDate, 'MMMM yyyy')}
          </span>
          <button
            className="nav-btn"
            onClick={() => {
              const d = new Date(currentDate)
              if (currentView === 'week') d.setDate(d.getDate() + 7)
              else d.setMonth(d.getMonth() + 1)
              setCurrentDate(d)
            }}
            aria-label="Next"
          >
            ›
          </button>
          <button
            className="nav-btn today-btn"
            onClick={() => setCurrentDate(new Date(2026, 5, 15))}
          >
            Today
          </button>
        </div>

        <div className="header-right">
          <ViewToggle current={currentView} onChange={setCurrentView} />
          <button
            className="sidebar-toggle export-btn"
            onClick={handleExportPDF}
            disabled={exporting}
            title="Export PDF"
            id="btn-export-pdf"
          >
            <span className="toggle-icon">{exporting ? '⏳' : '📄'}</span>
            <span className="toggle-label">PDF</span>
          </button>
          {/* Action Plan toggle */}
          <button
            className={`sidebar-toggle ${showActionPlan ? 'active' : ''}`}
            onClick={() => setShowActionPlan(v => !v)}
            title="Action Plan"
            id="toggle-action-plan"
          >
            <span className="toggle-icon">📋</span>
            <span className="toggle-label">Plan</span>
          </button>
          {/* Skipped Activities toggle */}
          <button
            className={`sidebar-toggle ${showUnscheduled ? 'active' : ''}`}
            onClick={() => setShowUnscheduled(v => !v)}
            title="Skipped Activities"
            id="toggle-unscheduled"
          >
            <span className="toggle-icon">⚠️</span>
            {totalUnscheduled > 0 && (
              <span className="toggle-badge">{totalUnscheduled}</span>
            )}
          </button>
        </div>
      </header>

      {/* ── Main Content ─────────────────────────────── */}
      <div className="app-body">
        <main className="calendar-container" id="calendar-main" ref={calendarRef}>
          <BigCalendar<CalendarEvent>
            localizer={localizer}
            events={events}
            view={currentView}
            date={currentDate}
            onNavigate={handleNavigate}
            onView={() => {}}
            onSelectEvent={handleSelectEvent}
            eventPropGetter={eventPropGetter}
            dayPropGetter={dayPropGetter}
            components={components}
            step={15}
            timeslots={4}
            min={new Date(2026, 5, 15, 5, 30)}
            max={new Date(2026, 5, 15, 22, 30)}
            scrollToTime={new Date(2026, 5, 15, 6, 0)}
            popup
            selectable={false}
            toolbar={false}
          />
          <Legend />
        </main>

        {showActionPlan && (
          <ActionPlanPanel
            activities={actionPlan}
            loading={apLoading}
            onClose={() => setShowActionPlan(false)}
          />
        )}

        {showUnscheduled && (
          <UnscheduledPanel
            items={unscheduled}
            skipSummary={schedule?.skip_summary}
            onClose={() => setShowUnscheduled(false)}
          />
        )}
      </div>

      {/* ── Detail Modal ─────────────────────────────── */}
      {selectedEvent && (
        <ActivityDetail
          event={selectedEvent}
          onClose={() => setSelectedEvent(null)}
        />
      )}
    </div>
  )
}
