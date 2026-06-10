import { useCallback, useEffect, useState } from "react";
import { ActivityType, FrequencyPeriod } from "../types";

const API_URL = "/api/activities";

export interface ActionPlanActivity {
  id: string;
  name: string;
  activity_type: ActivityType;
  subtype: string;
  priority: number;
  duration_minutes: number;
  frequency_times: number;
  frequency_period: FrequencyPeriod;
  is_necessary: boolean;
  backup_activity_ids: string[];
  location_name: string;
  remote_capable: boolean;
  details: string;
  energy_cost: number;
}

interface UseActionPlanReturn {
  activities: ActionPlanActivity[];
  loading: boolean;
  error: string | null;
}

export function useActionPlan(): UseActionPlanReturn {
  const [activities, setActivities] = useState<ActionPlanActivity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchPlan = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(API_URL);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setActivities(data.activities ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load action plan");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchPlan(); }, [fetchPlan]);

  return { activities, loading, error };
}
