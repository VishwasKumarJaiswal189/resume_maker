# 📄 ATS Resume Utility

A lightweight, AI-powered ATS resume analyzer and tailoring utility built with FastAPI, React, and WeasyPrint. Paste your raw resume and a target job description to get an instant ATS match score, keyword gap analysis, and a tailored resume rendered as a live PDF and downloadable LaTeX (`.tex`) file.

### 🌐 Live Demo: **[resume-maker-ats.onrender.com](https://resume-maker-ats.onrender.com)**
*(Note: Hosted on Render's free tier—initial requests after inactivity may take ~30–50 seconds while the server wakes up.)*

---

## ✨ What It Does

- **ATS Match & Keyword Analysis:** Compares your resume against a job description to score compatibility and highlight matched vs. missing keywords.
- **Tailored Resume Generation:** Rewrites and aligns your summary, experience, projects, and skills without dropping your history, with support for custom prompt overrides (e.g., *"Strictly 1 page"*).
- **Live PDF & LaTeX Export:** Preview and download your tailored resume in **Classic**, **Modern**, or **Compact 1-Page** templates.
- **Browser Version History:** Automatically saves past generations locally in your browser (`localStorage`) with zero server-side data storage.

---

## 🛠️ Tech Stack

- **Backend:** FastAPI, Uvicorn, HTTPX, OpenRouter API
- **Frontend:** React 18 + Tailwind CSS (single-file `index.html`)
- **PDF & LaTeX Engine:** WeasyPrint + custom `.tex` generator
- **Deployment:** Docker on Render

---

## 🚀 Run Locally

```bash
# 1. Clone the repo & install Python dependencies
git clone [https://github.com/your-username/your-repo-name.git](https://github.com/your-username/your-repo-name.git)
cd your-repo-name
pip install -r requirements.txt

# 2. Add your OpenRouter API key
echo "OPENROUTER_API_KEY=sk-or-v1-your-key-here" > .env
echo "OPENROUTER_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free" >> .env

# 3. Start the server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload