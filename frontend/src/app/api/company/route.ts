import { companyDiligence } from "@/lib/cala/diligence";
import { requireRole } from "@/lib/server/auth";

/** Due diligence on a startup found in Cala, for the logged-in investor. */
export async function POST(request: Request) {
  const auth = await requireRole("investor");
  if ("error" in auth) return auth.error;
  const investor = auth.user.investorName;
  if (!investor) return Response.json({ error: "Pick your fund first." }, { status: 400 });
  const body = (await request.json().catch(() => null)) as { company?: unknown } | null;
  const company = typeof body?.company === "string" ? body.company.trim().slice(0, 120) : "";
  if (!company) return Response.json({ error: "Missing company." }, { status: 400 });
  try {
    const result = await companyDiligence(company, investor);
    if (!result) return Response.json({ error: `Cala has no funding rounds for ${company}.` }, { status: 404 });
    return Response.json(result);
  } catch (err) {
    return Response.json({ error: (err as Error).message }, { status: 502 });
  }
}
