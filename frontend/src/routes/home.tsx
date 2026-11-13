import { HealthCard } from "@/components/health-card";

export function HomePage() {
  return (
    <main className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-6 py-10">
      <div className="space-y-2">
        <p className="text-xs font-medium uppercase tracking-widest text-slate-500">
          Référentiel opérationnel
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">
          Squelette frontend opérationnel
        </h1>
        <p className="max-w-2xl text-sm text-slate-600">
          React, TypeScript strict, Tailwind, shadcn/ui, TanStack Router et TanStack
          Query sont câblés. Le client OpenAPI est généré depuis le contrat FastAPI.
        </p>
      </div>
      <HealthCard />
    </main>
  );
}
