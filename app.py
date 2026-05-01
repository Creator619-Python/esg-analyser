import re
import os
import json
import fitz
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from groq import Groq
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ESG Report Analyser",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;600;700;800&display=swap');

html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }

.stApp {
    background: linear-gradient(135deg, #071313 0%, #0b1720 50%, #081411 100%);
    color: #f8fafc;
}
section[data-testid="stSidebar"] {
    background: #0b1220;
    border-right: 1px solid rgba(148,163,184,0.15);
}
.block-container { padding-top: 1.5rem; padding-bottom: 3rem; }

.hero {
    padding: 32px 36px 28px;
    border-radius: 24px;
    background: radial-gradient(circle at top right, rgba(16,185,129,.25), transparent 35%),
                linear-gradient(135deg, rgba(15,23,42,.98), rgba(8,47,73,.85));
    border: 1px solid rgba(148,163,184,0.18);
    box-shadow: 0 24px 80px rgba(0,0,0,.3);
    margin-bottom: 24px;
}
.hero h1 { font-size: 40px; font-weight: 900; line-height: 1.05; margin: 0 0 10px 0; color: #f8fafc; }
.hero p  { color: #cbd5e1; font-size: 15px; margin: 0; max-width: 860px; line-height: 1.6; }
.tag {
    display: inline-block; margin: 14px 6px 0 0; padding: 5px 12px;
    border-radius: 999px; background: rgba(16,185,129,.1);
    border: 1px solid rgba(16,185,129,.25); color: #a7f3d0;
    font-size: 11px; font-weight: 700; letter-spacing: .03em;
}

.metric-card {
    padding: 22px 24px; border-radius: 20px;
    background: rgba(15,23,42,0.82);
    border: 1px solid rgba(148,163,184,0.15);
    box-shadow: 0 14px 40px rgba(0,0,0,.22);
    min-height: 130px;
}
.metric-label { color: #94a3b8; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; margin-bottom: 8px; }
.metric-value { font-size: 34px; font-weight: 900; line-height: 1; }
.metric-note  { color: #cbd5e1; font-size: 12px; margin-top: 10px; }

.panel {
    padding: 22px 24px; border-radius: 20px;
    background: rgba(15,23,42,0.78);
    border: 1px solid rgba(148,163,184,0.15);
    box-shadow: 0 14px 40px rgba(0,0,0,.2);
    margin-bottom: 18px;
}
.panel-title { color: #f8fafc; font-size: 17px; font-weight: 800; margin-bottom: 12px; }
.small-muted  { color: #cbd5e1; font-size: 14px; line-height: 1.75; }

.footer {
    margin-top: 48px; padding: 20px 0; text-align: center;
    border-top: 1px solid rgba(148,163,184,0.1);
    color: #475569; font-size: 13px;
}
</style>
""", unsafe_allow_html=True)

# ── Knowledge bases ───────────────────────────────────────────────────────────
FRAMEWORK_KEYWORDS = {
    "GRI": [
        "gri", "material topics", "stakeholder engagement", "general disclosures",
        "management approach", "content index", "materiality", "disclosure",
    ],
    "ESRS / CSRD": [
        "esrs", "csrd", "double materiality", "impact materiality", "financial materiality",
        "value chain", "e1", "s1", "g1", "sustainability statement",
    ],
    "TCFD": [
        "tcfd", "scenario analysis", "climate risk", "governance", "strategy",
        "risk management", "metrics and targets", "physical risk", "transition risk",
    ],
    "GHG Protocol": [
        "ghg protocol", "scope 1", "scope 2", "scope 3", "greenhouse gas",
        "emissions", "market-based", "location-based", "carbon dioxide equivalent", "co2e",
    ],
    "SDGs": [
        "sdg", "sustainable development goals", "un global compact",
        "sdg 13", "sdg 12", "sdg 8", "sdg 5",
    ],
    "BRSR": [
        "brsr", "business responsibility", "sustainability reporting", "sebi",
        "ngrbc", "national guidelines", "principle 6", "esg india",
        "extended producer responsibility", "epr",
    ],
}

ESG_PILLARS = {
    "Environment": [
        "emissions", "energy", "renewable", "water", "waste", "biodiversity",
        "pollution", "recycling", "resource efficiency", "climate",
    ],
    "Social": [
        "employees", "health and safety", "diversity", "inclusion", "human rights",
        "labour", "training", "community", "equity", "wellbeing",
    ],
    "Governance": [
        "board", "ethics", "anti-corruption", "compliance", "whistleblowing",
        "risk committee", "remuneration", "audit", "policy", "oversight",
    ],
    "Climate Risk": [
        "net zero", "transition plan", "1.5", "science-based", "scenario analysis",
        "climate risk", "physical risk", "transition risk", "carbon price", "decarbonisation",
    ],
    "Supply Chain": [
        "supplier", "supply chain", "procurement", "value chain", "due diligence",
        "supplier code", "category 1", "category 11", "category 15", "scope 3",
    ],
}

GAP_CHECKS = [
    ("Scope 3 data incomplete",          "scope 3",         "High",   "Disclose material Scope 3 categories, calculation method, boundary, and assumptions."),
    ("Double materiality missing",        "double materiality","High", "Add impact and financial materiality assessment with stakeholder input and methodology."),
    ("Climate transition plan missing",   "transition plan", "Medium", "Explain how climate targets will be achieved through CAPEX, operations, and accountable owners."),
    ("Interim climate targets missing",   "2030",            "Medium", "Add near-term targets, not only long-term net-zero ambition."),
    ("Human rights due diligence limited","human rights",    "Medium", "Explain due diligence process, salient risks, findings, and remediation actions."),
    ("Governance oversight not clear",    "board oversight", "Medium", "Clarify board/committee responsibilities for sustainability and climate risk."),
    ("Biodiversity assessment missing",   "biodiversity",    "Low",    "Assess biodiversity impacts, dependencies, locations, and mitigation actions where material."),
    ("BRSR disclosures absent",           "brsr",            "High",   "Indian-listed companies must file BRSR with SEBI. Add NGRBC principle-wise disclosures."),
    ("Water stewardship data missing",    "water withdrawal","Medium", "Report water withdrawal, consumption, and recycling volumes with source breakdown."),
    ("Waste management data missing",     "waste generated", "Medium", "Disclose total waste generated, diverted from disposal, and directed to disposal by category."),
]

GREENWASHING_TERMS = [
    "eco-friendly", "environmentally friendly", "carbon neutral", "climate neutral",
    "net zero", "green product", "best-in-class", "industry leading",
    "most sustainable", "climate positive", "zero impact", "nature positive",
    "100% renewable", "fully sustainable", "zero carbon",
]

EVIDENCE_TERMS = [
    "%", "tonnes", "tco2e", "co2e", "scope 1", "scope 2", "scope 3",
    "baseline", "verified", "assurance", "certified", "iso", "sbti",
    "methodology", "audit", "limited assurance", "reasonable assurance",
]

ESRS_TOPICS = {
    "ESRS E1 – Climate Change":          ["climate", "emissions", "scope 1", "scope 2", "scope 3", "transition plan"],
    "ESRS E2 – Pollution":               ["pollution", "air emissions", "water pollution", "hazardous"],
    "ESRS E3 – Water & Marine":          ["water", "water withdrawal", "water consumption", "marine"],
    "ESRS E4 – Biodiversity":            ["biodiversity", "ecosystem", "habitat", "nature"],
    "ESRS E5 – Circular Economy":        ["circular", "recycling", "waste", "resource use"],
    "ESRS S1 – Own Workforce":           ["employees", "workforce", "health and safety", "training", "diversity"],
    "ESRS S2 – Value Chain Workers":     ["value chain workers", "supplier workers", "labour rights"],
    "ESRS S3 – Affected Communities":    ["communities", "affected communities", "local community"],
    "ESRS S4 – Consumers & End-users":   ["consumers", "end-users", "customer safety", "privacy"],
    "ESRS G1 – Business Conduct":        ["anti-corruption", "ethics", "whistleblowing", "business conduct"],
}

BRSR_PRINCIPLES = {
    "P1 – Ethics & Transparency":        ["ethics", "anti-corruption", "transparency", "integrity", "whistleblowing"],
    "P2 – Sustainable Products":         ["sustainable product", "product lifecycle", "extended producer", "epr"],
    "P3 – Employee Wellbeing":           ["employee wellbeing", "health and safety", "training", "skill development"],
    "P4 – Stakeholder Engagement":       ["stakeholder", "community engagement", "grievance", "consultation"],
    "P5 – Human Rights":                 ["human rights", "child labour", "forced labour", "equal remuneration"],
    "P6 – Environment":                  ["emissions", "energy", "water", "waste", "biodiversity", "scope 1", "scope 2"],
    "P7 – Policy Advocacy":              ["policy advocacy", "industry association", "lobbying", "trade body"],
    "P8 – Inclusive Growth":             ["csr", "social impact", "inclusive growth", "community development"],
    "P9 – Customer Value":               ["customer", "product safety", "data privacy", "consumer complaint"],
}

# ── GRI Standards Knowledge Base ─────────────────────────────────────────────
# Universal Standards
GRI_UNIVERSAL = {
    "GRI 1 – Foundation 2021": {
        "keywords": ["gri 1", "gri foundation", "reporting principles", "due diligence", "material topics"],
        "disclosures": {
            "1-1 Reporting principles":       ["accuracy", "balance", "clarity", "comparability", "completeness", "sustainability context", "timeliness", "verifiability"],
            "1-2 Reporting with GRI Standards":["gri standards", "claim", "accordance", "reference"],
        }
    },
    "GRI 2 – General Disclosures 2021": {
        "keywords": ["gri 2", "general disclosures", "organizational profile", "governance", "stakeholder engagement", "reporting practice"],
        "disclosures": {
            "2-1 Organizational details":     ["legal name", "ownership", "headquarters", "countries of operation"],
            "2-2 Entities in report":         ["subsidiaries", "joint ventures", "consolidated", "reporting boundary"],
            "2-3 Reporting period":           ["reporting period", "fiscal year", "publication date"],
            "2-4 Restatements":               ["restatement", "recalculation", "prior period"],
            "2-5 External assurance":         ["external assurance", "third-party assurance", "limited assurance", "reasonable assurance", "verified"],
            "2-6 Activities & value chain":   ["value chain", "products and services", "markets served", "supply chain"],
            "2-7 Employees":                  ["total employees", "full-time", "part-time", "permanent", "temporary", "employee breakdown"],
            "2-8 Workers not employees":      ["contract workers", "self-employed", "non-employee workers"],
            "2-9 Governance structure":       ["board of directors", "governance structure", "committee", "oversight"],
            "2-10 Nomination of board":       ["nomination", "selection criteria", "board diversity"],
            "2-11 Chair of board":            ["chair", "chairperson", "board chair"],
            "2-12 Board ESG oversight":       ["board oversight", "esg oversight", "sustainability governance"],
            "2-13 Delegation of responsibility":["delegation", "responsible individual", "senior executive"],
            "2-14 Board sustainability role": ["board role", "sustainability report approval"],
            "2-15 Conflicts of interest":     ["conflict of interest", "related party"],
            "2-16 Communication of concerns": ["concerns", "reporting concerns", "speak up"],
            "2-17 Knowledge of board":        ["board competency", "esg knowledge", "board training"],
            "2-18 Board performance":         ["board evaluation", "performance assessment"],
            "2-19 Remuneration policies":     ["remuneration", "compensation policy", "pay policy"],
            "2-20 Remuneration process":      ["remuneration process", "say on pay", "compensation committee"],
            "2-21 Annual total compensation": ["ceo pay ratio", "total compensation ratio", "pay gap"],
            "2-22 Statement on strategy":     ["ceo statement", "strategy statement", "sustainability strategy"],
            "2-23 Policy commitments":        ["policy commitments", "human rights policy", "code of conduct"],
            "2-24 Embedding policy":          ["embedding", "policy implementation", "integration"],
            "2-25 Remediation processes":     ["remediation", "grievance mechanism", "remedy"],
            "2-26 Mechanisms for seeking advice":["ethics hotline", "advice mechanism", "helpline"],
            "2-27 Compliance with laws":      ["compliance", "violations", "fines", "penalties", "non-compliance"],
            "2-28 Membership associations":   ["membership", "industry association", "trade association"],
            "2-29 Approach to stakeholder engagement":["stakeholder engagement", "stakeholder identification", "engagement approach"],
            "2-30 Collective bargaining":     ["collective bargaining", "trade union", "works council"],
        }
    },
    "GRI 3 – Material Topics 2021": {
        "keywords": ["gri 3", "material topics", "materiality assessment", "double materiality", "impact assessment"],
        "disclosures": {
            "3-1 Process to determine material topics": ["materiality process", "materiality assessment", "impact identification"],
            "3-2 List of material topics":              ["material topics list", "material issues", "priority topics"],
            "3-3 Management of material topics":        ["management approach", "policies", "commitments", "goals", "targets"],
        }
    },
}

# Economic Standards (GRI 200)
GRI_200 = {
    "GRI 201 – Economic Performance": {
        "keywords": ["gri 201", "economic performance", "direct economic value", "financial implications", "climate risk financial"],
        "disclosures": {
            "201-1 Direct economic value":     ["direct economic value", "revenue", "operating costs", "employee wages", "community investment"],
            "201-2 Climate financial risks":   ["financial implications", "climate risk", "physical risk financial", "transition risk financial"],
            "201-3 Pension obligations":       ["pension", "retirement plan", "defined benefit"],
            "201-4 Government assistance":     ["government assistance", "subsidies", "tax relief", "grants"],
        }
    },
    "GRI 202 – Market Presence": {
        "keywords": ["gri 202", "market presence", "local minimum wage", "senior management local"],
        "disclosures": {
            "202-1 Minimum wage ratio":        ["minimum wage", "entry level wage", "local wage"],
            "202-2 Local senior management":   ["local senior management", "locally hired"],
        }
    },
    "GRI 203 – Indirect Economic Impacts": {
        "keywords": ["gri 203", "indirect economic", "infrastructure investment", "significant indirect"],
        "disclosures": {
            "203-1 Infrastructure investment": ["infrastructure investment", "services supported", "commercial development"],
            "203-2 Significant indirect impacts":["significant indirect impacts", "economic impacts", "local economy"],
        }
    },
    "GRI 204 – Procurement Practices": {
        "keywords": ["gri 204", "procurement", "local suppliers", "proportion local"],
        "disclosures": {
            "204-1 Local suppliers":           ["local suppliers", "proportion spent", "local procurement"],
        }
    },
    "GRI 205 – Anti-Corruption": {
        "keywords": ["gri 205", "anti-corruption", "corruption risk", "anti-bribery", "training corruption"],
        "disclosures": {
            "205-1 Corruption risk assessment":["corruption risk", "operations assessed", "bribery risk"],
            "205-2 Anti-corruption training":  ["anti-corruption training", "anti-bribery training", "employees trained"],
            "205-3 Corruption incidents":      ["confirmed corruption", "corruption incidents", "employees dismissed"],
        }
    },
    "GRI 206 – Anti-Competitive Behaviour": {
        "keywords": ["gri 206", "anti-competitive", "antitrust", "monopoly", "competition law"],
        "disclosures": {
            "206-1 Anti-competitive actions":  ["anti-competitive", "antitrust", "monopoly practices", "legal actions"],
        }
    },
    "GRI 207 – Tax": {
        "keywords": ["gri 207", "tax", "tax governance", "country-by-country", "tax transparency"],
        "disclosures": {
            "207-1 Approach to tax":           ["tax strategy", "tax governance", "tax risk"],
            "207-2 Tax governance":            ["tax governance", "tax compliance", "tax controls"],
            "207-3 Stakeholder engagement tax":["tax stakeholder", "public tax"],
            "207-4 Country-by-country report": ["country-by-country", "cbc report", "jurisdictions"],
        }
    },
}

# Environmental Standards (GRI 300)
GRI_300 = {
    "GRI 301 – Materials": {
        "keywords": ["gri 301", "materials", "raw materials", "recycled materials", "material consumption"],
        "disclosures": {
            "301-1 Materials used":            ["materials used", "raw materials", "tonnes of material", "material consumption"],
            "301-2 Recycled input materials":  ["recycled input", "recycled materials", "recycled content"],
            "301-3 Reclaimed products":        ["reclaimed products", "packaging reclaimed", "end of life"],
        }
    },
    "GRI 302 – Energy": {
        "keywords": ["gri 302", "energy consumption", "energy intensity", "renewable energy", "energy reduction"],
        "disclosures": {
            "302-1 Energy consumption":        ["energy consumption", "fuel consumption", "electricity consumption", "gigajoules", "gj", "mwh"],
            "302-2 Energy outside organisation":["energy outside", "upstream energy", "downstream energy"],
            "302-3 Energy intensity":          ["energy intensity", "energy per unit", "energy ratio"],
            "302-4 Energy reduction":          ["energy reduction", "energy savings", "efficiency improvements"],
            "302-5 Reductions in product energy":["product energy reduction", "service energy reduction"],
        }
    },
    "GRI 303 – Water & Effluents": {
        "keywords": ["gri 303", "water", "water withdrawal", "water consumption", "water discharge", "effluents"],
        "disclosures": {
            "303-1 Interactions with water":   ["water stewardship", "water interaction", "water-related impacts"],
            "303-2 Management of water discharge":["water discharge management", "effluent management"],
            "303-3 Water withdrawal":          ["water withdrawal", "megalitres", "water sources", "surface water", "groundwater"],
            "303-4 Water discharge":           ["water discharge", "effluent discharge", "discharge destination"],
            "303-5 Water consumption":         ["water consumption", "net water", "water consumed"],
        }
    },
    "GRI 304 – Biodiversity": {
        "keywords": ["gri 304", "biodiversity", "habitats", "protected areas", "species affected", "iucn"],
        "disclosures": {
            "304-1 Sites in protected areas":  ["protected areas", "high biodiversity", "sites owned"],
            "304-2 Impacts on biodiversity":   ["biodiversity impacts", "habitats affected", "species disturbed"],
            "304-3 Habitats protected":        ["habitats protected", "restored habitats", "rehabilitation"],
            "304-4 IUCN species":              ["iucn", "red list", "species on iucn"],
        }
    },
    "GRI 305 – Emissions": {
        "keywords": ["gri 305", "scope 1", "scope 2", "scope 3", "ghg emissions", "co2e", "tco2e", "emissions intensity"],
        "disclosures": {
            "305-1 Scope 1 GHG emissions":     ["scope 1", "direct emissions", "tco2e", "co2e scope 1"],
            "305-2 Scope 2 GHG emissions":     ["scope 2", "indirect emissions", "market-based", "location-based"],
            "305-3 Scope 3 GHG emissions":     ["scope 3", "value chain emissions", "upstream", "downstream"],
            "305-4 GHG emissions intensity":   ["emissions intensity", "ghg intensity", "co2e per unit"],
            "305-5 Reduction of GHG emissions":["emissions reduction", "ghg reduction", "abatement"],
            "305-6 Ozone-depleting substances":["ozone depleting", "ods", "hcfc", "cfc"],
            "305-7 NOx SOx emissions":         ["nox", "sox", "nitrogen oxides", "sulphur oxides", "particulate matter"],
        }
    },
    "GRI 306 – Waste": {
        "keywords": ["gri 306", "waste", "waste generated", "waste diverted", "hazardous waste", "waste disposal"],
        "disclosures": {
            "306-1 Waste generation impacts":  ["waste impacts", "waste generation approach"],
            "306-2 Management of waste":       ["waste management", "waste minimisation"],
            "306-3 Waste generated":           ["waste generated", "tonnes of waste", "total waste"],
            "306-4 Waste diverted":            ["waste diverted", "reuse", "recycling", "composting", "recovery"],
            "306-5 Waste directed to disposal":["waste disposal", "landfill", "incineration", "hazardous disposal"],
        }
    },
    "GRI 308 – Supplier Environmental Assessment": {
        "keywords": ["gri 308", "supplier environmental", "environmental screening", "supplier assessment"],
        "disclosures": {
            "308-1 Environmental screening":   ["environmental screening", "suppliers screened", "new suppliers"],
            "308-2 Negative environmental impacts in supply chain":["negative environmental impacts", "supplier audits", "environmental impacts supply chain"],
        }
    },
}

# Social Standards (GRI 400)
GRI_400 = {
    "GRI 401 – Employment": {
        "keywords": ["gri 401", "employment", "new hires", "employee turnover", "benefits", "parental leave"],
        "disclosures": {
            "401-1 New hires & turnover":      ["new hires", "employee turnover", "attrition rate"],
            "401-2 Benefits to full-time employees":["benefits", "health insurance", "life insurance", "parental leave", "retirement"],
            "401-3 Parental leave":            ["parental leave", "maternity leave", "paternity leave", "return to work"],
        }
    },
    "GRI 402 – Labour Management Relations": {
        "keywords": ["gri 402", "labour management", "notice period", "operational changes"],
        "disclosures": {
            "402-1 Notice periods":            ["notice period", "minimum notice", "operational changes"],
        }
    },
    "GRI 403 – Occupational Health & Safety": {
        "keywords": ["gri 403", "occupational health", "safety", "work-related injuries", "hazard identification", "lost time"],
        "disclosures": {
            "403-1 OHS management system":     ["ohs management", "health and safety system", "iso 45001"],
            "403-2 Hazard identification":     ["hazard identification", "risk assessment", "incident investigation"],
            "403-3 Occupational health services":["occupational health services", "health promotion"],
            "403-4 Worker OHS participation":  ["worker participation", "health and safety committee", "safety representative"],
            "403-5 OHS training":              ["health and safety training", "ohs training"],
            "403-6 Promotion of worker health":["worker health promotion", "wellness programme"],
            "403-7 Prevention of impacts":     ["prevention", "supply chain ohs", "contractor safety"],
            "403-8 Workers covered by OHS":    ["workers covered", "ohs coverage"],
            "403-9 Work-related injuries":     ["work-related injuries", "fatalities", "lost time", "trir", "ltir", "recordable incidents"],
            "403-10 Work-related ill health":  ["work-related ill health", "occupational disease", "ill health cases"],
        }
    },
    "GRI 404 – Training & Education": {
        "keywords": ["gri 404", "training", "education", "hours of training", "performance review", "skills development"],
        "disclosures": {
            "404-1 Hours of training":         ["hours of training", "average training hours", "training hours per employee"],
            "404-2 Programmes for upgrading skills":["upskilling", "reskilling", "skills development programme", "transition assistance"],
            "404-3 Performance and career reviews":["performance review", "career development", "appraisal"],
        }
    },
    "GRI 405 – Diversity & Equal Opportunity": {
        "keywords": ["gri 405", "diversity", "equal opportunity", "gender diversity", "board diversity", "pay ratio"],
        "disclosures": {
            "405-1 Diversity in governance":   ["diversity governance", "board diversity", "gender board", "age group board"],
            "405-2 Ratio of remuneration":     ["pay ratio", "gender pay", "remuneration ratio", "basic salary ratio"],
        }
    },
    "GRI 406 – Non-Discrimination": {
        "keywords": ["gri 406", "non-discrimination", "discrimination incidents", "equal treatment"],
        "disclosures": {
            "406-1 Discrimination incidents":  ["discrimination incidents", "harassment incidents", "non-discrimination"],
        }
    },
    "GRI 407 – Freedom of Association": {
        "keywords": ["gri 407", "freedom of association", "collective bargaining", "right to organise"],
        "disclosures": {
            "407-1 Right to collective bargaining":["right to organise", "freedom of association", "operations at risk"],
        }
    },
    "GRI 408 – Child Labour": {
        "keywords": ["gri 408", "child labour", "young workers", "minimum age"],
        "disclosures": {
            "408-1 Child labour risk":         ["child labour", "operations at risk child", "suppliers child labour"],
        }
    },
    "GRI 409 – Forced or Compulsory Labour": {
        "keywords": ["gri 409", "forced labour", "compulsory labour", "modern slavery", "human trafficking"],
        "disclosures": {
            "409-1 Forced labour risk":        ["forced labour", "modern slavery", "human trafficking", "bonded labour"],
        }
    },
    "GRI 410 – Security Practices": {
        "keywords": ["gri 410", "security practices", "security personnel", "human rights training security"],
        "disclosures": {
            "410-1 Security personnel training":["security personnel", "human rights training", "security training"],
        }
    },
    "GRI 411 – Rights of Indigenous Peoples": {
        "keywords": ["gri 411", "indigenous peoples", "free prior informed consent", "fpic"],
        "disclosures": {
            "411-1 Indigenous peoples incidents":["indigenous peoples", "fpic", "free prior informed consent"],
        }
    },
    "GRI 413 – Local Communities": {
        "keywords": ["gri 413", "local communities", "community engagement", "community impact", "social impact assessment"],
        "disclosures": {
            "413-1 Community engagement":      ["community engagement", "social impact assessment", "stakeholder engagement local"],
            "413-2 Negative community impacts":["negative community impacts", "community grievances"],
        }
    },
    "GRI 414 – Supplier Social Assessment": {
        "keywords": ["gri 414", "supplier social", "social screening", "supplier social assessment"],
        "disclosures": {
            "414-1 Social screening new suppliers":["social screening", "suppliers screened social", "new suppliers social"],
            "414-2 Negative social impacts supply chain":["negative social impacts", "social audits", "supply chain social"],
        }
    },
    "GRI 415 – Public Policy": {
        "keywords": ["gri 415", "public policy", "political contributions", "lobbying"],
        "disclosures": {
            "415-1 Political contributions":   ["political contributions", "lobbying expenditure", "political donations"],
        }
    },
    "GRI 416 – Customer Health & Safety": {
        "keywords": ["gri 416", "customer health", "product safety", "health and safety impacts products"],
        "disclosures": {
            "416-1 Product safety assessment": ["product safety assessment", "health impact assessment", "services assessed"],
            "416-2 Product safety incidents":  ["product safety incidents", "regulatory non-compliance products"],
        }
    },
    "GRI 417 – Marketing & Labelling": {
        "keywords": ["gri 417", "marketing", "labelling", "product information", "marketing communications"],
        "disclosures": {
            "417-1 Product information":       ["product information requirements", "labelling", "product ingredients"],
            "417-2 Labelling incidents":        ["labelling incidents", "non-compliance labelling"],
            "417-3 Marketing communications":  ["marketing non-compliance", "advertising incidents"],
        }
    },
    "GRI 418 – Customer Privacy": {
        "keywords": ["gri 418", "customer privacy", "data privacy", "data protection", "gdpr", "personal data"],
        "disclosures": {
            "418-1 Customer privacy complaints":["privacy complaints", "data breaches", "customer data", "personal data complaints"],
        }
    },
}

# Combined GRI lookup
ALL_GRI_STANDARDS = {**GRI_UNIVERSAL, **GRI_200, **GRI_300, **GRI_400}

# ── Core analysis functions ───────────────────────────────────────────────────
def extract_pdf_text(uploaded_file) -> str:
    data = uploaded_file.read()
    doc  = fitz.open(stream=data, filetype="pdf")
    return "\n".join(page.get_text("text") for page in doc)


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def keyword_score(text: str, keywords: list) -> int:
    matched = sum(1 for k in keywords if k.lower() in text)
    return round((matched / len(keywords)) * 100) if keywords else 0


def grade_from_score(score: int) -> str:
    if score >= 85: return "A"
    if score >= 70: return "B"
    if score >= 55: return "C"
    if score >= 40: return "D"
    return "F"


# ── Numeric pattern detectors ─────────────────────────────────────────────────
# Matches things like: 12,345 tCO2e | 98.6% | 4.2 GJ | 500 megalitres
_NUM_RE       = re.compile(r'\b\d[\d,\.]*\s{0,4}(%|tco2e|co2e|gj|mj|mwh|kwh|gwh|megalitres|ml|tonnes|mt|kg|m3|hectares|km2)\b')
_YEAR_RE      = re.compile(r'\b(20\d{2})\b')          # year references like 2023, 2030
_METHOD_TERMS = ["methodology", "calculation method", "boundary", "assumption", "baseline year",
                 "market-based", "location-based", "iso 14064", "ghg protocol", "defra", "ipcc",
                 "emission factor", "activity data", "assurance", "verified", "third-party"]
_TARGET_TERMS = ["target", "goal", "commitment", "net zero", "science-based", "sbti",
                 "reduce by", "reduction of", "by 2030", "by 2050", "interim target"]


def surrounding_window(text: str, term: str, window: int = 300) -> str:
    """Return text around all occurrences of term (up to 5 windows)."""
    windows, start = [], 0
    t = term.lower()
    for _ in range(5):
        idx = text.find(t, start)
        if idx == -1:
            break
        windows.append(text[max(0, idx - window): idx + len(t) + window])
        start = idx + len(t)
    return " ".join(windows)


def density_score(text: str, keyword: str) -> int:
    """
    Count how many times keyword appears per 10,000 chars.
    Returns a 0-100 capped density score.
    High density = substantive section, not a passing mention.
    """
    count = text.count(keyword.lower())
    if count == 0:
        return 0
    rate = (count / max(len(text), 1)) * 10_000   # occurrences per 10k chars
    return min(100, round(rate * 20))              # scale: 5 occ/10k → 100


def context_quality_score(text: str, keywords: list) -> int:
    """
    For each matched keyword, check the surrounding window for:
      - numeric data  (+30)
      - methodology terms  (+25)
      - target/goal language  (+20)
      - year references  (+15)
      - density bonus  (+10)
    Returns 0-100.
    """
    matched = [k for k in keywords if k.lower() in text]
    if not matched:
        return 0

    scores = []
    for kw in matched:
        ctx   = surrounding_window(text, kw, window=400)
        score = 0
        if _NUM_RE.search(ctx):                                      score += 30
        if any(m in ctx for m in _METHOD_TERMS):                     score += 25
        if any(t in ctx for t in _TARGET_TERMS):                     score += 20
        if len(_YEAR_RE.findall(ctx)) >= 2:                          score += 15
        score += min(10, density_score(text, kw) // 10)
        scores.append(min(100, score))

    return round(sum(scores) / len(scores))


def combined_score(text: str, keywords: list) -> int:
    """
    Blended score:
      50% presence score (original)   — does the topic exist at all?
      50% context quality score (new) — is it backed by data & methodology?
    This prevents a single passing mention from scoring the same as a full section.
    """
    presence = keyword_score(text, keywords)
    if presence == 0:
        return 0
    quality  = context_quality_score(text, keywords)
    return round(presence * 0.5 + quality * 0.5)


def calculate_scores(text: str):
    framework_scores = {name: combined_score(text, kws) for name, kws in FRAMEWORK_KEYWORDS.items()}
    pillar_scores    = {name: combined_score(text, kws) for name, kws in ESG_PILLARS.items()}
    return framework_scores, pillar_scores


def build_gap_table(text: str) -> pd.DataFrame:
    """
    Gap detection now uses context quality, not just presence.
    A term that appears once with no data context is still flagged as a gap.
    """
    rows = []
    for gap, term, sev, rec in GAP_CHECKS:
        present = term.lower() in text
        if not present:
            rows.append({"Severity": sev, "Disclosure Gap": gap,
                         "Signal": "Term absent", "Recommendation": rec})
        else:
            ctx_score = context_quality_score(text, [term])
            if ctx_score < 25:
                # Term exists but lacks numeric data / methodology context
                rows.append({"Severity": sev, "Disclosure Gap": f"{gap} (mentioned but lacks data/methodology)",
                             "Signal": f"Term present, context quality {ctx_score}/100",
                             "Recommendation": rec})
    return pd.DataFrame(rows)


def detect_greenwashing(text: str) -> pd.DataFrame:
    rows = []
    for term in GREENWASHING_TERMS:
        if term in text:
            ctx          = surrounding_window(text, term)
            has_numbers  = bool(_NUM_RE.search(ctx))
            has_method   = any(m in ctx for m in _METHOD_TERMS)
            has_evidence = any(e in ctx for e in EVIDENCE_TERMS)
            evidence_count = sum([has_numbers, has_method, has_evidence])

            risk = "Low" if evidence_count >= 3 else "Medium" if evidence_count >= 1 else "High"
            assessment = (
                "Strong evidence nearby — numbers, methodology, and verification present." if evidence_count >= 3
                else "Partial evidence nearby — some supporting data but methodology or verification missing." if evidence_count >= 1
                else "Claim appears without numeric evidence, methodology, or verification."
            )
            rows.append({
                "Risk Level":      risk,
                "Claim Detected":  term,
                "Evidence Found":  f"Numbers: {'✓' if has_numbers else '✗'} | Method: {'✓' if has_method else '✗'} | Assurance: {'✓' if has_evidence else '✗'}",
                "Assessment":      assessment,
                "Recommended Fix": "Add quantified evidence, baseline year, methodology reference, reporting boundary, and assurance statement.",
            })
    return pd.DataFrame(rows).drop_duplicates(subset=["Claim Detected"]) if rows else pd.DataFrame()


def esrs_coverage(text: str) -> pd.DataFrame:
    rows = []
    for topic, kws in ESRS_TOPICS.items():
        score  = combined_score(text, kws)
        status = "Disclosed" if score >= 55 else "Partial" if score >= 25 else "Missing"
        rows.append({"ESRS Topic": topic, "Status": status, "Coverage Score": score})
    return pd.DataFrame(rows)


def brsr_coverage(text: str) -> pd.DataFrame:
    rows = []
    for principle, kws in BRSR_PRINCIPLES.items():
        score  = combined_score(text, kws)
        status = "Disclosed" if score >= 55 else "Partial" if score >= 25 else "Missing"
        rows.append({"BRSR Principle": principle, "Status": status, "Coverage Score": score})
    return pd.DataFrame(rows)


# ── GRI analysis functions ────────────────────────────────────────────────────
def gri_standard_coverage(text: str) -> pd.DataFrame:
    """Coverage score per GRI standard using combined presence + context quality."""
    rows = []
    for standard, data in ALL_GRI_STANDARDS.items():
        score  = combined_score(text, data["keywords"])
        status = "Disclosed" if score >= 55 else "Partial" if score >= 25 else "Missing"
        group  = ("Universal" if standard.startswith("GRI 1") or standard.startswith("GRI 2") or standard.startswith("GRI 3 –")
                  else "Economic (200)" if any(standard.startswith(f"GRI 20{i}") for i in range(10))
                  else "Environmental (300)" if any(standard.startswith(f"GRI 3{i}") for i in range(10))
                  else "Social (400)")
        rows.append({
            "GRI Standard": standard,
            "Group":        group,
            "Status":       status,
            "Coverage %":   score,
        })
    return pd.DataFrame(rows)


def gri_disclosure_detail(text: str) -> pd.DataFrame:
    """Detailed disclosure-level mapping with presence + context quality scores."""
    rows = []
    for standard, data in ALL_GRI_STANDARDS.items():
        for disclosure, keywords in data.get("disclosures", {}).items():
            presence = keyword_score(text, keywords)
            quality  = context_quality_score(text, keywords) if presence > 0 else 0
            blended  = round(presence * 0.5 + quality * 0.5)
            status   = "Present" if blended >= 50 else "Partial" if blended >= 20 else "Missing"
            rows.append({
                "GRI Standard":    standard,
                "Disclosure":      disclosure,
                "Status":          status,
                "Presence %":      presence,
                "Context Quality": quality,
                "Blended Score %": blended,
            })
    return pd.DataFrame(rows)


def gri_group_summary(coverage_df: pd.DataFrame) -> dict:
    """Summary score per GRI group."""
    return coverage_df.groupby("Group")["Coverage %"].mean().round(1).to_dict()


def plot_gri_heatmap(coverage_df: pd.DataFrame):
    """Bar chart coloured by status for GRI standard coverage."""
    color_map = {"Disclosed": "#34d399", "Partial": "#f59e0b", "Missing": "#ef4444"}
    fig = px.bar(
        coverage_df.sort_values("Coverage %"),
        x="Coverage %", y="GRI Standard", orientation="h",
        color="Status", color_discrete_map=color_map,
        range_x=[0, 100], text="Coverage %",
        facet_col="Group", facet_col_wrap=2,
    )
    fig.update_traces(texttemplate="%{text}%", textposition="outside")
    fig.update_layout(
        height=900, showlegend=True,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e2e8f0", family="DM Sans, sans-serif"),
        margin=dict(l=20, r=20, t=60, b=20),
    )
    return fig


def plot_gri_group_radar(group_scores: dict):
    cats = list(group_scores.keys())
    vals = list(group_scores.values())
    fig  = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=vals + [vals[0]], theta=cats + [cats[0]],
        fill="toself", line_color="#818cf8",
        fillcolor="rgba(129,140,248,0.18)", name="GRI Coverage",
    ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], color="#475569"),
            angularaxis=dict(color="#94a3b8"),
            bgcolor="rgba(0,0,0,0)",
        ),
        showlegend=False, **CHART_LAYOUT,
    )
    return fig


# ── Groq AI summary ───────────────────────────────────────────────────────────
def generate_ai_summary(
    overall: int, csrd: int, risk: str,
    strongest: str, weakest: str,
    gap_count: int, flag_count: int,
    framework_scores: dict,
    brsr_score: int,
    gri_group_scores: dict = None,
    gri_disclosed: int = 0,
    gri_total: int = 0,
) -> str:
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        api_key = st.secrets.get("GROQ_API_KEY", "")
    if not api_key:
        return "⚠️ GROQ_API_KEY not found. Add it to your .env file or Streamlit secrets."

    client = Groq(api_key=api_key)

    gri_text = ""
    if gri_group_scores:
        gri_text = f"\n- GRI Standards Disclosed: {gri_disclosed}/{gri_total}"
        gri_text += f"\n- GRI Group Scores: {', '.join(f'{k}: {v}%' for k, v in gri_group_scores.items())}"

    prompt = f"""You are a senior ESG disclosure analyst writing for a sustainability practitioner.

Rule-based screening results:
- Overall ESG Score: {overall}/100 (Grade {grade_from_score(overall)})
- CSRD/ESRS Readiness: {csrd}%
- BRSR Readiness: {brsr_score}%
- Greenwashing Risk: {risk}
- Strongest ESG Pillar: {strongest}
- Weakest ESG Pillar: {weakest}
- Disclosure Gaps: {gap_count}
- Greenwashing Flags: {flag_count}
- Framework Coverage: {', '.join(f'{k}: {v}%' for k, v in framework_scores.items())}{gri_text}

Write a concise 3-paragraph executive summary:
1. Overall disclosure maturity, GRI standards coverage, and key strengths
2. Critical gaps, greenwashing risks, BRSR/CSRD compliance status, and weakest GRI areas
3. Top 3 specific, actionable recommendations prioritised by impact

Be direct, specific, and professional. No bullet points. No generic filler."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
        max_tokens=600,
    )
    return response.choices[0].message.content.strip()


# ── Chart helpers ─────────────────────────────────────────────────────────────
CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#e2e8f0", family="DM Sans, sans-serif"),
    margin=dict(l=20, r=20, t=30, b=30),
    height=370,
)


def plot_radar(pillar_scores: dict):
    cats   = list(pillar_scores.keys())
    vals   = list(pillar_scores.values())
    fig    = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=vals + [vals[0]], theta=cats + [cats[0]],
        fill="toself", line_color="#34d399",
        fillcolor="rgba(52,211,153,0.18)", name="Score",
    ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], color="#475569"),
            angularaxis=dict(color="#94a3b8"),
            bgcolor="rgba(0,0,0,0)",
        ),
        showlegend=False, **CHART_LAYOUT,
    )
    return fig


def plot_frameworks(framework_scores: dict):
    df  = pd.DataFrame({"Framework": list(framework_scores.keys()), "Coverage": list(framework_scores.values())})
    fig = px.bar(df, x="Framework", y="Coverage", text="Coverage",
                 range_y=[0, 100], color="Coverage",
                 color_continuous_scale=["#ef4444", "#f59e0b", "#34d399"])
    fig.update_traces(texttemplate="%{text}%", textposition="outside")
    fig.update_coloraxes(showscale=False)
    fig.update_layout(**CHART_LAYOUT)
    return fig


def plot_esrs_bar(esrs_df: pd.DataFrame):
    color_map = {"Disclosed": "#34d399", "Partial": "#f59e0b", "Missing": "#ef4444"}
    fig = px.bar(
        esrs_df, x="Coverage Score", y="ESRS Topic", orientation="h",
        color="Status", color_discrete_map=color_map,
        range_x=[0, 100], text="Coverage Score",
    )
    fig.update_traces(texttemplate="%{text}%", textposition="outside")
    fig.update_layout(showlegend=True, height=420, **{k: v for k, v in CHART_LAYOUT.items() if k != "height"})
    return fig


def kpi_card(label: str, value: str, note: str, color: str = "#34d399"):
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div class="metric-value" style="color:{color}">{value}</div>
        <div class="metric-note">{note}</div>
    </div>""", unsafe_allow_html=True)


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🌿 ESG Report Analyser")
    st.caption("Powered by Groq · llama-3.3-70b")
    st.divider()
    st.markdown("### Screening modules")
    st.markdown("""
- 📊 ESG pillar maturity  
- 🏛 CSRD / ESRS readiness  
- 🇮🇳 BRSR compliance (India)  
- 📋 GRI Universal Standards (1, 2, 3)  
- 📋 GRI 200 Economic (201–207)  
- 📋 GRI 300 Environmental (301–308)  
- 📋 GRI 400 Social (401–418)  
- 🔍 GRI disclosure-level mapping  
- 📋 TCFD · GHG Protocol · SDGs  
- ⚠️ Greenwashing risk flags  
- 🔍 Disclosure gap analysis  
- 🤖 AI executive summary  
    """)
    st.divider()
    st.info("Rule-based screening engine + Groq AI summary. Not a formal audit or assurance opinion.")
    st.divider()
    st.caption("Built by **Gokul Krishna T. B.**")

# ── Google Analytics injection ────────────────────────────────────────────────
GA_ID = "G-NNLCK8ZFVN"
components.html(f"""
<script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', '{GA_ID}');
</script>
""", height=0)

# ── Google Sheets helpers ─────────────────────────────────────────────────────
SHEET_COLUMNS = [
    "Timestamp", "Industry", "Report Year",
    "Overall Score", "CSRD %", "BRSR %", "GRI Disclosed", "GRI Total",
    "Greenwashing Risk", "Gaps Count", "Flags Count",
    "Env Score", "Social Score", "Governance Score", "Climate Risk Score", "Supply Chain Score",
]

INDUSTRIES = [
    "Energy & Utilities", "Manufacturing", "Financial Services",
    "Healthcare & Pharma", "Technology", "Retail & Consumer Goods",
    "Transport & Logistics", "Real Estate & Construction",
    "Agriculture & Food", "Mining & Resources", "Other",
]


@st.cache_resource
def get_sheet():
    """Connect to Google Sheet using service account credentials from Streamlit secrets."""
    try:
        creds_dict = dict(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
        creds = Credentials.from_service_account_info(
            creds_dict,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        client = gspread.authorize(creds)
        sheet_id = st.secrets.get("GOOGLE_SHEET_ID", "")
        return client.open_by_key(sheet_id).sheet1
    except Exception:
        return None


def ensure_headers(sheet):
    """Add header row if sheet is empty."""
    try:
        if sheet and not sheet.row_values(1):
            sheet.append_row(SHEET_COLUMNS)
    except Exception:
        pass


def submit_to_community(sheet, industry, report_year, result, pillar_scores,
                         gri_disclosed, gri_total):
    """Append one anonymous row to the community sheet."""
    try:
        ensure_headers(sheet)
        row = [
            datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
            industry,
            report_year,
            result["overall"],
            result["csrd"],
            result["brsr"],
            gri_disclosed,
            gri_total,
            result["risk"],
            result["gaps"],
            result["flags"],
            pillar_scores.get("Environment", 0),
            pillar_scores.get("Social", 0),
            pillar_scores.get("Governance", 0),
            pillar_scores.get("Climate Risk", 0),
            pillar_scores.get("Supply Chain", 0),
        ]
        sheet.append_row(row)
        return True
    except Exception:
        return False


def get_community_stats(sheet):
    """Fetch all rows and compute community stats."""
    try:
        records = sheet.get_all_records()
        if not records:
            return None
        df = pd.DataFrame(records)
        return df
    except Exception:
        return None


def plot_you_vs_community(your_scores: dict, community_df: pd.DataFrame):
    """Bar chart comparing your pillar scores vs community average."""
    cols = {
        "Environment":    "Env Score",
        "Social":         "Social Score",
        "Governance":     "Governance Score",
        "Climate Risk":   "Climate Risk Score",
        "Supply Chain":   "Supply Chain Score",
    }
    community_avgs = {k: round(community_df[v].mean()) for k, v in cols.items() if v in community_df.columns}

    pillars = list(cols.keys())
    your_vals = [your_scores.get(p, 0) for p in pillars]
    comm_vals = [community_avgs.get(p, 0) for p in pillars]

    fig = go.Figure()
    fig.add_trace(go.Bar(name="Your Report", x=pillars, y=your_vals,
                         marker_color="#34d399", text=your_vals,
                         textposition="outside"))
    fig.add_trace(go.Bar(name="Community Average", x=pillars, y=comm_vals,
                         marker_color="#60a5fa", text=comm_vals,
                         textposition="outside"))
    fig.update_layout(
        barmode="group", yaxis_range=[0, 110],
        **CHART_LAYOUT,
    )
    return fig

# ── Hero ──────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero">
    <h1>ESG Report Analyser</h1>
    <p>Upload a sustainability report PDF and get an instant screening dashboard — CSRD/ESRS readiness,
    BRSR compliance, GRI · TCFD · GHG Protocol coverage, greenwashing risk flags, disclosure gaps,
    and an AI-generated executive summary powered by Groq.</p>
    <span class="tag">CSRD / ESRS</span>
    <span class="tag">GRI Universal · 200 · 300 · 400</span>
    <span class="tag">BRSR · India</span>
    <span class="tag">TCFD</span>
    <span class="tag">GHG Protocol</span>
    <span class="tag">Groq AI</span>
    <span class="tag">Greenwashing Risk</span>
</div>
""", unsafe_allow_html=True)

