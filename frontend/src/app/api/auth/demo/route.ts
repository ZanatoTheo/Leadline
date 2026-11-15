import { withService } from "@/lib/server/leadline-service";
import { demoLoginEnabled, logInDemo } from "@/lib/server/auth";

/** One-click demo login (development only). */
export const POST = withService(async (request: Request) => {
  if (!demoLoginEnabled()) return Response.json({ error: "Demo login is disabled." }, { status: 404 });
  const b = (await request.json().catch(() => null)) as { role?: unknown } | null;
  const role = b?.role === "investor" ? "investor" : "founder";
  await logInDemo(role);
  return Response.json({ role });
});
