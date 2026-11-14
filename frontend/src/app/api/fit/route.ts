import { computeFit } from "@/lib/cala/match";
import { parseProfile } from "@/lib/leadline/validate";
import { requireUser } from "@/lib/server/auth";

export async function POST(request: Request) {
  const auth = await requireUser();
  if ("error" in auth) return auth.error;
  const body = (await request.json().catch(() => null)) as { profile?: unknown; investor?: unknown } | null;
  const profile = parseProfile(body?.profile);
  if (typeof profile === "string") return Response.json({ error: profile }, { status: 400 });
  const investor = typeof body?.investor === "string" ? body.investor.trim().slice(0, 120) : "";
  if (!investor) return Response.json({ error: "Missing investor." }, { status: 400 });
  try {
    return Response.json(await computeFit(profile, investor));
  } catch (err) {
    return Response.json({ error: (err as Error).message }, { status: 502 });
  }
}
