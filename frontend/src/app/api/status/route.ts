import { calaMode } from "@/lib/cala/client";

export async function GET() {
  return Response.json({ mode: calaMode() });
}
