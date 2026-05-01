# 🌿 ESG Report Analyser

AI-powered ESG screening tool built with Streamlit and Groq.

**Built by Gokul Krishna T. B.**

---

## What it does

- Upload a sustainability report PDF
- Rule-based scoring across ESG pillars, frameworks, and disclosure gaps
- CSRD / ESRS readiness scoring
- **BRSR compliance check** (India-specific — SEBI / NGRBC)
- GRI · TCFD · GHG Protocol · SDG coverage
- Greenwashing risk detection
- AI-generated executive summary via **Groq llama-3.3-70b**
- CSV exports for all outputs

---

## Setup

### 1. Clone / download this folder

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Add your Groq API key
Edit the `.env` file:
```
GROQ_API_KEY=your_groq_api_key_here
```
Get a free key at https://console.groq.com

### 4. Run
```bash
streamlit run app.py
```

---

## Tech stack

- Python · Streamlit · PyMuPDF · Pandas · Plotly · Groq SDK

---

## Important note

This is a rule-based screening tool, not a formal ESG audit or assurance opinion.
Results should be treated as indicative and reviewed by a qualified sustainability professional.
