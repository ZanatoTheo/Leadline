import { withService } from "@/lib/server/leadline-service";
import { startupDiligence } from "@/lib/cala/diligence";
import { requireRole } from "@/lib/server/auth";
import { getFounder, listIntros } from "@/lib/server/db";

/**
 * Due diligence on a Leadline founder, for the logged-in investor. Only
 * founders who opted in to discovery, or who have an intro with this
 * investor's fund, can be viewed.
 */
export const POST = withService(async (request: Request) => {
  const auth = await requireRole("investor");
  if ("error" in auth) return auth.error;
  const investor = auth.user.investorName;
  if (!investor) return Response.json({ error: "Pick your fund first." }, { status: 400 });

  const body = (await request.json().catch(() => null)) as { founderId?: unknown } | null;
  const founderId = typeof body?.founderId === "string" ? body.founderId : "";
  const [founder, intros] = await Promise.all([getFounder(founderId), founderId ? listIntros({ founderId, investor }) : []]);
  const intro = intros.sort((a, b) => b.createdAt.localeCompare(a.createdAt))[0] ?? null;
  if (!founder || (!founder.discoverable && !intro)) {
    return Response.json({ error: "This startup isn't visible to you." }, { status: 404 });
  }
  try {
    return Response.json(await startupDiligence(founder, investor, intro));
  } catch (err) {
    return Response.json({ error: (err as Error).message }, { status: 502 });
  }
});
