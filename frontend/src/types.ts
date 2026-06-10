/**
 * TypeScript types mirroring backend/models.py
 *
 * Single source of truth for the frontend data shapes.
 * Every enum value and field name matches the Python @dataclass definitions.
 */

/* ═══════════════════════════════════════════════════════════
 *  ENUMS
 * ═══════════════════════════════════════════════════════════ */

export enum ActivityType {
  FITNESS = "FITNESS",
  FOOD_CONSUMPTION = "FOOD_CONSUMPTION",
  MEDICATION = "MEDICATION",
  THERAPY = "THERAPY",
  CONSULTATION = "CONSULTATION",
}

export enum ScheduleBlockType {
  ACTIVITY = "ACTIVITY",
  PREP = "PREP",
  TRANSIT = "TRANSIT",
  TRAVEL_DAY = "TRAVEL_DAY",
}

export enum TravelAdherence {
  STRICT = "STRICT",
  FLEXIBLE = "FLEXIBLE",
  BREAK = "BREAK",
}

export enum FrequencyPeriod {
  DAILY = "DAILY",
  WEEKLY = "WEEKLY",
  MONTHLY = "MONTHLY",
}

export enum DayOfWeek {
  MONDAY = "MONDAY",
  TUESDAY = "TUESDAY",
  WEDNESDAY = "WEDNESDAY",
  THURSDAY = "THURSDAY",
  FRIDAY = "FRIDAY",
  SATURDAY = "SATURDAY",
  SUNDAY = "SUNDAY",
}

/* ═══════════════════════════════════════════════════════════
 *  SCHEDULE OUTPUT INTERFACES
 * ═══════════════════════════════════════════════════════════ */

/** A single time block in the calendar. */
export interface ScheduleBlock {
  block_id: string;
  block_type: ScheduleBlockType;
  activity_id: string | null;
  activity_name: string;
  activity_type: ActivityType | null;
  date: string; // ISO date string "YYYY-MM-DD"
  start_time: string; // "HH:MM:SS" or "HH:MM"
  end_time: string;
  facilitator_id: string | null;
  facilitator_name: string;
  location: string;
  is_remote: boolean;
  metrics_to_collect: string[];
  notes: string;
  color_code: string;
  duration_minutes: number;
}

/** All blocks for a single day. */
export interface DaySchedule {
  date: string; // ISO date string
  day_of_week: DayOfWeek;
  blocks: ScheduleBlock[];
  is_travel_day: boolean;
  travel_destination: string | null;
  travel_adherence: TravelAdherence | null;
}

/** An activity that could not be placed in the schedule. */
export interface UnscheduledActivity {
  activity_id: string;
  activity_name: string;
  activity_type: ActivityType;
  target_date: string; // ISO date string
  reason: string;
  adjustment: string;
}

/** The complete schedule returned by the API. */
export interface FullSchedule {
  start_date: string;
  end_date: string;
  total_days: number;
  total_scheduled: number;
  total_unscheduled: number;
  days: DaySchedule[];
  unscheduled: UnscheduledActivity[];
  skip_summary: Record<string, number>;
}

/* ═══════════════════════════════════════════════════════════
 *  UI HELPER TYPES
 * ═══════════════════════════════════════════════════════════ */

/** react-big-calendar event shape with our extra metadata. */
export interface CalendarEvent {
  id: string;
  title: string;
  start: Date;
  end: Date;
  allDay: boolean;
  resource: CalendarEventResource;
}

/** Extra data attached to every CalendarEvent. */
export interface CalendarEventResource {
  blockType: ScheduleBlockType;
  activityType: ActivityType | null;
  isRemote: boolean;
  facilitatorName: string;
  location: string;
  metricsToCollect: string[];
  notes: string;
  travelDestination?: string;
  travelAdherence?: TravelAdherence;
  activityId: string | null;
}

/* ═══════════════════════════════════════════════════════════
 *  COLOR MAPS
 * ═══════════════════════════════════════════════════════════ */

export const ACTIVITY_COLORS: Record<ActivityType, string> = {
  [ActivityType.FITNESS]: "#4CAF50",
  [ActivityType.FOOD_CONSUMPTION]: "#FF9800",
  [ActivityType.MEDICATION]: "#2196F3",
  [ActivityType.THERAPY]: "#9C27B0",
  [ActivityType.CONSULTATION]: "#F44336",
};

export const BLOCK_TYPE_COLORS: Record<string, string> = {
  [ScheduleBlockType.PREP]: "#78909C",
  [ScheduleBlockType.TRANSIT]: "#607D8B",
  [ScheduleBlockType.TRAVEL_DAY]: "#00BCD4",
};

/** Emoji icons per activity / block type. */
export const ACTIVITY_EMOJI: Record<string, string> = {
  [ActivityType.FITNESS]: "🏃",
  [ActivityType.FOOD_CONSUMPTION]: "🍽️",
  [ActivityType.MEDICATION]: "💊",
  [ActivityType.THERAPY]: "🧊",
  [ActivityType.CONSULTATION]: "👨‍⚕️",
  [ScheduleBlockType.PREP]: "🔧",
  [ScheduleBlockType.TRANSIT]: "🚗",
  [ScheduleBlockType.TRAVEL_DAY]: "✈️",
};

/** Human-readable labels for activity types. */
export const ACTIVITY_LABELS: Record<ActivityType, string> = {
  [ActivityType.FITNESS]: "Fitness",
  [ActivityType.FOOD_CONSUMPTION]: "Food",
  [ActivityType.MEDICATION]: "Medication",
  [ActivityType.THERAPY]: "Therapy",
  [ActivityType.CONSULTATION]: "Consultation",
};
