# Putting Book Exchange online (₹0)

All the code is ready. Going live is creating 5 free accounts and pasting settings.
Do the steps **in order**. Each one gives you a value you need in a later step.
Keep the values in a private note (not in this repo).

| # | Service | What it does | You'll copy |
|---|---|---|---|
| 1 | **Neon** | Postgres database | `DATABASE_URL` |
| 2 | **Cloudinary** | Stores book photos | `CLOUDINARY_URL` |
| 3 | **Brevo** | Sends verification/reset emails | `BREVO_API_KEY` + your verified sender email |
| 4 | **Render** | Runs the FastAPI backend | your API address, e.g. `https://book-exchange-api.onrender.com` |
| 5 | **Vercel** | Hosts the React website | your site address, e.g. `https://book-exchange.vercel.app` |

Before starting: make sure your latest code is pushed to GitHub (`git status` is clean, then `git push`).

---

## 1. Neon (database)
1. Sign up at **neon.com** (no card needed) and create a project, e.g. `book-exchange`. Pick the region closest to India (e.g. Singapore) if offered.
2. Open **Connect** / **Connection string** and copy it. It looks like
   `postgresql://user:password@ep-xxxx.ap-southeast-1.aws.neon.tech/neondb?sslmode=require`
3. This is `DATABASE_URL`. It contains a password, so treat it as a secret.

You don't create any tables: the backend's migrations do that the first time it starts.

## 2. Cloudinary (photos)
1. Sign up at **cloudinary.com** (free plan).
2. On the dashboard, find the **API environment variable**: `cloudinary://API_KEY:API_SECRET@CLOUD_NAME`.
3. Copy everything after `CLOUDINARY_URL=`. This is `CLOUDINARY_URL` (a secret).

## 3. Brevo (emails)
1. Sign up at **brevo.com** (free plan).
2. **Senders**: add and verify the email address the app sends from (your Gmail works; Brevo emails you a confirmation link).
3. **SMTP & API → API Keys**: create a key. This is `BREVO_API_KEY` (a secret).
4. Your `EMAIL_FROM` will be `Book Exchange <the-email-you-verified@gmail.com>`.

Emails sent from a Gmail address through a service can land in spam at first. Tell early users to check spam. A custom domain fixes this later.

## 4. Render (backend)
1. Sign up at **render.com** with your GitHub account.
2. **New → Blueprint**, then pick the `book-exchange` repo. Render reads `render.yaml` and creates `book-exchange-api` on the **Free** plan.
3. It asks for the secret values. Paste:
   - `DATABASE_URL`: from Neon
   - `CLOUDINARY_URL`: from Cloudinary
   - `BREVO_API_KEY`: from Brevo
   - `EMAIL_FROM`: `Book Exchange <your-verified@gmail.com>`
   - `FRONTEND_ORIGINS`: put `http://localhost:5173` for now; you'll change it in step 6.
4. Deploy. Watch the **Logs**. You should see the migrations run, then `Uvicorn running`.
5. Open `https://YOUR-SERVICE.onrender.com/docs`. The same `/docs` page you know, now online, with `https` and a padlock.
6. Quick test there: **POST /auth/signup** with **your real email**. You should receive a real code by email.

If Blueprint isn't available, do **New → Web Service** with the repo instead, and set: Root directory `backend`, Build `pip install -r requirements.txt`, Start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, Instance type **Free**, plus the environment variables from `render.yaml` (including `STORAGE_BACKEND=cloudinary` and `EMAIL_BACKEND=brevo`).

The free server sleeps after 15 minutes without visitors; the next visitor waits about a minute while it wakes up. That's normal on the free plan.

## 5. Vercel (website)
1. Sign up at **vercel.com** with GitHub, then **Add New → Project** and import the `book-exchange` repo.
2. **Root Directory**: `frontend`. Framework: **Vite** (usually detected automatically).
3. **Environment Variables**: `VITE_API_URL` = your Render address from step 4 (no trailing `/`).
4. Deploy, and copy your site address, e.g. `https://book-exchange.vercel.app`.

## 6. Connect the two
1. Back on Render, go to **Environment** and set `FRONTEND_ORIGINS` to your Vercel address (to keep local development working too: `https://book-exchange.vercel.app,http://localhost:5173`). Save; Render restarts.
2. Open your Vercel site, sign up with your real email, verify with the emailed code, list a book with a photo. Then on your phone (another account), request it and chat.

## After launch
- Every `git push` updates both sites automatically (Render and Vercel watch your GitHub repo).
- If you change `models.py`, create a migration first (see README → Migrations). Never delete the online database.
- Changing a secret: edit it in Render/Vercel settings, never in code.
- If a secret ever ends up on GitHub by mistake: create a new one in that service immediately (Neon: reset password, Cloudinary/Brevo: new key) and update Render.
