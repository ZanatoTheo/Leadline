import { createIntro, readDb, respondToIntro } from "@/lib/server/db";
import { requireUser } from "@/lib/server/auth";
import { PASS_REASONS, type Intro } from "@/lib/leadline/match-types";

const str = (v: unknown, max: number) => (typeof v === "string" ? v.trim().slice(0, max) : "");

/**
 * The caller's own intros only, decided by their session:
 *  - founder  → intros involving their startup
 *  - investor → intros involving their fund, with founder details; the
 *               founder's email appears only once both sides said yes
 */
export async function GET() {
  const auth = await requireUser();
  if ("error" in auth) return auth.error;
  const { user } = auth;
  const db = await readDb();

  if (user.role === "founder") {
    const intros = user.founderId ? db.intros.filter((i) => i.founderId === user.founderId) : [];
    return Response.json({ intros: intros.sort((a, b) => b.createdAt.localeCompare(a.createdAt)) });
  }

  const intros = db.intros
    .filter((i) => i.investor === user.investorName)
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
    .map((i) => {
      const f = db.founders.find((x) => x.id === i.founderId);
      return {
        ...i,
        founder: f
          ? { id: f.id, profile: f.profile, founderName: f.founderName, email: i.status === "accepted" ? f.email : undefined }
          : null,
      };
    });
  return Response.json({ intros });
}

/** Founders request intros to an investor; investors invite a founder. */
export async function POST(request: Request) {
  const auth = await requireUser();
  if ("error" in auth) return auth.error;
  const { user } = auth;
  const body = (await request.json().catch(() => null)) as Record<string, unknown> | null;
  const note = str(body?.note, 1000);

  if (user.role === "founder") {
    const investor = str(body?.investor, 120);
    if (!user.founderId) return Response.json({ error: "Save your startup profile first." }, { status: 400 });
    if (!investor) return Response.json({ error: "Missing investor." }, { status: 400 });
    const intro = await createIntro({ founderId: user.founderId, investor, direction: "founder-to-investor", note });
    return Response.json({ intro });
  }

  if (!user.investorName) return Response.json({ error: "Pick your fund first." }, { status: 400 });
  const founderId = str(body?.founderId, 64);
  const db = await readDb();
  const founder = db.founders.find((f) => f.id === founderId);
  if (!founder || !founder.discoverable) {
    return Response.json({ error: "This founder isn't open to invites." }, { status: 404 });
  }
  const intro = await createIntro({ founderId, investor: user.investorName, direction: "investor-to-founder", note });
  return Response.json({ intro });
}

export async function PATCH(request: Request) {
  const auth = await requireUser();
  if ("error" in auth) return auth.error;
  const { user } = auth;
  const body = (await request.json().catch(() => null)) as Record<string, unknown> | null;
  const status = body?.status as Intro["status"];
  if (status !== "accepted" && status !== "passed") return Response.json({ error: "Bad status." }, { status: 400 });
  const reason = str(body?.passReason, 120);
  const passReason = (PASS_REASONS as readonly string[]).includes(reason) ? reason : reason ? "Other" : undefined;

  const by =
    user.role === "founder"
      ? user.founderId
        ? ({ role: "founder", founderId: user.founderId } as const)
        : null
      : user.investorName
        ? ({ role: "investor", investorName: user.investorName } as const)
        : null;
  const intro = by ? await respondToIntro(str(body?.id, 64), by, status, passReason) : null;
  if (!intro) return Response.json({ error: "Intro not found, or not yours to answer." }, { status: 404 });
  return Response.json({ intro });
}