# ── Community stat bar ────────────────────────────────────────────────────────
_sheet = get_sheet()
_community_df = get_community_stats(_sheet) if _sheet else None
_total_count  = len(_community_df) if _community_df is not None else 0
_avg_score    = round(_community_df["Overall Score"].mean()) if _community_df is not None and _total_count > 0 else "—"
_industries   = _community_df["Industry"].nunique() if _community_df is not None and _total_count > 0 else 0

st.markdown(f"""
<div style="
    padding: 14px 24px; border-radius: 14px; margin-bottom: 20px;
    background: rgba(52,211,153,0.07); border: 1px solid rgba(52,211,153,0.2);
    display: flex; gap: 32px; align-items: center; flex-wrap: wrap;
">
    <span style="color:#a7f3d0; font-size:13px; font-weight:700;">🌍 Community</span>
    <span style="color:#f8fafc; font-size:14px;">
        <strong style="color:#34d399; font-size:22px;">{_total_count}</strong>
        &nbsp;reports analysed
    </span>
    <span style="color:#f8fafc; font-size:14px;">
        <strong style="color:#60a5fa; font-size:22px;">{_industries}</strong>
        &nbsp;industries
    </span>
    <span style="color:#f8fafc; font-size:14px;">
        <strong style="color:#f59e0b; font-size:22px;">{_avg_score}</strong>
        &nbsp;avg score
    </span>
    {"<span style='color:#94a3b8; font-size:12px;'>Be one of the first to contribute! 🚀</span>" if _total_count < 10 else ""}
</div>
""", unsafe_allow_html=True)

