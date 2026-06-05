/**
 * Backend URL configuration.
 *
 * Read from Vite env at build time so the same artifact can target localhost,
 * a staging deployment, or production by setting VITE_API_BASE in .env files
 * or the deploy environment. The fallbacks here keep `npm run dev` working
 * out of the box for new contributors who haven't created a frontend/.env yet.
 */

const trimSlash = (s: string) => s.replace(/\/+$/, "");

/** Full base URL including the /api/v1 prefix — used by all REST + SSE calls. */
export const API_BASE = trimSlash(
  import.meta.env.VITE_API_BASE ?? "http://localhost:8000/api/v1"
);

/** Backend root (no /api/v1) — used for the App-level health probe at `/`. */
export const BACKEND_ROOT = trimSlash(
  import.meta.env.VITE_BACKEND_ROOT ?? "http://localhost:8000"
);

/** Discord webhook receiver — best-effort, only used by StockExplorer's "Push Alert". */
export const DISCORD_WEBHOOK_URL = trimSlash(
  import.meta.env.VITE_DISCORD_WEBHOOK_URL ?? "http://localhost:5000/alert"
);
