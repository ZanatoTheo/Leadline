import { agentMatch, computeFit, founderKey, investorKey } from "@/lib/cala/match";
import { parseProfile } from "@/lib/leadline/validate";
import { requireUser } from "@/lib/server/auth";
import { ServiceError, withService } from "@/lib/server/leadline-service";

/** How well a founder profile fits an investor; a founder sees the agent's score when it ranked that investor. */
export const POST = withService(async (request: Request) => {
  const auth = await requireUser();
  if ("error" in auth) return auth.error;
  const { user } = auth;
  const body = (await request.json().catch(() => null)) as { profile?: unknown; investor?: unknown } | null;
  const profile = parseProfile(body?.profile);
  if (typeof profile === "string") return Response.json({ error: profile }, { status: 400 });
  const investor = typeof body?.investor === "string" ? body.investor.trim().slice(0, 120) : "";
  if (!investor) return Response.json({ error: "Missing investor." }, { status: 400 });
  try {
    const founderId = user.role === "founder" ? user.founderId : null;
    const [match, theirs] = founderId
      ? await Promise.all([
          agentMatch(founderKey(founderId), investorKey(investor)),
          agentMatch(investorKey(investor), founderKey(founderId)),
        ])
      : [null, null];
    const other = founderId ? { viewer: "founder" as const, score: theirs?.score ?? null } : undefined;
    return Response.json(await computeFit(profile, investor, match, undefined, other));
  } catch (err) {
    if (err instanceof ServiceError) throw err;
    return Response.json({ error: (err as Error).message }, { status: 502 });
  }
});
