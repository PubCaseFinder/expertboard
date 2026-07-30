# Developer Log — ExpertBoard

**Hackathon:** [MedHackathon Asia 2026](https://medhackathon.github.io/2026/)  
**Hackathon period:** 2026-07-27 – 2026-07-30  
**Coding days:** 2026-07-29 – 2026-07-30 (2 days)  
**Developer:** Yuko Kitano  
**AI coding assistant:** GitHub Copilot (approx. $50 credit used over the 2 coding days)

---

## What I Built

ExpertBoard is a web application designed to support **multidisciplinary expert panel review** for undiagnosed disease genomic cases. The core idea: give rare disease experts a shared workspace where they can review patient VCF variants, apply structured ACMG assessments, and get AI-assisted reasoning to guide their decisions.

---

## How To Use

### 1. Setup

```bash
cp .env.example .env   # configure DB credentials
sudo docker compose up -d
open http://localhost:8010
```

### 2. Configure AI (Admin → Ollama settings)

An API key / endpoint is required to use the AI analysis feature.

- Go to **Admin** → **Ollama settings**
- Enter your Ollama **Base URL**, **Model name**, and **API Key**

> ⚠️ **Important — Patient Data Security**
>
> During this hackathon, all testing was done with **AI-generated dummy data**.
> The online version of **Gemma 4 via Ollama** was used for development.
>
> **Real patient data and real variants must NEVER be sent to an internet-connected AI service.**
> This is a fundamental patient rights and privacy requirement.
> If you use this application with real clinical data, you must use a **local LLM**
> (e.g. Ollama running on-premises) or another solution where data never leaves your secure environment.

### 3. Prepare annotated VCF

The AI reads the **clinical notes** and the **VCF INFO field** for each variant.
The system prompt sent to the LLM is:

```
You are an expert clinical geneticist specializing in rare and undiagnosed diseases.
You will receive a patient's clinical description (including family history if available)
and a list of genetic variants with annotation data from VCF INFO fields.

For each variant, perform the following analysis and return a structured JSON response.
Return ONLY a valid JSON array — no markdown, no text outside the array.

== Analysis tasks ==
1. Reason through five clinical points (see fields below).
2. Recommend ACMG/AMP 2015 criteria that are SUPPORTED by available data.
   Pathogenic evidence: PVS1, PS1, PS2, PS3, PS4, PM1, PM2, PM3, PM4, PM5, PM6, PP1, PP2, PP3, PP4, PP5
   Benign evidence: BA1, BS1, BS2, BS3, BS4, BP1, BP2, BP3, BP4, BP5, BP6, BP7
3. Identify criteria that CANNOT be evaluated due to missing annotation data,
   and state exactly what data is needed.
   Common missing items: population allele frequency (PM2/BA1/BS1), in-silico scores
   like CADD/SIFT/PolyPhen (PP3/BP4), de novo status (PS2/PM6), segregation data (PP1/BS4),
   functional studies (PS3/BS3), phasing information (PM3/BP2), ClinVar evidence (PS1/PP5/BP6).

== Output format ==
[
  {
    "id": <variant_id_integer>,
    "patient_symptoms": "<2-3 sentences>",
    "gene_diseases": "<2-3 sentences>",
    "relevance": "<2-3 sentences>",
    "family_history": "<1-2 sentences>",
    "score_rationale": "<1-2 sentences>",
    "suggested_acmg": ["<code>", ...],
    "missing_data": ["<CriterionCode>: <what is missing>"],
    "score": <integer 0-10>
  }
]
```

Therefore, **VCF files should be annotated with VEP or a similar tool** to include fields needed for ACMG classification (population allele frequency, in-silico prediction scores, ClinVar evidence, etc.).

For this hackathon, an AI-generated dummy VCF was annotated with VEP before import.

---

## Feature Overview

### Patient Registration

Upload a patient's **VCF file** and **clinical notes** (free text including symptoms, family history, diagnosis). This becomes the main review page for board members. Board members use this page to read variant annotations, add ACMG-based assessments, and view AI reasoning.

### Board (Expert Board)

> ⚠️ **This feature is a partial / prototype implementation.**

The intended design: create clinician and bioinformatician users, assign them to a board (by country or specialty), and route patients to that board for review. Board members would then evaluate variants assigned to them.

In the current implementation, this part is **not working correctly**. For the hackathon, a simple role switcher is placed at the top of the page to quickly swap between user roles. However, role-based access control — controlling which fields each role can edit — was **not completed**.

In a production implementation, each role (coordinator, clinical reviewer, expert, bioinformatician) would need fine-grained permission control over which actions and data fields they can view or modify.

### Review Queue

Shows the current review status of all patients across the review lifecycle (pending → in review → completed). Gives coordinators an overview of workload and progress.

### Admin

- Add and manage users (name, role)
- Configure AI settings: Ollama Base URL, Model, API Key
- Manage Expert Board members

---

## Development Notes

- **Coding assistant:** GitHub Copilot — used throughout for code generation, debugging, and refactoring. Approx. $50 in API credits over 2 days.
- **Test data:** AI-generated synthetic VCF (HCM phenotype) annotated with VEP
- **LLM used for testing:** Gemma 4 via Ollama online endpoint
- Schema migrations run automatically on startup via `admin.ensure_schema()` — no migration framework needed for hackathon iteration speed
- No real authentication — role switcher is a mock placeholder

---

## Thank You 🙏

This project would not have been possible without the support, ideas, and collaboration of:

**Rutharr**-san, **Francis**-san, **Pierre-Alexis**-san, **Piyakrit**-san 

And to all organizers of **MedHackathon Asia 2026** — thank you for creating such a wonderful and inspiring environment. Hope to see you all again next time! 🌏


