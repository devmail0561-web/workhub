import { Outlet } from "@tanstack/react-router";

export function AppLayout() {
  return (
    <div className="flex min-h-full flex-col">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-4xl items-center gap-3 px-6 py-4">
          <span className="text-lg font-semibold tracking-tight">WorkHub</span>
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
            fondations
          </span>
        </div>
      </header>
      <Outlet />
    </div>
  );
}
