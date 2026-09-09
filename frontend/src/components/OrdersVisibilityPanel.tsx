import { ExchangeOrdersPanel } from "./ExchangeOrdersPanel";
import { ExecutionIntentsPanel } from "./ExecutionIntentsPanel";
import type {
  ExchangeOrderIdentityListResponse,
  ExecutionIntentListResponse,
} from "../models/orderVisibility";

interface OrdersVisibilityPanelProps {
  executionIntents: ExecutionIntentListResponse;
  exchangeOrders: ExchangeOrderIdentityListResponse;
}

export function OrdersVisibilityPanel({
  executionIntents,
  exchangeOrders,
}: OrdersVisibilityPanelProps) {
  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
      <ExecutionIntentsPanel executionIntents={executionIntents} />
      <ExchangeOrdersPanel exchangeOrders={exchangeOrders} />
    </div>
  );
}
