import json
import os
import re
from pathlib import Path
from typing import Dict

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
from weasyprint import HTML

load_dotenv()

app = FastAPI(title="Local ATS Resume Utility")

# --- ENVIRONMENT CONFIGURATION ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class AnalyzeRequest(BaseModel):
    resume_text: str
    job_description: str
    extra_instructions: str = ""
    template_id: str = "classic"


class RenderPdfRequest(BaseModel):
    structured_resume: Dict
    template_id: str = "classic"


def escape_latex(text: str) -> str:
    if not text:
        return ""
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    pattern = re.compile("|".join(re.escape(k) for k in replacements.keys()))
    return pattern.sub(lambda m: replacements[m.group(0)], text)


def escape_html(text: str) -> str:
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def extract_first_json_object(text: str) -> Dict:
    """Safely extracts and parses the first complete JSON object, ignoring trailing text."""
    start = text.find("{")
    if start == -1:
        raise ValueError(f"No JSON object found in output: {text[:300]}")
    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(text, start)
    if not isinstance(obj, dict):
        raise ValueError("Parsed JSON root is not a dictionary.")
    return obj


def build_latex(data: Dict, template_id: str) -> str:
    name = escape_latex(data.get("name", "Your Name"))
    contact = escape_latex(data.get("contact", "Email | Phone | Location | LinkedIn"))
    summary = escape_latex(data.get("summary", ""))
    skills = escape_latex(data.get("skills", ""))

    edu_blocks = []
    for item in data.get("education", []):
        deg = escape_latex(item.get("degree", ""))
        school = escape_latex(item.get("school", ""))
        dates = escape_latex(item.get("dates", ""))
        edu_blocks.append(f"\\textbf{{{deg}}}, {school} \\hfill \\textit{{{dates}}}\\\\")
    education_tex = "\n".join(edu_blocks)

    exp_blocks = []
    for item in data.get("experience", []):
        role = escape_latex(item.get("role", ""))
        company = escape_latex(item.get("company", ""))
        dates = escape_latex(item.get("dates", ""))
        bullets = "\n".join(
            f"  \\item {escape_latex(b)}" for b in item.get("bullets", []) if b.strip()
        )
        exp_blocks.append(
            f"\\textbf{{{role}}} --- {company} \\hfill \\textit{{{dates}}}\\\\\n"
            f"\\begin{{itemize}}[leftmargin=1.2em, itemsep=1pt, topsep=2pt]\n{bullets}\n\\end{{itemize}}"
        )
    experience_tex = "\n\\vspace{4pt}\n".join(exp_blocks)

    proj_blocks = []
    for item in data.get("projects", []):
        pname = escape_latex(item.get("name", ""))
        tech = escape_latex(item.get("tech", ""))
        dates = escape_latex(item.get("dates", ""))
        bullets = "\n".join(
            f"  \\item {escape_latex(b)}" for b in item.get("bullets", []) if b.strip()
        )
        header = f"\\textbf{{{pname}}}" + (f" --- \\textit{{{tech}}}" if tech else "")
        proj_blocks.append(
            f"{header} \\hfill \\textit{{{dates}}}\\\\\n"
            f"\\begin{{itemize}}[leftmargin=1.2em, itemsep=1pt, topsep=2pt]\n{bullets}\n\\end{{itemize}}"
        )
    projects_tex = "\n\\vspace{4pt}\n".join(proj_blocks)

    certs = [escape_latex(c) for c in data.get("certifications", []) if c.strip()]
    cert_section_tex = ""
    if certs:
        cert_items = "\n".join(f"  \\item {c}" for c in certs)
        cert_section_tex = (
            "\\section*{Certifications}\n"
            f"\\begin{{itemize}}[leftmargin=1.2em, itemsep=1pt, topsep=2pt]\n{cert_items}\n\\end{{itemize}}"
        )

    projects_section_tex = f"\\section*{{Projects}}\n{projects_tex}" if projects_tex else ""

    if template_id == "modern":
        return rf"""\documentclass[10pt,letterpaper]{{article}}
\usepackage[margin=0.6in]{{geometry}}
\usepackage[T1]{{fontenc}}
\usepackage{{lmodern}}
\usepackage{{enumitem}}
\usepackage{{xcolor}}
\usepackage{{titlesec}}
\definecolor{{accent}}{{RGB}}{{25, 65, 120}}
\titleformat{{\section}}{{\large\bfseries\sffamily\color{{accent}}}}{{}}{{0em}}{{}}[\titlerule]
\titlespacing*{{\section}}{{0pt}}{{8pt}}{{4pt}}
\pagestyle{{empty}}
\begin{{document}}
\begin{{center}}
    {{\LARGE\bfseries\sffamily\color{{accent}} {name}}} \\[3pt]
    {{\small\sffamily {contact}}}
\end{{center}}
\section*{{Summary}}
{summary}
\section*{{Education}}
{education_tex}
\section*{{Experience}}
{experience_tex}
{projects_section_tex}
\section*{{Technical Skills}}
{skills}
{cert_section_tex}
\end{{document}}"""

    elif template_id == "compact":
        return rf"""\documentclass[9.5pt,letterpaper]{{article}}
\usepackage[margin=0.45in]{{geometry}}
\usepackage{{enumitem}}
\usepackage{{titlesec}}
\titleformat{{\section}}{{\normalsize\bfseries\uppercase}}{{}}{{0em}}{{}}[\hrule]
\titlespacing*{{\section}}{{0pt}}{{6pt}}{{3pt}}
\pagestyle{{empty}}
\begin{{document}}
\noindent{{\Large\bfseries {name}}} \hfill {{\small {contact}}}
\vspace{{4pt}}\hrule
\section*{{Summary}}
{summary}
\section*{{Education}}
{education_tex}
\section*{{Experience}}
{experience_tex}
{projects_section_tex}
\section*{{Core Skills}}
{skills}
{cert_section_tex}
\end{{document}}"""

    return rf"""\documentclass[10.5pt,letterpaper]{{article}}
\usepackage[margin=0.65in]{{geometry}}
\usepackage{{enumitem}}
\usepackage{{titlesec}}
\titleformat{{\section}}{{\large\bfseries}}{{}}{{0em}}{{}}[\titlerule]
\titlespacing*{{\section}}{{0pt}}{{8pt}}{{4pt}}
\pagestyle{{empty}}
\begin{{document}}
\begin{{center}}
    {{\LARGE\bfseries {name}}} \\[2pt]
    {{\small {contact}}}
\end{{center}}
\section*{{Professional Summary}}
{summary}
\section*{{Education}}
{education_tex}
\section*{{Experience}}
{experience_tex}
{projects_section_tex}
\section*{{Technical Skills}}
{skills}
{cert_section_tex}
\end{{document}}"""


