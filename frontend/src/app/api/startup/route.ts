import { startupDiligence } from "@/lib/cala/diligence";
import { requireRole } from "@/lib/server/auth";
import { readDb } from "@/lib/server/db";

/**
 * Due diligence on a Leadline founder, for the logged-in investor. Only
 * founders who opted in to discovery, or who have an intro with this
 * investor's fund, can be viewed.
 */
export async function POST(request: Request) {
  const auth = await requireRole("investor");
  if ("error" in auth) return auth.error;
  const investor = auth.user.investorName;
  if (!investor) return Response.json({ error: "Pick your fund first." }, { status: 400 });

  const body = (await request.json().catch(() => null)) as { founderId?: unknown } | null;
  const founderId = typeof body?.founderId === "string" ? body.founderId : "";
  const db = await readDb();
  const founder = db.founders.find((f) => f.id === founderId);
  const intro =
    db.intros
      .filter((i) => i.founderId === founderId && i.investor === investor)
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))[0] ?? null;
  if (!founder || (!founder.discoverable && !intro)) {
    return Response.json({ error: "This startup isn't visible to you." }, { status: 404 });
  }
  try {
    return Response.json(await startupDiligence(founder, investor, intro));
  } catch (err) {
    return Response.json({ error: (err as Error).message }, { status: 502 });
  }
}
