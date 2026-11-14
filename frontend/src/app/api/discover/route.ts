import { discover } from "@/lib/cala/match";
import { requireRole } from "@/lib/server/auth";
import { ServiceError, withService } from "@/lib/server/leadline-service";

/** Deal flow for the logged-in investor's own fund. */
export const POST = withService(async () => {
  const auth = await requireRole("investor");
  if ("error" in auth) return auth.error;
  if (!auth.user.investorName) return Response.json({ error: "Pick your fund first." }, { status: 400 });
  try {
    return Response.json(await discover(auth.user.investorName));
  } catch (err) {
    if (err instanceof ServiceError) throw err;
    return Response.json({ error: (err as Error).message }, { status: 502 });
  }
});
