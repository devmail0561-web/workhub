import createClient from "openapi-fetch";

import type { paths } from "./schema";

export type Health =
  paths["/api/v1/health"]["get"]["responses"][200]["content"]["application/json"];

export async function fetchHealth(): Promise<Health> {
  const client = createClient<paths>({
    baseUrl: import.meta.env.VITE_API_BASE_URL ?? window.location.origin,
  });
  const { data, error, response } = await client.GET("/api/v1/health");
  const status = response.status;
  if (error !== undefined) {
    throw new Error(`Échec de la sonde de santé (${status})`);
  }
  if (data === undefined) {
    throw new Error("Réponse de santé vide");
  }
  return data;
}