# ── File upload ───────────────────────────────────────────────────────────────
uploaded_file = st.file_uploader(
    "Upload a sustainability report PDF",
    type=["pdf"],
    help="Upload a text-based PDF. Scanned/image-only PDFs may not extract correctly.",
)

if uploaded_file is None:
    c1, c2, c3 = st.columns(3)
    with c1: kpi_card("Step 1", "Upload", "Add a sustainability or ESG report PDF.")
    with c2: kpi_card("Step 2", "Scan",   "Checks ESG, CSRD, BRSR, GRI, TCFD, and GHG terms.", "#60a5fa")
    with c3: kpi_card("Step 3", "Improve","Use the dashboard to identify and fix reporting gaps.", "#f59e0b")
    st.stop()

# ── Extract & analyse ─────────────────────────────────────────────────────────
try:
    raw_text = extract_pdf_text(uploaded_file)
except Exception as exc:
    st.error(f"Could not read the PDF: {exc}")
    st.stop()

if len(raw_text.strip()) < 300:
    st.error("Not enough text extracted. This may be a scanned/image-based PDF. Try a text-based PDF.")
    st.stop()

text = clean_text(raw_text)

framework_scores, pillar_scores = calculate_scores(text)
gaps_df         = build_gap_table(text)
greenwashing_df = detect_greenwashing(text)
esrs_df         = esrs_coverage(text)
brsr_df         = brsr_coverage(text)
gri_coverage_df = gri_standard_coverage(text)
gri_detail_df   = gri_disclosure_detail(text)
gri_groups      = gri_group_summary(gri_coverage_df)
gri_disclosed   = len(gri_coverage_df[gri_coverage_df["Status"] == "Disclosed"])
gri_total       = len(gri_coverage_df)

