import { useCallback, useEffect, useState } from "react";
import type {
  CalendarEvent,
  CalendarEventResource,
  DaySchedule,
  FullSchedule,
  ScheduleBlock,
  UnscheduledActivity,
} from "../types";
import { ScheduleBlockType } from "../types";

const API_URL = "/api/schedule";

interface UseScheduleReturn {
  events: CalendarEvent[];
  unscheduled: UnscheduledActivity[];
  schedule: FullSchedule | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

/**
 * Parse "HH:MM" or "HH:MM:SS" time string into hours and minutes.
 */
function parseTime(timeStr: string): { hours: number; minutes: number } {
  const parts = timeStr.split(":");
  return {
    hours: parseInt(parts[0] ?? "0", 10),
    minutes: parseInt(parts[1] ?? "0", 10),
  };
}

/**
 * Combine a date string ("YYYY-MM-DD") and time string ("HH:MM:SS")
 * into a JavaScript Date object.
 */
function combineDateAndTime(dateStr: string, timeStr: string): Date {
  const dateParts = dateStr.split("-");
  const year = parseInt(dateParts[0] ?? "2026", 10);
  const month = parseInt(dateParts[1] ?? "1", 10);
  const day = parseInt(dateParts[2] ?? "1", 10);
  const { hours, minutes } = parseTime(timeStr);
  return new Date(year, month - 1, day, hours, minutes, 0);
}

/**
 * Convert a ScheduleBlock into a CalendarEvent for react-big-calendar.
 */
function blockToEvent(
  block: ScheduleBlock,
  day: DaySchedule
): CalendarEvent {
  const isTravelDay = block.block_type === ScheduleBlockType.TRAVEL_DAY;

  const resource: CalendarEventResource = {
    blockType: block.block_type,
    activityType: block.activity_type,
    isRemote: block.is_remote,
    isBackup: block.is_backup,
    facilitatorName: block.facilitator_name,
    location: block.location,
    metricsToCollect: block.metrics_to_collect,
    notes: block.notes,
    activityId: block.activity_id,
    originalActivityId: block.original_activity_id,
  };

  if (isTravelDay) {
    resource.travelDestination = day.travel_destination ?? undefined;
    resource.travelAdherence = day.travel_adherence ?? undefined;

    const dateObj = new Date(block.date + "T00:00:00");
    return {
      id: block.block_id,
      title: `✈️ ${day.travel_destination ?? "Travel Day"}`,
      start: dateObj,
      end: dateObj,
      allDay: true,
      resource,
    };
  }

  return {
    id: block.block_id,
    title: block.activity_name,
    start: combineDateAndTime(block.date, block.start_time),
    end: combineDateAndTime(block.date, block.end_time),
    allDay: false,
    resource,
  };
}

export function useSchedule(): UseScheduleReturn {
  const [schedule, setSchedule] = useState<FullSchedule | null>(null);
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [unscheduled, setUnscheduled] = useState<UnscheduledActivity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSchedule = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(API_URL);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data: FullSchedule = await response.json();
      setSchedule(data);
      setUnscheduled(data.unscheduled);

      // Convert all blocks from all days into CalendarEvents
      const calendarEvents: CalendarEvent[] = [];

      for (const day of data.days) {
        for (const block of day.blocks) {
          calendarEvents.push(blockToEvent(block, day));
        }

        // If a day is a travel day but has no TRAVEL_DAY block, add a synthetic one
        if (
          day.is_travel_day &&
          !day.blocks.some(
            (b) => b.block_type === ScheduleBlockType.TRAVEL_DAY
          )
        ) {
          const dateObj = new Date(day.date + "T00:00:00");
          calendarEvents.push({
            id: `travel-${day.date}`,
            title: `✈️ ${day.travel_destination ?? "Travel Day"}`,
            start: dateObj,
            end: dateObj,
            allDay: true,
            resource: {
              blockType: ScheduleBlockType.TRAVEL_DAY,
              activityType: null,
              isRemote: false,
              isBackup: false,
              facilitatorName: "",
              location: day.travel_destination ?? "",
              metricsToCollect: [],
              notes: "",
              travelDestination: day.travel_destination ?? undefined,
              travelAdherence: day.travel_adherence ?? undefined,
              activityId: null,
              originalActivityId: null,
            },
          });
        }
      }

      setEvents(calendarEvents);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to fetch schedule";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSchedule();
  }, [fetchSchedule]);

  return { events, unscheduled, schedule, loading, error, refetch: fetchSchedule };
}
