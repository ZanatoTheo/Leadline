import { withService } from "@/lib/server/leadline-service";
import { currentUser, demoLoginEnabled, toSessionUser } from "@/lib/server/auth";

export const GET = withService(async () => {
  const user = await currentUser();
  return Response.json({ user: user ? toSessionUser(user) : null, demoLogin: demoLoginEnabled() });
});
