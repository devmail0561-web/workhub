import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchHealth } from "./health";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("fetchHealth", () => {
  it("retourne la santé typée", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ status: "ok", version: "0.1.0" })),
    );

    await expect(fetchHealth()).resolves.toEqual({
      status: "ok",
      version: "0.1.0",
    });
  });

  it("rejette une réponse HTTP en erreur", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ detail: "boom" }, 500)));

    await expect(fetchHealth()).rejects.toThrow("500");
  });
});
