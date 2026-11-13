# Frontend WorkHub

Interface web React : Vite 8, TypeScript strict, Tailwind 4, shadcn/ui, TanStack Router et
TanStack Query. Le client API est généré depuis le contrat OpenAPI de FastAPI.

## Prérequis

- Node.js 20.19+
- pnpm 10+

## Commandes

```bash
pnpm install --frozen-lockfile
pnpm run dev          # http://localhost:5173 (proxy /api vers :8000)
pnpm run typecheck
pnpm run test
pnpm run build
```

## Client OpenAPI

`openapi.json` est un instantané du contrat backend. Après un changement d'API :

```bash
curl -fsS http://localhost:8000/openapi.json -o openapi.json
pnpm run generate:api
```