def build_pdf_html(data: Dict, template_id: str) -> str:
    name = escape_html(data.get("name", "Your Name"))
    contact = escape_html(data.get("contact", "Email | Phone | Location | LinkedIn"))
    summary = escape_html(data.get("summary", ""))
    skills = escape_html(data.get("skills", ""))

    edu_html = ""
    for item in data.get("education", []):
        deg = escape_html(item.get("degree", ""))
        school = escape_html(item.get("school", ""))
        dates = escape_html(item.get("dates", ""))
        edu_html += f"""
        <div class="row-header">
            <span><strong>{deg}</strong>, {school}</span>
            <span class="dates">{dates}</span>
        </div>
        """

    exp_html = ""
    for item in data.get("experience", []):
        role = escape_html(item.get("role", ""))
        company = escape_html(item.get("company", ""))
        dates = escape_html(item.get("dates", ""))
        bullets = "".join(
            f"<li>{escape_html(b)}</li>" for b in item.get("bullets", []) if b.strip()
        )
        exp_html += f"""
        <div class="exp-item">
            <div class="row-header">
                <span><strong>{role}</strong> &mdash; {company}</span>
                <span class="dates">{dates}</span>
            </div>
            <ul>{bullets}</ul>
        </div>
        """

    proj_html = ""
    for item in data.get("projects", []):
        pname = escape_html(item.get("name", ""))
        tech = escape_html(item.get("tech", ""))
        dates = escape_html(item.get("dates", ""))
        bullets = "".join(
            f"<li>{escape_html(b)}</li>" for b in item.get("bullets", []) if b.strip()
        )
        title_line = f"<strong>{pname}</strong>" + (f" &mdash; <em>{tech}</em>" if tech else "")
        proj_html += f"""
        <div class="exp-item">
            <div class="row-header">
                <span>{title_line}</span>
                <span class="dates">{dates}</span>
            </div>
            <ul>{bullets}</ul>
        </div>
        """

    certs = [escape_html(c) for c in data.get("certifications", []) if c.strip()]
    cert_html = f"<ul>{''.join(f'<li>{c}</li>' for c in certs)}</ul>" if certs else ""

    # Exact section order: Summary -> Education -> Experience -> Projects -> Skills -> Certifications (if exist)
    section_order = [
        ("Professional Summary", f"<div>{summary}</div>" if summary else ""),
        ("Education", edu_html),
        ("Experience", exp_html),
        ("Projects", proj_html),
        ("Technical Skills", f"<div>{skills}</div>" if skills else ""),
        ("Certifications", cert_html),
    ]
    ordered_sections = "\n".join(
        f"<h2>{title}</h2>\n{content}" for title, content in section_order if content.strip()
    )

    if template_id == "modern":
        css = """
        @page { size: letter; margin: 0.55in; }
        body { font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 10pt; color: #1e293b; line-height: 1.38; }
        .header { text-align: center; margin-bottom: 10px; }
        .name { font-size: 20pt; font-weight: 700; color: #194178; margin: 0; }
        .contact { font-size: 9pt; color: #475569; margin-top: 3px; }
        h2 { font-size: 11pt; font-weight: 700; color: #194178; border-bottom: 1.5px solid #194178; padding-bottom: 2px; margin: 10px 0 5px 0; }
        .row-header { display: flex; justify-content: space-between; font-size: 10pt; }
        .dates { font-style: italic; color: #475569; font-size: 9pt; }
        ul { margin: 3px 0 7px 18px; padding: 0; }
        li { margin-bottom: 2px; }
        """
    elif template_id == "compact":
        css = """
        @page { size: letter; margin: 0.42in; }
        body { font-family: Georgia, 'Times New Roman', serif; font-size: 9.2pt; color: #000; line-height: 1.3; }
        .header { display: flex; justify-content: space-between; align-items: baseline; border-bottom: 1.5px solid #000; padding-bottom: 4px; margin-bottom: 6px; }
        .name { font-size: 16pt; font-weight: bold; }
        .contact { font-size: 8.5pt; }
        h2 { font-size: 9.8pt; font-weight: bold; text-transform: uppercase; border-bottom: 1px solid #000; margin: 7px 0 4px 0; padding-bottom: 1px; }
        .row-header { display: flex; justify-content: space-between; }
        .dates { font-style: italic; font-size: 8.8pt; }
        ul { margin: 2px 0 5px 16px; padding: 0; }
        li { margin-bottom: 1.5px; }
        """
    else:
        css = """
        @page { size: letter; margin: 0.6in; }
        body { font-family: 'Times New Roman', Georgia, serif; font-size: 10.5pt; color: #000; line-height: 1.38; }
        .header { text-align: center; margin-bottom: 10px; }
        .name { font-size: 20pt; font-weight: bold; margin: 0; }
        .contact { font-size: 9.5pt; margin-top: 2px; }
        h2 { font-size: 11.5pt; font-weight: bold; border-bottom: 1px solid #000; padding-bottom: 2px; margin: 10px 0 5px 0; }
        .row-header { display: flex; justify-content: space-between; }
        .dates { font-style: italic; font-size: 9.5pt; }
        ul { margin: 3px 0 7px 18px; padding: 0; }
        li { margin-bottom: 2px; }
        """

    return f"""<!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"><style>{css}</style></head>
    <body>
        <div class="header">
            <div class="name">{name}</div>
            <div class="contact">{contact}</div>
        </div>
        {ordered_sections}
    </body>
    </html>"""


