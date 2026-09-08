import { useEffect, useState } from "react";
import { app, initialToolOutput, unwrap } from "../lib/mcp";
import { OrdersPanel, type Payload } from "../components/OrdersPanel";

/**
 * The standalone order-history View.
 *
 * Owns the bridge; the panel owns the rendering, so the storefront can show
 * the same thing inline without a second ui/initialize handshake.
 */
export default function Orders() {
  const [seed, setSeed] = useState<Payload | null>(initialToolOutput());

  useEffect(() => {
    app.ontoolresult = (result: unknown) => setSeed(unwrap<Payload>(result));
    void app.connect();
  }, []);

  return <OrdersPanel seed={seed} />;
}
