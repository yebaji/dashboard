# NSE Dashboard

Automated daily dashboard for NSE CM bhavcopy data.  
Fetches data → processes it → publishes to GitHub Pages. Zero servers, zero cost.

---

## How it works

```
GitHub Actions (4:30 PM IST weekdays)
        │
        ▼
fetch_and_process.py   ← downloads latest bhavcopy zip from NSE archives
        │
        ▼
data.json              ← committed back to the repo
        │
        ▼
index.html             ← reads data.json, renders dashboard (GitHub Pages)
```

---

## Setup (one time, ~5 minutes)

### 1. Create a GitHub repo

Go to github.com → New repository → name it `nse-dashboard` (or anything).  
Make it **public** (required for free GitHub Pages).

### 2. Push these files

```
your-repo/
├── index.html
├── fetch_and_process.py
├── data.json              ← will be auto-generated; commit a placeholder first
└── .github/
    └── workflows/
        └── daily.yml
```

Create a placeholder `data.json`:
```bash
echo "{}" > data.json
git add . && git commit -m "init" && git push
```

### 3. Enable GitHub Pages

Repo → Settings → Pages → Source: **Deploy from branch** → Branch: `main` / `/ (root)` → Save.

Your dashboard will be live at:  
`https://<your-username>.github.io/<repo-name>/`

### 4. Enable Actions write permission

Repo → Settings → Actions → General → Workflow permissions → **Read and write** → Save.

(This lets the workflow commit `data.json` back to the repo.)

### 5. Trigger a first run

Repo → Actions → "Fetch & publish NSE bhavcopy" → **Run workflow**.

After it completes, your dashboard at the GitHub Pages URL will show live data.

---

## Schedule

The workflow runs automatically at **11:00 UTC (4:30 PM IST) Monday–Friday**,
30 minutes after NSE market close.

To run it manually at any time: Actions → Run workflow.

---

## Files

| File | Purpose |
|------|---------|
| `index.html` | The dashboard — reads `data.json` and renders all charts |
| `fetch_and_process.py` | Fetches bhavcopy from NSE, processes it, writes `data.json` |
| `data.json` | Processed market data (auto-updated daily by CI) |
| `.github/workflows/daily.yml` | GitHub Actions schedule |

---

## Local development

```bash
pip install pandas requests
python fetch_and_process.py          # writes data.json
python -m http.server 8000           # serves index.html at localhost:8000
```

Open `http://localhost:8000` in your browser.
