import { withService } from "@/lib/server/leadline-service";
import { endSession } from "@/lib/server/auth";

export const POST = withService(async () => {
  await endSession();
  return Response.json({ ok: true });
});
