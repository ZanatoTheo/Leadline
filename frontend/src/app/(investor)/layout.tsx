import { redirect } from "next/navigation";
import { currentUser, toSessionUser } from "@/lib/server/auth";
import { SessionProvider } from "@/components/leadline/session";

/** Every investor page requires a logged-in investor. Founders are sent to their side. */
export default async function InvestorLayout({ children }: { children: React.ReactNode }) {
  const user = await currentUser();
  if (!user) redirect("/login?role=investor");
  if (user.role !== "investor") redirect("/today");
  return <SessionProvider user={toSessionUser(user)}>{children}</SessionProvider>;
}
