import { redirect } from "next/navigation";
import { currentUser, toSessionUser } from "@/lib/server/auth";
import { SessionProvider } from "@/components/leadline/session";

/** Every founder page requires a logged-in founder. Investors are sent to their side. */
export default async function FounderLayout({ children }: { children: React.ReactNode }) {
  const user = await currentUser();
  if (!user) redirect("/login?role=founder");
  if (user.role !== "founder") redirect("/investor/today");
  return <SessionProvider user={toSessionUser(user)}>{children}</SessionProvider>;
}
