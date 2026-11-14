import { signUp } from "@/lib/server/auth";

export async function POST(request: Request) {
  const b = (await request.json().catch(() => null)) as Record<string, unknown> | null;
  const role = b?.role === "investor" ? "investor" : b?.role === "founder" ? "founder" : null;
  const name = typeof b?.name === "string" ? b.name.trim().slice(0, 80) : "";
  const email = typeof b?.email === "string" ? b.email.trim().slice(0, 160) : "";
  const password = typeof b?.password === "string" ? b.password : "";
  if (!role) return Response.json({ error: "Choose founder or investor." }, { status: 400 });
  if (!name || !/^\S+@\S+\.\S+$/.test(email)) return Response.json({ error: "Enter your name and a valid email." }, { status: 400 });
  if (password.length < 8) return Response.json({ error: "Use at least 8 characters for your password." }, { status: 400 });
  const err = await signUp({ role, name, email, password });
  if (err) return Response.json({ error: err }, { status: 409 });
  return Response.json({ role });
}
