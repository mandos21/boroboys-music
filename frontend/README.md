# Boro Boys Music Frontend

This package contains the React/Vite app that will drive the user interface for the platform.

## Getting Started

```bash
npm install
npm run dev
```

The dev server proxies `/api` requests to the FastAPI backend. Configure `VITE_API_URL` if the backend runs on a non-default origin.

## Production Build

```bash
npm run build
npm run preview
```

Deploy the build output under the `frontend/dist` directory (created by Vite).
