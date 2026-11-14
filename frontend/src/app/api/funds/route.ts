import { entitySearch } from "@/lib/cala/client";

/** Fund name autocomplete, backed by Cala entity search. */
export async function GET(request: Request) {
  const q = new URL(request.url).searchParams.get("q")?.trim() ?? "";
  if (q.length < 2) return Response.json({ funds: [] });
  try {
    const entities = await entitySearch(q, ["Organization", "Company"], 8);
    return Response.json({ funds: entities.map((e) => ({ id: e.id, name: e.name })) });
  } catch (err) {
    return Response.json({ error: (err as Error).message }, { status: 502 });
  }
}