overall_score   = round(sum(pillar_scores.values()) / len(pillar_scores))
csrd_score      = framework_scores.get("ESRS / CSRD", 0)
brsr_score      = round(brsr_df["Coverage Score"].mean())
high_gaps       = 0 if gaps_df.empty else len(gaps_df[gaps_df["Severity"] == "High"])
risk_level      = ("High"   if len(greenwashing_df) >= 4 or high_gaps >= 2 else
                   "Medium" if len(greenwashing_df) >= 2 or high_gaps == 1  else "Low")
strongest       = max(pillar_scores, key=pillar_scores.get)
weakest         = min(pillar_scores, key=pillar_scores.get)

risk_color  = {"High": "#ef4444", "Medium": "#f59e0b", "Low": "#34d399"}.get(risk_level, "#94a3b8")

st.success(f"✅ Analysed: **{uploaded_file.name}**")

# ── KPI row ───────────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5, c6 = st.columns(6)
with c1: kpi_card("Overall ESG Score",   f"{overall_score}/100", f"Grade {grade_from_score(overall_score)}")
with c2: kpi_card("CSRD Readiness",      f"{csrd_score}%",       "ESRS/CSRD evidence coverage", "#60a5fa")
with c3: kpi_card("BRSR Readiness",      f"{brsr_score}%",       "India NGRBC principle coverage", "#a78bfa")
with c4: kpi_card("GRI Coverage",        f"{gri_disclosed}/{gri_total}", "GRI standards disclosed", "#f472b6")
with c5: kpi_card("Greenwashing Risk",   risk_level,             f"{len(greenwashing_df)} flag(s)", risk_color)
with c6: kpi_card("Disclosure Gaps",     str(len(gaps_df)),      f"{high_gaps} high severity", "#f59e0b")

