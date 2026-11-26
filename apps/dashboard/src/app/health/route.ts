import { connection } from "next/server";

/** Dashboard liveness for container healthchecks. Does not call the API. */
export async function GET() {
  await connection();
  return Response.json({ status: "ok" }, { headers: { "cache-control": "no-store" } });
}
