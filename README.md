# ExpertBoard

A web application for expert panel review of undiagnosed disease cases, built during the **MedHack 2026-07-29** hackathon.

ExpertBoard is an experimental, standalone prototype for AI-assisted complex case review. It explores reusable expert boards organized by gene, disease, or clinical domain, with ACMG-based variant assessment and Ollama LLM integration.

---

## Key Features (MedHackathonAsia 2026-07-29/30)

### Patient & Variant Management
- Upload VCF files per patient (new patient creation or re-import for existing patients)
- Variant annotations parsed from VCF INFO column: gene, HGVS c./p., ClinVar significance, genotype, depth, in-silico scores
- Clinical free-text per patient (family history, phenotype description)

### Expert Board Workflow
- **Expert Boards**: country/specialty-based panels
- Patients assigned to a board appear in the board's **Waiting List**
- Board members managed via Admin panel

### Variant Assessment (ACMG-based)
- Add assessments per variant with ACMG/AMP 2015 criteria selection (27 criteria: PVS1, PS1–4, PM1–6, PP1–5, BA1, BS1–4, BP1–7)
- Auto-classification and evidence level computed from selected criteria (JS rules engine)
- Cross-patient review tracking ("Other pt. reviews" column, read-only)
- Composite sort: Clin. sig. > Other pt. reviews > Assessed

### AI-Assisted Analysis (Ollama)
- Configure Ollama endpoint (URL, model, API key) via **Admin → Ollama settings**
- **"✦ Analyze with AI"** — sends clinical text + VCF INFO fields to LLM
- Per-variant structured reasoning displayed in the assessment modal:
  - Patient symptoms summary
  - Gene-associated diseases
  - Relevance to patient phenotype
  - Family history interpretation
  - Assessment rationale
- **ACMG criteria suggestions** with one-click "Apply suggestions"
- **Missing data warnings**: flags annotation gaps (allele frequency, in-silico scores, de-novo status, etc.)
- Results persisted to DB (`llm_score`, `llm_reason`)

### UI / Navigation
- Sticky header with global navigation (Expert boards / Patients / Review queue / Admin)
- Role switcher dropdown (mock auth: Coordinator, Clinical Reviewer, Expert, Admin)
- Filter and search within variant tables

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, Flask 3.0.3 |
| ORM | SQLAlchemy 2.0 |
| Database | MySQL 8.4 (Docker) |
| LLM | Ollama (OpenAI-compatible API) |
| Frontend | Vanilla HTML/CSS/JS |
| Container | Docker Compose |

---

## Quick Start

- Install Docker Desktop or Docker Engine.
- Start Docker locally before running the development environment.
- Make sure ports `8010` and `13307` are available, or change them in `.env`.

## Local development

```bash
git clone https://github.com/PubCaseFinder/expertboard.git
cd expertboard
cp .env.example .env
docker compose up -d --build
```

Open:

```text
http://localhost:8010/boards
```

Create the first demo board room from the landing page.

## MVP scope

- Expert board list and demo board creation
- Case review rooms under a fixed expert board
- Review room with left-side workspace navigation
- Core board roles and optional support roles
- Phenotype, variant, hypothesis, evidence, history, and briefing views
- MySQL-backed case, member, comment, decision, and audit log tables
- PubCaseFinder API client placeholder via `PUBCASEFINDER_BASE_URL`

## Role model

Core board:

- Case chair
- Clinical reviewer
- Bioinformatician
- Laboratory scientist
- Genetic counselor

Optional support:

- Case coordinator
- External consultant
