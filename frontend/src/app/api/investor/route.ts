import { getInvestorBrief } from "@/lib/cala/leadline";
import { parseProfile } from "@/lib/leadline/validate";
import { requireRole } from "@/lib/server/auth";

export async function POST(request: Request) {
  const auth = await requireRole("founder");
  if ("error" in auth) return auth.error;
  const body = (await request.json().catch(() => null)) as { profile?: unknown; slug?: unknown } | null;
  const profile = parseProfile(body?.profile);
  if (typeof profile === "string") return Response.json({ error: profile }, { status: 400 });
  if (typeof body?.slug !== "string") return Response.json({ error: "Missing investor." }, { status: 400 });
  try {
    const result = await getInvestorBrief(profile, body.slug);
    if (!result) return Response.json({ error: "Investor not found in matching rounds." }, { status: 404 });
    return Response.json(result);
  } catch (err) {
    return Response.json({ error: (err as Error).message }, { status: 502 });
  }
}
