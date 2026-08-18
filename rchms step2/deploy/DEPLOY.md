# RCHMS Deployment Guide — Render

Render doesn't offer a free MySQL database anymore, so this pairs **Render**
(hosts the Flask app) with **Aiven** (a genuinely free-forever managed MySQL,
no credit card needed). Both free tiers, both permanent.

Heads-up on Render's free web service: it **spins down after ~15 minutes of
no traffic** and takes 30–60 seconds to wake back up on the next request.
Fine for a lecturer checking it occasionally — just means the very first
load after a quiet period will feel slow. Nothing you need to do about it,
just don't be surprised.

---

## Part 1 — Quick live link for a presentation (ngrok)

If you need a public link *today* without waiting on any deploy, you can
still just run RCHMS on your own PC and tunnel it:
1. Sign up free at https://ngrok.com, install it, run:
   ```
   ngrok config add-authtoken YOUR_TOKEN
   ```
2. Start RCHMS as usual (`python run.py`), then in a second terminal:
   ```
   ngrok http 5000
   ```
3. Share the `https://....ngrok-free.app` link it gives you.

Skip to Part 2 for the permanent Render setup.

---

## Part 2 — Permanent hosting on Render + Aiven MySQL

### Step 1 — Create the free MySQL database (Aiven)
1. Go to https://aiven.io, sign up free (no card required).
2. Create a new service → **MySQL** → Free plan.
3. Once it's running, open the service overview page and note:
   - **Host**
   - **Port**
   - **User** (usually `avnadmin`)
   - **Password**
   - **Database name** (default is `defaultdb` — you can rename or just use it)
   - Download the **CA certificate** (there's a download link on the same page)

### Step 2 — Load your schema into Aiven
From your own PC, with the `mysql` client installed, connect and import
(replace the placeholders with your real Aiven values):
```bash
mysql --host=YOUR_AIVEN_HOST --port=YOUR_AIVEN_PORT \
      --user=avnadmin --password \
      --ssl-ca=/path/to/downloaded/ca.pem \
      defaultdb < database/schema.sql
```
Then repeat for each of the other SQL files in the same order as before:
```bash
mysql --host=... --port=... --user=avnadmin --password --ssl-ca=ca.pem defaultdb < database/add_business_centre_types.sql
mysql --host=... --port=... --user=avnadmin --password --ssl-ca=ca.pem defaultdb < database/add_starlink_tables.sql
mysql --host=... --port=... --user=avnadmin --password --ssl-ca=ca.pem defaultdb < database/add_voucher_username.sql
mysql --host=... --port=... --user=avnadmin --password --ssl-ca=ca.pem defaultdb < database/allow_delete_used_packages_plans.sql
mysql --host=... --port=... --user=avnadmin --password --ssl-ca=ca.pem defaultdb < database/add_installation_tables.sql
mysql --host=... --port=... --user=avnadmin --password --ssl-ca=ca.pem defaultdb < database/add_inventory_tables.sql
mysql --host=... --port=... --user=avnadmin --password --ssl-ca=ca.pem defaultdb < database/add_fault_ticket_tables.sql
```

### Step 3 — Push the code to GitHub
Render deploys from a GitHub repo.
```bash
cd "rchms step2"
git init
git add .
git commit -m "Initial commit"
```
Create an empty repo on GitHub, then:
```bash
git remote add origin https://github.com/YOUR_USERNAME/rchms.git
git branch -M main
git push -u origin main
```
Because of the `.gitignore` already in this package, your real `.env`,
`venv/`, and log files won't be pushed — good, keep it that way.

### Step 4 — Create the Render web service
1. Go to https://render.com, sign up free, connect your GitHub account.
2. **New +** → **Web Service** → pick your `rchms` repo.
3. Settings:
   - **Root Directory**: `server`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn run:app --bind 0.0.0.0:$PORT --workers 3`
   - **Instance Type**: Free
   (If you kept `render.yaml`, Render can pick most of this up automatically
   when you choose "Blueprint" instead of "Web Service" — either way works.)

### Step 5 — Set environment variables on Render
In the service's **Environment** tab, add:
| Key | Value |
|---|---|
| `DB_HOST` | your Aiven host |
| `DB_PORT` | your Aiven port |
| `DB_USER` | `avnadmin` |
| `DB_PASSWORD` | your Aiven password |
| `DB_NAME` | `defaultdb` (or whatever you named it) |
| `DB_SSL_REQUIRED` | `true` |
| `SECRET_KEY` | a random string — generate with `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `DEBUG_MODE` | `false` |

Click **Deploy**. Render will build and start the app — watch the logs tab;
once it says the service is live, open the `.onrender.com` URL it gives you.

### Step 6 — Create the admin login
You don't need shell access on Render for this — just run it from your own
PC, pointed at the Aiven database. Temporarily set these in your local
`.env` (or export them in your terminal) to match your Aiven credentials,
with `DB_SSL_REQUIRED=true` and `DB_SSL_CA=/path/to/ca.pem`, then:
```bash
cd server
python setup_admin.py
```
That creates the admin account directly in the live Aiven database.
Afterwards, switch your local `.env` back to your local MySQL settings.

### Client agent — pointing it at the live server
Edit `client_agent/agent_config.json` and set `server_url` to your
`https://your-app.onrender.com` URL, then run `start_agent.bat`.

---

## Security reminders
- Never commit your real `.env` — the `.gitignore` already excludes it.
- Keep `DEBUG_MODE=false` on Render — debug mode leaks internal details
  to anyone who triggers an error.
- The Aiven CA certificate file isn't secret, but your `DB_PASSWORD` and
  `SECRET_KEY` are — only ever set those as environment variables in the
  Render dashboard, never hardcoded in the repo.
