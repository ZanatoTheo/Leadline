import { getTwins } from "@/lib/cala/leadline";
import { parseProfile } from "@/lib/leadline/validate";
import { requireRole } from "@/lib/server/auth";

export async function POST(request: Request) {
  const auth = await requireRole("founder");
  if ("error" in auth) return auth.error;
  const profile = parseProfile(await request.json().catch(() => null));
  if (typeof profile === "string") return Response.json({ error: profile }, { status: 400 });
  try {
    return Response.json(await getTwins(profile));
  } catch (err) {
    return Response.json({ error: (err as Error).message }, { status: 502 });
  }
}
