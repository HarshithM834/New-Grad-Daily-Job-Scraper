# CareerOps web dashboard

A React 19 / Vite / Tailwind 3 frontend with shadcn-style **owned components** and Radix Dialog, Select, and Switch primitives. The existing Python dashboard API remains the source of truth.

## Development

Start the Python API in the repository root:

```bash
python dashboard_server.py
```

In a second terminal:

```bash
cd web
npm install
npm run dev
# http://127.0.0.1:5173
```

The Vite proxy connects to the local API on port 8765, including the local-only Origin requirement for writes. No third-party deployment is needed.

## Production build

```bash
cd web
npm install
npm run build
cd ..
python dashboard_server.py
```

The Python server serves the built React dashboard from `web/dist` if it exists. Otherwise it falls back to the existing dependency-free dashboard, keeping first-time setup simple.

## Design principles

`DESIGN.md` is the product-specific design contract. React component source is owned here, not delivered through a hosted UI framework. No sample KPI data is rendered in the live app. The project does not copy or ship the four community design-skill repositories.