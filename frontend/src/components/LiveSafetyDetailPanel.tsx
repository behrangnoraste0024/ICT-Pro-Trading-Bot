import { KillSwitchStatusPanel } from "./KillSwitchStatusPanel";
import { PersistenceStatusPanel } from "./PersistenceStatusPanel";
import { ReadinessStatusPanel } from "./ReadinessStatusPanel";
import { SafetyStatusPanel } from "./SafetyStatusPanel";
import type {
  KillSwitchControlResponse,
  LiveReadinessResponse,
  LiveSafetyStatusResponse,
  PersistenceStatusResponse,
} from "../models/liveSafetyDetail";

interface LiveSafetyDetailPanelProps {
  safetyStatus: LiveSafetyStatusResponse;
  readiness: LiveReadinessResponse;
  persistence: PersistenceStatusResponse;
  killSwitch: KillSwitchControlResponse;
}

export function LiveSafetyDetailPanel({
  safetyStatus,
  readiness,
  persistence,
  killSwitch,
}: LiveSafetyDetailPanelProps) {
  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
      <SafetyStatusPanel safetyStatus={safetyStatus} />
      <ReadinessStatusPanel readiness={readiness} />
      <PersistenceStatusPanel persistence={persistence} />
      <KillSwitchStatusPanel killSwitch={killSwitch} />
    </div>
  );
}