@app.get("/", response_class=HTMLResponse)
def serve_ui():
    return Path("index.html").read_text(encoding="utf-8")


@app.get("/api/config")
def get_config():
    load_dotenv(override=True)
    return {"active_model": os.getenv("OPENROUTER_MODEL", OPENROUTER_MODEL)}


@app.post("/api/analyze")
async def analyze_and_tailor(req: AnalyzeRequest):
    load_dotenv(override=True)
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    model = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")

    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="OPENROUTER_API_KEY is not set in .env.",
        )

    is_compact = (
        req.template_id == "compact"
        or any(
            w in req.extra_instructions.lower()
            for w in ["compact", "concise", "short", "brief", "1 page", "one page", "1-page"]
        )
    )

    length_rules = (
        "2. Write a tight, punchy 2-sentence professional summary (max 35 words).\n"
        "3. Write 2-3 concise, high-impact bullet points per experience and project entry (strictly 12-16 words per bullet, 1 line each) using strong action verbs and quantified metrics.\n"
        "4. Keep the skills list compact and grouped on 1-2 lines, including only the highest-priority JD keywords.\n"
        if is_compact
        else
        "2. Write a rich 3-4 sentence professional summary tailored to the target role.\n"
        "3. Write 3-5 detailed, high-impact bullet points per experience and project entry (20-30 words per bullet) using strong action verbs, technical specifics, and quantified metrics.\n"
        "4. Include a comprehensive, thorough comma-separated skills list integrating relevant keywords from the job description.\n"
    )

    system_prompt = (
        "You are an expert ATS resume writer and optimizer. Analyze the pasted resume against the target job description "
        "and produce a tailored resume.\n"
        "CRITICAL RULES:\n"
        "1. By default, include all roles, internships, academic/personal projects, certifications, and education entries from the raw resume—UNLESS EXTRA USER INSTRUCTIONS tell you to omit, limit, or select specific items.\n"
        f"{length_rules}"
        "5. If the candidate has certifications in the raw resume, include them in 'certifications'; otherwise return an empty list [].\n"
        "6. EXTRA USER INSTRUCTIONS OVERRIDE ALL DEFAULTS ABOVE. Follow them strictly.\n"
        "7. Output ONLY a single valid JSON object with no trailing commentary or markdown fences, matching this exact schema:\n"
        "{\n"
        '  "ats_score": 85,\n'
        '  "matched_keywords": ["Python", "FastAPI"],\n'
        '  "missing_keywords": ["Kubernetes", "CI/CD"],\n'
        '  "suggestions": ["Actionable improvement 1", "Actionable improvement 2"],\n'
        '  "structured_resume": {\n'
        '    "name": "Full Name",\n'
        '    "contact": "email@example.com | 555-0100 | City, State | LinkedIn/GitHub",\n'
        '    "summary": "Tailored professional summary...",\n'
        '    "education": [\n'
        '      {"degree": "Degree Name", "school": "University", "dates": "Year"}\n'
        "    ],\n"
        '    "experience": [\n'
        '      {"role": "Title", "company": "Company", "dates": "2022 - Present", "bullets": ["Bullet 1", "Bullet 2"]}\n'
        "    ],\n"
        '    "projects": [\n'
        '      {"name": "Project Name (Personal or Academic)", "tech": "Python, FastAPI", "dates": "2024", "bullets": ["Bullet 1", "Bullet 2"]}\n'
        "    ],\n"
        '    "skills": "Technical skills aligned with JD",\n'
        '    "certifications": ["Certification Name (Year)"]\n'
        "  }\n"
        "}"
    )

    extra_block = (
        f"\n\nEXTRA USER INSTRUCTIONS (MUST FOLLOW — OVERRIDES DEFAULTS):\n{req.extra_instructions.strip()}"
        if req.extra_instructions.strip()
        else ""
    )
    user_prompt = (
        f"RAW RESUME:\n{req.resume_text}\n\n"
        f"TARGET JOB DESCRIPTION:\n{req.job_description}"
        f"{extra_block}"
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.25,
        "max_tokens": 8192,
        "reasoning": {"effort": "none"},
    }

    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(OPENROUTER_URL, headers=headers, json=payload)
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"OpenRouter error ({model}): {resp.text}")

        resp_data = resp.json()
        choices = resp_data.get("choices") or []
        if not choices:
            raise HTTPException(status_code=502, detail=f"Empty response from {model}: {resp_data}")

        message = choices[0].get("message") or {}
        raw_content = (message.get("content") or message.get("reasoning") or "").strip()
        if not raw_content:
            raise HTTPException(
                status_code=502,
                detail=f"Model {model} returned empty content (finish_reason={choices[0].get('finish_reason')}). Switch OPENROUTER_MODEL in .env.",
            )

    try:
        parsed = extract_first_json_object(raw_content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse model JSON: {e}")

    structured = parsed.get("structured_resume", {})
    parsed["latex_code"] = build_latex(structured, req.template_id)
    parsed["model_used"] = model
    return parsed


@app.post("/api/render-pdf")
def render_pdf(req: RenderPdfRequest):
    html_str = build_pdf_html(req.structured_resume, req.template_id)
    pdf_bytes = HTML(string=html_str).write_pdf()
    return Response(content=pdf_bytes, media_type="application/pdf")


@app.post("/api/render-latex")
def render_latex(req: RenderPdfRequest):
    return {"latex_code": build_latex(req.structured_resume, req.template_id)}