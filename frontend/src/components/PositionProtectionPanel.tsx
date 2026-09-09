import { PositionSummaryPanel } from "./PositionSummaryPanel";
import { ProtectiveOrdersPanel } from "./ProtectiveOrdersPanel";
import type {
  PositionResponse,
  ProtectiveOrdersCurrentResponse,
} from "../models/positionProtection";

interface PositionProtectionPanelProps {
  position: PositionResponse;
  protectiveOrders: ProtectiveOrdersCurrentResponse;
}

export function PositionProtectionPanel({
  position,
  protectiveOrders,
}: PositionProtectionPanelProps) {
  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
      <PositionSummaryPanel position={position} />
      <ProtectiveOrdersPanel protectiveOrders={protectiveOrders} />
    </div>
  );
}
