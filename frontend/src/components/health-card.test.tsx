import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { fetchHealth } from "@/api/health";
import { HealthCard } from "@/components/health-card";

vi.mock("@/api/health", () => ({ fetchHealth: vi.fn() }));

function renderCard() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <HealthCard />
    </QueryClientProvider>,
  );
}

describe("HealthCard", () => {
  it("affiche l'état de l'API et sa version", async () => {
    vi.mocked(fetchHealth).mockResolvedValue({ status: "ok", version: "0.1.0" });

    renderCard();

    expect(await screen.findByText("API opérationnelle")).toBeInTheDocument();
    expect(screen.getByText("Version 0.1.0")).toBeInTheDocument();
  });
});
