import { buildShortlist, Pending } from "@/lib/cala/leadline";
import { parseProfile } from "@/lib/leadline/validate";
import { requireRole } from "@/lib/server/auth";
import { ServiceError, withService } from "@/lib/server/leadline-service";

/** The founder's investors, from the agent's stored ranking of their saved profile. */
export const POST = withService(async (request: Request) => {
  const auth = await requireRole("founder");
  if ("error" in auth) return auth.error;
  const profile = parseProfile(await request.json().catch(() => null));
  if (typeof profile === "string") return Response.json({ error: profile }, { status: 400 });
  if (!auth.user.founderId) return Response.json({ error: "Save your startup profile first." }, { status: 400 });
  try {
    return Response.json(await buildShortlist(profile, auth.user.founderId));
  } catch (err) {
    // Normal background work, not an error: 202 with the running step, so the page can show progress and poll.
    if (err instanceof Pending) return Response.json(err.pending, { status: 202 });
    if (err instanceof ServiceError) throw err;
    return Response.json({ error: (err as Error).message }, { status: 502 });
  }
});