st.markdown("<br>", unsafe_allow_html=True)

# ── Community opt-in ──────────────────────────────────────────────────────────
with st.expander("🌍 Contribute to community benchmarking (optional & anonymous)", expanded=False):
    st.markdown("""
    Your scores will be saved **anonymously** — no report content, no email, no personal data.
    Just your scores + industry + year. This helps build a public benchmark for the ESG community.
    """)
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        opt_in = st.checkbox("Yes, share my scores anonymously", value=False)
    with col_b:
        selected_industry = st.selectbox("Industry", INDUSTRIES, disabled=not opt_in)
    with col_c:
        selected_year = st.selectbox("Report Year", list(range(2024, 2018, -1)), disabled=not opt_in)

    if opt_in:
        if st.button("Submit to community", type="primary"):
            result_dict = {
                "overall": overall_score, "csrd": csrd_score,
                "brsr": brsr_score, "risk": risk_level,
                "gaps": len(gaps_df), "flags": len(greenwashing_df),
            }
            success = submit_to_community(
                _sheet, selected_industry, selected_year,
                result_dict, pillar_scores, gri_disclosed, gri_total,
            )
            if success:
                st.success("✅ Submitted! Thank you for contributing to the community benchmark.")
                st.cache_resource.clear()
            else:
                st.error("Submission failed — Google Sheets may not be configured yet.")

