import { currentUser, demoLoginEnabled, toSessionUser } from "@/lib/server/auth";

export async function GET() {
  const user = await currentUser();
  return Response.json({ user: user ? toSessionUser(user) : null, demoLogin: demoLoginEnabled() });
}
