# Frontend (Admin SPA)

React + Vite admin UI for authentication and car inventory review.

## Features
- `/login` sign-in form, stores JWT in `localStorage`
- `/` protected route with cars table from backend API
- refresh, search, logout, and responsive layout

## Run locally
```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Backend dependency
Backend should be running on `http://localhost:8000`.
The Vite dev server proxies `/api` and `/health` requests to backend.

## Optional env override
You can define `VITE_API_BASE_URL` in `.env` if needed.
Example:

```env
VITE_API_BASE_URL=http://localhost:8000
```
