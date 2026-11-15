import { calaMode } from "@/lib/cala/client";
import * as service from "@/lib/server/leadline-service";

/** The data mode ("live" once the database holds Cala facts) and the agent's job counts. */
export async function GET() {
  try {
    return Response.json(await service.status());
  } catch {
    return Response.json({ mode: calaMode(), jobs: null, error: "The Leadline service is not reachable." });
  }
}
