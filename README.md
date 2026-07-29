# ExpertBoard

ExpertBoard is an experimental, standalone prototype for AI-assisted complex case review.

It explores reusable expert boards organized by gene, disease, or clinical domain. Each board can open case-specific review rooms where multidisciplinary experts review evidence, record positions, track consensus, and keep final decisions human-governed.

## Prerequisites

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
