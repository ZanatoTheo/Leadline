import { withService } from "@/lib/server/leadline-service";
import { upsertFounderForUser } from "@/lib/server/db";
import { requireRole } from "@/lib/server/auth";
import { parseProfile } from "@/lib/leadline/validate";

/** Saves the logged-in founder's profile (shared with investors per their choice). */
export const POST = withService(async (request: Request) => {
  const auth = await requireRole("founder");
  if ("error" in auth) return auth.error;
  const body = (await request.json().catch(() => null)) as Record<string, unknown> | null;
  const profile = parseProfile(body?.profile);
  if (typeof profile === "string") return Response.json({ error: profile }, { status: 400 });
  const record = await upsertFounderForUser(auth.user.id, {
    profile,
    founderName: auth.user.name,
    email: auth.user.email,
    discoverable: body?.discoverable === true,
  });
  // The saved profile is trimmed and capped by parseProfile: the page stores this copy, not what it sent.
  return Response.json({ id: record.id, profile: record.profile });
});