# ── Community comparison ──────────────────────────────────────────────────────
if _community_df is not None and _total_count >= 5:
    with st.expander("📊 Your scores vs community average", expanded=True):
        industry_df = _community_df[_community_df["Industry"] == selected_industry] if opt_in and len(_community_df[_community_df["Industry"] == selected_industry]) >= 3 else _community_df
        label = f"industry average ({selected_industry})" if opt_in and len(industry_df) >= 3 else "overall community average"
        st.caption(f"Comparing your report against {label} · {len(industry_df)} reports")

        # Percentile ranks
        p_overall = round((industry_df["Overall Score"] < overall_score).mean() * 100)
        p_csrd    = round((industry_df["CSRD %"] < csrd_score).mean() * 100)

        pc1, pc2 = st.columns(2)
        with pc1:
            kpi_card("Your Percentile (Overall)", f"Top {100 - p_overall}%",
                     f"Better than {p_overall}% of reports", "#34d399")
        with pc2:
            kpi_card("Your Percentile (CSRD)", f"Top {100 - p_csrd}%",
                     f"Better than {p_csrd}% on CSRD readiness", "#60a5fa")

        st.plotly_chart(plot_you_vs_community(pillar_scores, industry_df), use_container_width=True)

elif _community_df is not None and 0 < _total_count < 5:
    st.info(f"🌱 {_total_count} report(s) submitted so far — community comparison unlocks at 5. Be an early contributor!")

