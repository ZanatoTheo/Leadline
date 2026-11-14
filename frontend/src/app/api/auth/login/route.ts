import { withService } from "@/lib/server/leadline-service";
import { logIn } from "@/lib/server/auth";

export const POST = withService(async (request: Request) => {
  const b = (await request.json().catch(() => null)) as Record<string, unknown> | null;
  const user = await logIn(String(b?.email ?? ""), String(b?.password ?? ""));
  if (!user) return Response.json({ error: "Wrong email or password." }, { status: 401 });
  return Response.json({ role: user.role });
});
