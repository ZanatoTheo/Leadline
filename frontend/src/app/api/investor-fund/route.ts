import { setInvestorFund } from "@/lib/server/db";
import { requireRole } from "@/lib/server/auth";

/** An investor confirms which fund they represent. */
export async function POST(request: Request) {
  const auth = await requireRole("investor");
  if ("error" in auth) return auth.error;
  const body = (await request.json().catch(() => null)) as { investor?: unknown } | null;
  const investor = typeof body?.investor === "string" ? body.investor.trim().slice(0, 120) : "";
  if (!investor) return Response.json({ error: "Missing fund." }, { status: 400 });
  await setInvestorFund(auth.user.id, investor);
  return Response.json({ ok: true });
}
