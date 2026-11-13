import { useQuery } from "@tanstack/react-query";

import { fetchHealth } from "@/api/health";
import { Button } from "@/components/ui/button";

export function HealthCard() {
  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth });

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="text-lg font-semibold">État de l&apos;API</h2>
      <div className="mt-3 space-y-3 text-sm">
        {health.isPending ? (
          <p className="text-slate-500">Vérification en cours…</p>
        ) : health.isError ? (
          <>
            <p className="font-medium text-red-700">API indisponible</p>
            <p className="text-slate-500">{health.error.message}</p>
            <Button onClick={() => void health.refetch()}>Réessayer</Button>
          </>
        ) : (
          <>
            <p className="font-medium text-emerald-700">API opérationnelle</p>
            <p className="text-slate-500">Version {health.data.version}</p>
            <Button variant="outline" onClick={() => void health.refetch()}>
              Rafraîchir
            </Button>
          </>
        )}
      </div>
    </section>
  );
}