st.markdown("<br>", unsafe_allow_html=True)

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs([
    "📊 Dashboard",
    "🤖 AI Summary",
    "📋 GRI Coverage",
    "🔍 GRI Disclosures",
    "⚠️ Disclosure Gaps",
    "🧪 Greenwashing",
    "🗂 ESRS Coverage",
    "🇮🇳 BRSR Coverage",
    "📄 Extracted Text",
])

# ── Tab 1: Dashboard ──────────────────────────────────────────────────────────
with tab1:
    left, right = st.columns(2)
    with left:
        st.markdown('<div class="panel"><div class="panel-title">ESG Pillar Strength</div>', unsafe_allow_html=True)
        st.plotly_chart(plot_radar(pillar_scores), use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
    with right:
        st.markdown('<div class="panel"><div class="panel-title">Framework Coverage</div>', unsafe_allow_html=True)
        st.plotly_chart(plot_frameworks(framework_scores), use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    left2, right2 = st.columns(2)
    with left2:
        st.markdown('<div class="panel"><div class="panel-title">GRI Group Coverage</div>', unsafe_allow_html=True)
        st.plotly_chart(plot_gri_group_radar(gri_groups), use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
    with right2:
        st.markdown('<div class="panel"><div class="panel-title">ESRS Topic Coverage</div>', unsafe_allow_html=True)
        st.plotly_chart(plot_esrs_bar(esrs_df), use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

# ── Tab 2: AI Summary ─────────────────────────────────────────────────────────
with tab2:
    st.markdown('<div class="panel"><div class="panel-title">🤖 AI Executive Summary · Groq llama-3.3-70b</div>', unsafe_allow_html=True)
    if st.button("Generate AI Summary", type="primary"):
        with st.spinner("Generating summary via Groq…"):
            summary = generate_ai_summary(
                overall_score, csrd_score, risk_level,
                strongest, weakest,
                len(gaps_df), len(greenwashing_df),
                framework_scores, brsr_score,
                gri_group_scores=gri_groups,
                gri_disclosed=gri_disclosed,
                gri_total=gri_total,
            )
        st.markdown(f'<p class="small-muted">{summary}</p>', unsafe_allow_html=True)
    else:
        st.info("Click **Generate AI Summary** to get a Groq-powered executive summary.")
    st.markdown('</div>', unsafe_allow_html=True)

# ── Tab 3: GRI Coverage ───────────────────────────────────────────────────────
with tab3:
    st.subheader("GRI Standard Coverage")
    st.caption(f"Screening {gri_total} GRI standards · {gri_disclosed} disclosed · {len(gri_coverage_df[gri_coverage_df['Status'] == 'Partial'])} partial · {len(gri_coverage_df[gri_coverage_df['Status'] == 'Missing'])} missing")

    col_filter1, col_filter2 = st.columns(2)
    with col_filter1:
        group_filter = st.multiselect(
            "Filter by group",
            options=gri_coverage_df["Group"].unique().tolist(),
            default=gri_coverage_df["Group"].unique().tolist(),
        )
    with col_filter2:
        status_filter = st.multiselect(
            "Filter by status",
            options=["Disclosed", "Partial", "Missing"],
            default=["Disclosed", "Partial", "Missing"],
        )

    filtered_gri = gri_coverage_df[
        (gri_coverage_df["Group"].isin(group_filter)) &
        (gri_coverage_df["Status"].isin(status_filter))
    ]

    st.plotly_chart(plot_gri_heatmap(filtered_gri), use_container_width=True)
    st.dataframe(filtered_gri, use_container_width=True, hide_index=True)
    st.download_button(
        "⬇️ Download GRI Coverage CSV",
        filtered_gri.to_csv(index=False).encode("utf-8"),
        file_name="gri_standard_coverage.csv", mime="text/csv",
    )

# ── Tab 4: GRI Disclosure Detail ──────────────────────────────────────────────
with tab4:
    st.subheader("GRI Disclosure-Level Mapping")
    st.caption("Presence % = keyword found · Context Quality = backed by data, methodology & targets · Blended = final score")

    std_filter = st.selectbox(
        "Filter by GRI Standard",
        options=["All"] + sorted(gri_detail_df["GRI Standard"].unique().tolist()),
    )
    detail_filtered = gri_detail_df if std_filter == "All" else gri_detail_df[gri_detail_df["GRI Standard"] == std_filter]

    status_color = {"Present": "🟢", "Partial": "🟡", "Missing": "🔴"}
    display_df = detail_filtered.copy()
    display_df["Status"] = display_df["Status"].map(lambda s: f"{status_color.get(s,'')} {s}")

    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # Show gap between presence and quality
    low_quality = detail_filtered[
        (detail_filtered["Presence %"] >= 30) &
        (detail_filtered["Context Quality"] < 20)
    ]
    if not low_quality.empty:
        st.warning(f"⚠️ **{len(low_quality)} disclosures** are mentioned but lack numeric data or methodology context — these are the highest-priority items to strengthen.")
        st.dataframe(low_quality[["GRI Standard", "Disclosure", "Presence %", "Context Quality"]], use_container_width=True, hide_index=True)

    st.download_button(
        "⬇️ Download GRI Disclosure Detail CSV",
        gri_detail_df.to_csv(index=False).encode("utf-8"),
        file_name="gri_disclosure_detail.csv", mime="text/csv",
    )

# ── Tab 5: Disclosure Gaps ────────────────────────────────────────────────────
with tab5:
    st.subheader("Disclosure Gap Analysis")
    if gaps_df.empty:
        st.success("No major rule-based disclosure gaps detected.")
    else:
        st.dataframe(gaps_df, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Download Gap Analysis CSV",
            gaps_df.to_csv(index=False).encode("utf-8"),
            file_name="esg_disclosure_gaps.csv", mime="text/csv",
        )

# ── Tab 6: Greenwashing ───────────────────────────────────────────────────────
with tab6:
    st.subheader("Greenwashing Risk Review")
    if greenwashing_df.empty:
        st.success("No common greenwashing claims detected.")
    else:
        st.dataframe(greenwashing_df, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Download Greenwashing Review CSV",
            greenwashing_df.to_csv(index=False).encode("utf-8"),
            file_name="greenwashing_risk_review.csv", mime="text/csv",
        )

# ── Tab 7: ESRS Coverage ──────────────────────────────────────────────────────
with tab7:
    st.subheader("ESRS Topic Coverage")
    st.dataframe(esrs_df, use_container_width=True, hide_index=True)
    st.download_button(
        "⬇️ Download ESRS Coverage CSV",
        esrs_df.to_csv(index=False).encode("utf-8"),
        file_name="esrs_topic_coverage.csv", mime="text/csv",
    )

# ── Tab 8: BRSR Coverage ──────────────────────────────────────────────────────
with tab8:
    st.subheader("BRSR Principle Coverage (India)")
    st.caption("Business Responsibility & Sustainability Reporting — SEBI / NGRBC framework")
    st.dataframe(brsr_df, use_container_width=True, hide_index=True)
    st.download_button(
        "⬇️ Download BRSR Coverage CSV",
        brsr_df.to_csv(index=False).encode("utf-8"),
        file_name="brsr_principle_coverage.csv", mime="text/csv",
    )

# ── Tab 9: Extracted Text ─────────────────────────────────────────────────────
with tab9:
    st.subheader("Extracted Report Text Preview")
    st.caption("Showing first 8,000 characters.")
    st.text_area("Extracted text", raw_text[:8000], height=420)

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="footer">
    Built by <strong>Gokul Krishna T. B.</strong> · 
    Rule-based ESG intelligence engine + Groq AI · 
    Not a formal audit or assurance opinion
</div>
""", unsafe_allow_html=True)
