# Site Previewer

Sign up, log in, paste a website URL, and get a screenshot preview that is saved to your account. Every URL you have saved is listed with its preview.

**Stack:** React (Vite) frontend, FastAPI backend, SQLite, Playwright (headless Chromium) for screenshots.

## Features

- Signup and login with email and password (bcrypt-hashed passwords, JWT bearer tokens, 24h expiry)
- Submit a URL: the server loads it in headless Chromium, saves a screenshot, and shows it immediately
- URL, page title, preview image and timestamp are stored per user
- Saved sites list showing all previous previews, with delete and retry
- Each user only sees their own sites

## Prerequisites

- Python 3.10+
- Node.js 18+

## Setup

### 1. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium        # downloads the browser used for screenshots
cp .env.example .env               # optional; set SECRET_KEY for anything beyond local use
uvicorn main:app --reload --port 8000
```

API docs: http://localhost:8000/docs. The SQLite database (`app.db`) and the `screenshots/` folder are created automatically on first run.

On Linux servers, if Chromium fails to start, run `playwright install-deps chromium`.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The Vite dev server proxies `/api` and `/screenshots` to the backend on port 8000.

## Testing the flow

1. Create an account, then log in.
2. Paste the test URL into the form:
   `https://www.justdial.com/Hyderabad/Dr-Sarita-Rao-Tx-Hospitals-Near-Masjid-Uppal-Bus-Stand-Bharath-Nagar-Colony-Uppal/040PXX40-XX40-231215200040-Y2E1_BZDET`
3. The preview appears under "Just saved" and in the "Saved sites" list. Refresh or log in again to confirm it persisted.

### Note on JustDial and other bot-protected sites

Some sites (JustDial included) use bot protection and may return HTTP 403 or an "Access Denied" page to automated browsers, depending on your network and IP. The app handles this rather than failing silently:

- The screenshot is still saved and the card shows a warning ("The site returned HTTP 403...").
- If the page can't be loaded at all, the card shows an error with a **Retry** button.
- The URL is saved either way.

To get the best results the browser sends a normal desktop user agent and hides the `webdriver` flag. If a site still blocks it, running the backend from a residential network (not a cloud IP) or using `headless=False` in `capture()` usually helps.

## API

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/signup` | no | `{email, password}` returns `{token, email}` |
| POST | `/api/auth/login` | no | `{email, password}` returns `{token, email}` |
| GET | `/api/me` | yes | Current user |
| POST | `/api/sites` | yes | `{url}` captures, saves and returns the site |
| GET | `/api/sites` | yes | All of the user's saved sites, newest first |
| POST | `/api/sites/{id}/retry` | yes | Re-capture a preview |
| DELETE | `/api/sites/{id}` | yes | Delete a site and its screenshot |

Send the token as `Authorization: Bearer <token>`.

## Design notes

- **Passwords:** hashed with bcrypt; plaintext is never stored.
- **SSRF protection:** URLs resolving to private, loopback or link-local addresses are rejected before the browser is launched.
- **Screenshots:** stored as JPEG files on disk with random names; the database stores the filename. Previews are served from `/screenshots`.
- **Capture is synchronous:** the request waits for the screenshot (up to ~30s) so the preview shows immediately. For production, move capture to a background job queue.
- **Token storage:** the JWT is kept in `localStorage` for simplicity. An httpOnly cookie would be the stronger choice in production.

## Project structure

```
backend/
  main.py             FastAPI app: models, auth, screenshot capture, routes
  requirements.txt
  .env.example
frontend/
  src/App.jsx         Auth screen, dashboard, site cards
  src/api.js          fetch wrapper and session helpers
  src/styles.css
  vite.config.js
```
