# Financial Services AI Agent Suite — Solution Field Guide
### A Practitioner's Guide to Positioning, Engagement, and Deployment

> **Audience:** Solutions architects, technical account managers, and pre-sales engineers engaging with financial institutions on AI-driven compliance and revenue modernization.

---

## The Platform Story: One Problem, Ten Entry Points

Financial institutions lose **$274 billion annually** to the combined burden of financial crime compliance, KYC overhead, fraud losses, RM administrative drag, regulatory change management, market surveillance, credit underwriting overhead, document processing bottlenecks, and payments dispute management. That number isn't going away — regulatory requirements are tightening, not loosening.

The status quo response is more analysts, more tools, and more complexity. The AI-native response is different: **let AI handle the high-volume, low-judgment work so your best people can focus on the 5% of decisions that actually require human expertise.**

This suite is ten purpose-built AI agents, each solving one high-cost problem. They are designed to be deployed independently — each delivers ROI on its own — but they share a common architecture, a common data model, and common regulatory controls. When deployed together, they form a closed-loop platform where every agent reinforces the others.

---

## The Ten-Agent Architecture

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│                       Financial Services AI Agent Suite                             │
│                                                                                    │
│  ┌──────────────────────────────────────────────────────────────────────────────┐  │
│  │  HORIZONTAL PLATFORM (Deploy First — Feeds All Other Agents)                 │  │
│  │                                                                              │  │
│  │  [09 · Document Intelligence]  25 doc types · PII masking before LLM        │  │
│  │   SWIFT/PDF/OCR → structured JSON · confidence scoring · HITL gate          │  │
│  │   $1.66M–$1.91M/yr · 3-week payback · suite multiplier                     │  │
│  └────────────────────────────┬─────────────────────────────────────────────────┘  │
│                               │ structured JSON feeds all specialist agents         │
│         ┌─────────────────────┼──────────────────────┐                            │
│         ▼                     ▼                       ▼                            │
│  ┌──────────────────────────────────────────────────────────────────────────────┐  │
│  │  FINANCIAL CRIME LOOP (AML)                                                  │  │
│  │                                                                              │  │
│  │  [02 · TMS Enhancement] ──────► [01 · Financial Crime Investigation]        │  │
│  │   Pre-queue FP suppression         Alert-to-SAR workflow                    │  │
│  │   ~50% queue reduction             80% reduction in hours/SAR               │  │
│  │                          ▲                    │                             │  │
│  │                          │                    ▼                             │  │
│  │  [03 · KYC/CDD Perpetual]◄──────── Risk events feed back to KYC            │  │
│  │   Triggered CDD refresh · 90% reduction in manual hours                    │  │
│  └──────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                    │
│  ┌──────────────────────────────────────────────────────────────────────────────┐  │
│  │  FRAUD & PAYMENTS LOOP                                                       │  │
│  │                                                                              │  │
│  │  [04 · Real-Time Fraud Detection] ─────► [10 · Payments Compliance]         │  │
│  │   Sub-200ms prevention · 65% fraud         BEC fraud triggers Reg E         │  │
│  │   loss reduction · Reg E auto-draft         Nacha · OFAC · SLA mgmt         │  │
│  │                                             $713K–$1.95M/yr (5K disputes)   │  │
│  └──────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                    │
│  ┌──────────────────────────────────────────────────────────────────────────────┐  │
│  │  LENDING & CLIENT INTELLIGENCE                                               │  │
│  │                                                                              │  │
│  │  [08 · Credit Underwriting] ──── [05 · Wealth & RM Copilot]                 │  │
│  │   12 loan types · ECOA/HMDA        RM productivity + Reg BI compliance      │  │
│  │   OFAC hard block · same-day       10+ hrs/week reclaimed · $3.5M/yr        │  │
│  │   $1.8M–$3.4M/yr decisions        (50 RMs) · suitability Python-only        │  │
│  └──────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                    │
│  ┌──────────────────────────────────────────────────────────────────────────────┐  │
│  │  COMPLIANCE OPERATIONS LAYER                                                 │  │
│  │                                                                              │  │
│  │  [06 · Regulatory Change Mgmt] ──► [07 · Trading Surveillance]              │  │
│  │   12-node gap analysis + remediation   11 alert types · Python rules        │  │
│  │   9 regulatory sources · FFIEC/SR 11-7 FINRA 3110 · SAR automation         │  │
│  │   $849K–$1.5M/yr (regional bank)       $2.6M/yr (6-analyst BD team)        │  │
│  └──────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                    │
│  SHARED PLATFORM LAYER (All 10 Agents)                                             │
│  LangGraph StateGraph · AWS Bedrock · Cognito + Okta/AD Auth                      │
│  Immutable Append-Only Audit Trail · SR 11-7 Explainability · BSA/FATF Controls   │
│  MCP Auth Gateway · ECS Fargate · Aurora PostgreSQL · S3 Object Lock (WORM)       │
└────────────────────────────────────────────────────────────────────────────────────┘
```

### How the Agents Feed Each Other

The linkages between agents are what make the suite more than the sum of its parts:

1. **Agent 02 (TMS Enhancement)** runs first — it scores every TMS alert before analysts see it, suppressing ~50% as false positives. The true positives that score ≤15% FP probability are automatically escalated to Agent 01 as HIGH priority.

2. **Agent 01 (Financial Crime Investigation)** receives the high-probability alert, runs the full investigation workflow — KYC pull, transaction analysis, OFAC screening, adverse media, network mapping — and drafts a BSA-compliant SAR for BSA Officer review.

3. **Agent 01 findings feed Agent 03**: when an investigation reveals a risk event (SAR filed, adverse media found, ownership change detected), Agent 03 automatically triggers a CDD refresh for that customer.

4. **Agent 03 findings feed Agent 01**: when a KYC refresh produces a risk rating change (customer is now HIGH risk), that signal is available to Agent 01 and Agent 02 as customer context in future alert scoring.

5. **Agent 04 (Fraud Detection)** runs in parallel to the AML loop. Fraud patterns it detects — account takeover, structured payments, new payee fraud — can generate SAR flags routed to Agent 01 for full investigation when patterns suggest money laundering layering.

6. **Agent 04 feeds Agent 10 (Payments Compliance)**: when Agent 04 detects Business Email Compromise or authorized push payment fraud on an ACH or wire transaction, it flags the payment for Reg E dispute processing in Agent 10. The two agents together close the loop: Agent 04 stops the fraud in real-time; Agent 10 manages the regulatory response, SLA deadlines, provisional credit, and customer notice.

7. **Agent 05 (Wealth Copilot)** is the client-facing layer — operationally independent, but it uses the same KYC data that Agent 03 maintains. If an RM client triggers an adverse media hit or watchlist match via Agent 03, the Wealth Copilot can surface that context to the RM.

8. **Agent 06 (Regulatory Change Management)** monitors 9 regulatory authorities continuously. When a BSA/AML final rule drops, it notifies Agent 01 and Agent 02 owners that threshold recalibration may be required. When a KYC/CDD rule changes, it notifies Agent 03's compliance owner with specific policy update tasks. When a new ECOA/HMDA rule affects adverse action standards, it notifies Agent 08's underwriting owner. When Nacha updates return code rules or Reg E SLA requirements change, it notifies Agent 10's payments compliance owner. Agent 06 is the connective tissue that keeps all other agents calibrated to current regulatory requirements.

9. **Agent 07 (Trading Surveillance)** monitors trading activity across 11 market abuse patterns. When it identifies potential insider trading, it cross-notifies Agent 01 for BSA/SAR assessment. When wash trading is detected across related accounts, it triggers Agent 03 to run a perpetual monitoring refresh on the implicated accounts. When Agent 06 identifies a new Dodd-Frank or FINRA rule, it notifies Agent 07's surveillance officer that detection thresholds may need updating.

10. **Agent 08 (Credit Underwriting)** feeds Agent 01 when a loan applicant triggers an OFAC hit — the hard block is recorded and the event is routed to the BSA Officer via Agent 01's case workflow. Agent 08 also uses Agent 09's structured document output directly: when Agent 09 extracts a 1003 loan application, pay stubs, and bank statements into JSON, Agent 08 receives clean, validated data instead of manual re-entry from PDFs.

11. **Agent 09 (Document Intelligence)** is the horizontal entry point for the entire suite. It receives raw documents — PDF loan applications, SWIFT MT103 wire instructions, KYC identity documents, regulatory filings — and outputs structured JSON that every other agent can consume immediately. Deploying Agent 09 first makes every subsequent agent faster to implement and more accurate, because the unstructured data problem is solved once at the platform level instead of agent by agent.

12. **Agent 10 (Payments Compliance)** receives structured SWIFT and wire instruction data from Agent 09, eliminating manual re-keying for international wires. OFAC hits detected by Agent 10 are routed to Agent 01 for BSA/SAR investigation. When a SAR candidate is detected in a payments pattern, Agent 10 flags it for the BSA Officer — Agent 01 handles the investigation workflow.

---

## Recommended Engagement Sequence

Not every customer is ready for all five agents at once. Here is the recommended engagement path based on institutional type and existing pain.

### Path A: AML-Heavy Bank (Community Bank, Regional Bank, Credit Union)
**Most common entry point — nearly every financial institution has a TMS alert volume problem.**

```
Phase 1 (Month 1-3):   Agent 02 (TMS Enhancement)
  → Fastest ROI to demonstrate: ~50% queue reduction visible within weeks
  → No workflow change required: sits upstream of existing TMS, analysts work normally

Phase 2 (Month 3-6):   Agent 01 (Financial Crime Investigation)
  → Natural follow-on: "your queue is smaller — now let's cut SAR filing costs too"
  → Agents 01+02 together: ~$6.4M combined annual savings

Phase 3 (Month 6-12):  Agent 03 (KYC/CDD Perpetual)
  → Position as: "close the loop — investigations now trigger automatic CDD refresh"
  → Addresses the exam finding that always follows a strong SAR program:
    "your KYC is out of date on your high-risk customers"
```

### Path B: Fraud-First Institution (Digital Bank, Card Issuer, Credit Union with High CNP Volume)
**Lead with Agent 04 — real-time fraud is the CFO/COO's P&L problem, not a compliance issue.**

```
Phase 1 (Month 1-3):   Agent 04 (Real-Time Fraud Detection)
  → Most tangible P&L impact: fraud loss reduction is measurable within 60 days
  → Non-regulatory buyer: COO, VP Operations, Head of Fraud Management

Phase 2 (Month 3-9):   Agent 02 + 01 (TMS Enhancement → Investigation)
  → Natural upsell: "your fraud agent already detects structuring patterns —
    let's route those to your AML team automatically"
  → Connects fraud and AML programs, which regulators are increasingly requiring
```

### Path C: Wealth Management Firm or Bank Wealth Division
**Agent 05 is the entry point — revenue-generating, not compliance-driven.**

```
Phase 1 (Month 1-3):   Agent 05 (Wealth & RM Copilot)
  → Fastest executive buy-in: RM productivity is visible and feels good
  → Revenue angle: better-prepared RMs retain and grow AUM

Phase 2 (Month 3-9):   Agent 03 (KYC/CDD Perpetual)
  → Natural follow-on: "your RMs already benefit from better client intelligence —
    now automate the KYC refresh that triggers when their clients have risk events"

Phase 3 (Optional):    Agents 01 + 02
  → For wealth firms with trust/brokerage that also has AML obligations
```

### Path D: Broker-Dealer or Bank with Trading Desk
**Lead with Agent 07 — trading surveillance is the CCO's exam-readiness problem.**

```
Phase 1 (Month 1-3):   Agent 07 (Trading Surveillance)
  → Immediate FINRA 3110 WSP documentation value — every alert gets a disposition memo
  → Buyer: Chief Compliance Officer, Head of Trading Surveillance
  → 83% reduction in hours per HIGH alert; SAR automation for BSA-obligated BDs

Phase 2 (Month 3-6):   Agent 06 (Regulatory Change Management)
  → Natural follow-on: "your surveillance rules are now documented —
    let's automate tracking when FINRA or the CFTC change them"
  → When a spoofing rule or Reg SHO amendment drops, Agent 06 flags it
    and automatically assigns remediation tasks to Agent 07's owner

Phase 3 (Optional):    Agents 01 + 03
  → For BDs with AML/BSA obligations (most FINRA members)
  → Agent 07 insider trading flags feed directly to Agent 01 investigation workflow
```

### Path E: Full-Suite (Large Regional Bank or Super Community Bank)
**Lead with the platform vision — individual agents are the proof points.**

```
Phase 1: Agent 09 (Document Intelligence) — deploy first, horizontal value day 1
Phase 2: Agent 02 + POC on Agent 01 (AML loop, fastest visible ROI)
Phase 3: Agent 03 + Agent 04 (close the AML loop; add fraud prevention)
Phase 4: Agent 10 (Payments Compliance — builds on Agent 04 fraud detection)
Phase 5: Agent 08 (Credit Underwriting — lending business unit)
Phase 6: Agent 05 for wealth/private banking division (12-18 months)
Phase 7: Agent 06 for compliance operations team (15-18 months)
Phase 8: Agent 07 if institution has trading desk or broker-dealer subsidiary (18-24 months)
```

### Path F: Lending-Led Institution (Mortgage Bank, SBA Lender, CDFI, Auto Lender)
**Lead with Agent 08 — underwriting speed and ECOA compliance are the CFO's P&L and legal risk problems.**

```
Phase 1 (Month 1-3):   Agent 09 (Document Intelligence)
  → Deploy first: 1003 applications, pay stubs, and tax returns arrive as PDFs
  → Agent 09 converts them to structured JSON — Agent 08 gets clean data from day 1
  → 3-week payback on Agent 09 alone from manual re-keying elimination

Phase 2 (Month 2-4):   Agent 08 (Credit Underwriting)
  → Same-day underwriting decisions for the buyer: ops leaders, Chief Credit Officer
  → ECOA adverse action is Python — every denial has the correct reason codes
  → OFAC hard block: no loan can fund to a sanctioned person regardless of score

Phase 3 (Month 6-12):  Agent 03 (KYC/CDD Perpetual)
  → Natural follow-on: "you're already doing CIP on applicants — perpetuate that monitoring"
  → Connects lending KYC to BSA/AML program — addresses FDIC exam findings

Phase 4 (Optional):    Agent 10 (Payments Compliance)
  → For lenders processing ACH repayments, Reg E return disputes become automated
```

### Path G: Payments-Led Institution (Fintech, MSB, Prepaid Card Issuer, ACH Originator)
**Lead with Agent 10 — Reg E SLA failures and OFAC exposure are the most immediate regulatory risks.**

```
Phase 1 (Month 1-3):   Agent 10 (Payments Compliance)
  → Immediate Reg E SLA compliance: provisional credit deadlines, written notice drafting
  → OFAC screening is Python hard-block — no sanctioned payment can auto-resolve
  → Nacha return code validation eliminates late-return Nacha fines

Phase 2 (Month 2-4):   Agent 09 (Document Intelligence)
  → SWIFT MT103 and wire instructions arrive unstructured — Agent 09 converts them
  → Feeds directly into Agent 10's payment intake, eliminating re-keying for wires

Phase 3 (Month 6-12):  Agent 04 (Real-Time Fraud Detection)
  → Natural follow-on: "your disputes are managed — now prevent the fraud that creates them"
  → Agent 04 detects BEC and ATO in real-time; Agent 10 handles the regulatory response

Phase 4 (Optional):    Agent 01 (Financial Crime Investigation)
  → For MSBs with SAR filing obligations: Agent 10 flags SAR candidates, Agent 01 investigates
```

---

## Buyer Persona Map

Different personas care about different agents. Know who's in the room.

| Persona | Primary Pain | Lead With | Supporting ROI Framing |
|---------|-------------|-----------|----------------------|
| **BSA Officer / Chief Compliance Officer** | Regulatory risk, exam findings, SAR quality | Agent 01 + 02 | "examination-ready audit trail, FFIEC-aligned, SR 11-7 compliant" |
| **Financial Crime Ops Leader / VP AML** | Analyst capacity, queue management, FP rates | Agent 02 | "50% queue reduction, analysts focus on real alerts" |
| **CRO / Chief Risk Officer** | Holistic risk posture, model risk, regulatory posture | Full suite | "$22M+ annual savings, <6 month payback, regulatory controls as code" |
| **CIO / CTO** | Integration complexity, AWS-native, security | Architecture | "LangGraph DAG, ECS Fargate, Bedrock, Cognito + Okta/AD, Terraform IaC" |
| **CFO / COO** | Fraud losses, operational cost, headcount | Agent 04 + 02 | "65% fraud loss reduction, $4M AML labor savings — hard P&L impact" |
| **Head of Wealth / Private Banking** | RM productivity, Reg BI, client retention | Agent 05 | "10+ hrs/week per RM reclaimed, $3.5M annually (50 RMs)" |
| **Head of Fraud** | False positive rate, real-time detection, Reg E | Agent 04 | "40% FP reduction, sub-200ms detection, auto Reg E disclosure" |
| **Head of Trading Surveillance / Market Risk** | Alert volume, FINRA 3110 WSP, SAR obligations | Agent 07 | "83% reduction in hours/alert, auto disposition memos, FINRA exam-ready" |
| **Regulatory Change Manager / CCO (compliance ops)** | 200-400 changes/year, exam findings, policy gaps | Agent 06 | "92% time reduction per change, $849K–$1.5M/yr, FFIEC/SR 11-7 documented" |
| **Chief Credit Officer / Head of Lending** | Underwriting speed, ECOA compliance, fair lending | Agent 08 | "same-day decisions, ECOA adverse action Python-only, $1.8M–$3.4M/yr" |
| **VP Payments Operations / Head of Disputes** | Reg E SLA failures, Nacha fines, OFAC exposure | Agent 10 | "143 min → 12 min per dispute, 92% time reduction, auto Reg E notice" |
| **Document Operations / Loan Ops Leader** | PDF re-keying, OCR errors, 25+ document types | Agent 09 | "88% document processing time reduction, 3-week payback, suite multiplier" |
| **Internal Audit / Exam Prep** | Audit trail, model documentation, defensibility | All agents | "every decision is explainable, cited, and examination-ready" |

---

## Per-Agent Positioning Stories

### Agent 01 · Financial Crime Investigation Agent
**The headline:** *"Your investigators spend 40 hours on a SAR. We get that to 8 — with a better narrative."*

**The problem narrative:** A BSA-experienced investigator at a mid-size bank spends the majority of their day doing data collection: logging into the TMS, pulling transaction history from core banking, checking OFAC lists, searching news sources, mapping counterparty relationships. The actual judgment work — is this suspicious? Should I file? — takes 20% of their time. The rest is copy-paste and spreadsheets.

**The AI-native answer:** Every step of that data collection process becomes a node in a LangGraph state machine. The agent pulls from TMS, core banking, OFAC, adverse media, and network intelligence simultaneously, assembles the evidence, scores the risk across six weighted dimensions, and produces a FinCEN FIN-2014-G001-compliant SAR narrative draft — ready for BSA Officer review. The investigator doesn't start from scratch; they start from a complete, cited, structured dossier.

**What the BSA Officer hears:** The decision is still mine. The filing deadline is still my responsibility. But I'm reviewing a complete package instead of reviewing a half-assembled spreadsheet. I can focus on judgment, not data retrieval.

**The regulatory angle:** Examiners increasingly look for documented reasoning behind SAR filings. This agent produces a decision rationale with every case: regulatory citations, evidence inventory, composite risk score breakdown, investigator review steps. That documentation is the examiner answer.

**Discovery questions:**
- How long does your average SAR investigation take today?
- What percentage of that time is data gathering vs. actual analysis?
- How many SARs do you file per year, and at what cost per filing?
- What does your examiner feedback look like on SAR narrative quality?
- How do you currently document the reasoning behind a SAR filing for audit purposes?

---

### Agent 02 · AML/TMS Enhancement Agent
**The headline:** *"Half your analysts' day is noise. Fix that first — then everything else gets easier."*

**The problem narrative:** Transaction monitoring systems are tuned for recall, not precision. That's by design — missing a genuine suspicious transaction is worse than a false positive. The result: 85-95% of TMS alerts at most institutions are false positives. A team of 10 analysts reviewing 500 alerts per day is spending 450 of those analyst-hours on cases that should have been auto-closed.

**The AI-native answer:** Before any alert reaches an analyst, Agent 02 scores it across three dimensions: deterministic rule-based pre-filter (30%), LLM contextual analysis of the full customer and transaction context (50%), and historical false positive base rates for that rule and typology combination (20%). Alerts above 85% FP confidence are suppressed with a full justification narrative and flagged for BSA Officer 90-day review. Alerts below 15% FP are escalated immediately to Agent 01 as HIGH priority.

**The number that sells:** If your institution has 10 AML analysts at $80K fully-loaded, each spending 60% of their time on false positives, that's $2.88M in wasted labor. A 50% queue reduction reclaims half of that — before touching SAR quality, staffing levels, or any other metric.

**The regulatory guardrail story:** Suppressions are not silent drops. Every suppressed alert gets a justification narrative, an audit trail entry, and a 90-day review flag. PEP flags and high-risk geography + large wire + new account combinations are hard-coded escalations — they cannot be suppressed regardless of FP score. Examiners see a smaller queue with better documentation, not a black box.

**Discovery questions:**
- What is your current alert volume per day, and how many analysts review them?
- What is your estimated false positive rate?
- How do you document your alert disposition decisions today?
- Have you had any examiner findings related to alert management efficiency?
- Do you currently have any pre-queue filtering or AI-assisted triage?

---

### Agent 03 · KYC/CDD Perpetual Monitoring Agent
**The headline:** *"Your KYC is a point-in-time snapshot. Regulators want perpetual monitoring. Here's how you do it at scale."*

**The problem narrative:** Periodic KYC review — HIGH risk annual, MEDIUM risk every 2 years, LOW risk every 3 years — is operationally expensive and episodic by design. The real risk events happen between reviews: a customer gets adverse media coverage, their counterparty is added to the OFAC list, their beneficial owner changes. By the time the scheduled review comes around, the risk change is months old. Examiners have noticed.

**The AI-native answer:** Agent 03 runs a perpetual monitoring loop. Eleven trigger types — watchlist hit, SAR filed, adverse media, transaction spike, UBO change, new beneficial owner, risk model flag, and more — automatically initiate a CDD refresh workflow. The agent pulls the customer risk profile, checks document gaps, runs watchlist screening, searches adverse media, rescores across eight weighted risk factors, and determines routing: pass, EDD required, escalate, or exit. If EDD is required, it automatically generates the document checklist and drafts the relationship manager communication.

**The examiner story:** FFIEC BSA/AML Examination Manual guidance is explicit: institutions should have processes to detect changes in customer risk between scheduled reviews. This agent is that process — documented, auditable, examination-ready.

**The operational efficiency story:** A typical 5,000-customer portfolio generates 500-1,000 risk events per year that should trigger a CDD refresh. At 4-6 hours per routine refresh and 12-20 hours per EDD review, that's a significant staffing burden. A 90% reduction in manual hours means that burden becomes a background process, not a headcount driver.

**Discovery questions:**
- How do you currently handle off-cycle KYC reviews triggered by risk events?
- What is your current average time to complete a CDD refresh after a trigger event?
- Have you had any examiner findings related to your perpetual monitoring program?
- How many customers do you have in HIGH/MEDIUM/LOW risk tiers?
- How do you generate EDD document requests and communicate with relationship managers today?

---

### Agent 04 · Real-Time Fraud Detection Agent
**The headline:** *"You're losing $2.3M to fraud annually. Two-thirds of that is preventable — without declining more legitimate customers."*

**The problem narrative:** Fraud detection is a precision-recall tradeoff. Rule-based systems tuned to catch fraud also generate thousands of false positives — declined transactions that frustrate legitimate customers, increase chargeback rates, and damage relationships. Manual review teams are overwhelmed. Reg E provisional credit timelines are missed. And the sophisticated fraud patterns — account takeover, authorized push payment fraud, BEC — slip through because they don't match simple velocity rules.

**The AI-native answer:** Agent 04 runs a two-path architecture: a sub-200ms real-time path for immediate block/allow decisions using deterministic rules plus fast feature extraction, and an async enrichment path that runs device intelligence, behavioral analysis, and LLM contextual synthesis to build the full fraud picture. The composite score (rules 30%, LLM 50%, historical 20%) drives routing: Block (with automatic Reg E disclosure drafting), Step-Up Authentication (SMS OTP or push), Analyst Review, or Allow. Hard blocks for confirmed fraud IPs, Tor exit nodes, and OFAC-adjacent merchants are score-independent.

**The Reg E compliance angle:** For blocked transactions, the agent automatically drafts the Reg E adverse action disclosure with the correct 60-day dispute rights language, 10-business-day provisional credit timeline, and reason code. That eliminates one of the most common regulatory findings for digital banking operations.

**Discovery questions:**
- What is your current annual fraud loss rate, and how does it break down (CNP, ATO, APP, wire)?
- How many fraud alerts does your team review per day, and what is your false positive rate?
- How are you handling Reg E provisional credit timelines and dispute disclosures?
- Do you have real-time fraud scoring at the transaction level, or is it batch/rule-based?
- How quickly can your current system adapt to a new fraud pattern?

---

### Agent 05 · Wealth & RM Copilot
**The headline:** *"Your RMs spend 35-40% of their time on admin. Give that time back — and make the time they spend with clients more valuable."*

**The problem narrative:** A wealth management firm with 50 relationship managers is paying for 50 expert advisors and getting the output of 30 — because the other 30% of their capacity is consumed by meeting prep, proposal writing, portfolio review documents, and compliance documentation. Junior RMs produce inconsistent quality. Reg BI documentation is incomplete. HNW clients notice when their RM walks in underprepared.

**The AI-native answer:** Agent 05 is a copilot, not a replacement. The RM selects a client and a task — meeting prep, rebalancing proposal, investment proposal, portfolio review, client communication — and the agent pulls the full client context: CRM data, portfolio holdings, performance vs. IPS benchmarks, recent life events, market conditions relevant to the client's situation. It checks Reg BI suitability using Python (not LLM) — if the proposed recommendation doesn't fit the client's risk profile or IPS, it's blocked before a draft is ever created. For suitable recommendations, GPT-4o drafts the content: briefing, proposal, or letter. A FINRA 2210 compliance check catches prohibited language and missing disclaimers. The RM reviews, edits, and approves before anything goes to the client.

**The Reg BI documentation story:** Every recommendation the agent produces includes cost analysis, alternatives considered, and best-interest rationale — pre-populated for the RM to review. That's the Reg BI Care obligation, documented automatically.

**The revenue story:** Better-prepared RMs convert more opportunities. Faster proposal turnaround means more proposals. Clients who feel their RM knows their situation stay and refer others. The productivity gain (10+ hours/week per RM) compounds into revenue, not just cost savings.

**Discovery questions:**
- How much time do your RMs spend per week on administrative prep vs. client-facing activities?
- How do you currently ensure Reg BI documentation completeness across your RM team?
- What is your current proposal turnaround time, and how does that affect conversion rates?
- How do you handle client communications when there's a market event or life event?
- What does your current compliance review process look like for client-facing content?

---

### Agent 06 · Regulatory Change Management Agent
**The headline:** *"You receive 300 regulatory updates per year. Each one takes 8–40 hours to analyze manually. There's a better way."*

**The problem narrative:** A mid-size bank's 4-person compliance team is the last line of defense between a new OCC bulletin and a Matters Requiring Attention. They read the publication, search for the affected policies, write a gap analysis, draft a remediation plan, and notify the business units — all manually. At 26 hours per HIGH-impact change and 250 changes per year, the math doesn't work. Backlogs accumulate. Gaps get missed. Examiners ask about the same unclosed items year after year.

**The AI-native answer:** Agent 06 automates the entire regulatory change workflow as a 12-node LangGraph pipeline. It ingests changes from 9 regulatory authorities (FinCEN, OCC, Federal Reserve, FDIC, CFPB, SEC, FINRA, NCUA, FATF), validates the source, maps the regulatory domain to affected business lines and policies from the institution's policy registry, runs an LLM-powered gap analysis against current policies, scores impact with a Python composite model (SR 11-7 documented), and routes CRITICAL/HIGH changes to the CCO for HITL review. For approved changes, it drafts the remediation plan with tasks, owners, and deadlines — and sends tailored notifications to each stakeholder.

**The exam-readiness angle:** When an examiner asks "what did you do about the FinCEN AML Effectiveness final rule?" — the answer is a timestamped, CCO-approved gap analysis with a remediation plan showing every task status. That's the difference between a finding and a compliment.

**The SR 11-7 story:** The impact scoring model is Python-only — 5 weighted factors, fixed weights, no LLM in the routing decision. Weight changes require CCO authentication and are logged. That's the model risk management story examiners want to hear.

**Discovery questions:**
- How do you currently track and analyze regulatory changes from FinCEN, OCC, CFPB, and your other regulators?
- How many hours does your compliance team spend per regulatory change, and what's your current backlog?
- Have you had any examination findings related to regulatory change implementation gaps?
- How do you document your gap analysis and remediation planning for examiner review?
- Do you have a systematic process for notifying business units of their obligations when a new rule drops?

---

### Agent 07 · Trading Surveillance Agent
**The headline:** *"Your surveillance team reviews 800 alerts a month. 90% are false positives. The one real case looks like the other 19. Here's how you find it."*

**The problem narrative:** A broker-dealer's 6-analyst surveillance team receives 800+ alerts per month from NASDAQ SMARTS or NICE Actimize. Each alert requires order blotter review, trader history lookup, market context assessment, pattern analysis, investigation documentation, and a disposition memo — 2–6 hours of work per significant alert. The false positive rate sits at 90–97%. False positive fatigue is real: analysts become desensitized to alerts, and the one actual spoofing case in 20 looks identical to the other 19 until someone digs in. FINRA Rule 3110 WSP documentation requirements mean every alert disposition must be documented — adding 30–45 minutes of administrative burden to every review.

**The AI-native answer:** Agent 07 runs an 8-rule Python pattern detection engine across 11 alert types — layering/spoofing, front running, wash trading, insider trading, marking the close, short selling violations, and more. Pattern detection produces confidence scores, not LLM guesses. A 5-factor Python risk scoring model determines severity (CRITICAL/HIGH/MEDIUM/LOW) and whether HITL is required. The LLM then assembles market context from public sources, synthesizes an investigation narrative with supporting evidence and regulatory citations, and drafts the disposition memorandum. For CRITICAL/HIGH alerts, the compliance officer reviews the AI-assembled package — complete before they open the case — and submits a decision in one-third the time.

**The FINRA 3110 story:** Every alert produces a timestamped audit trail, a reviewer decision record, and a disposition memo — the three things FINRA examiners want to see during a supervision exam. For institutions that have received FINRA findings on inadequate surveillance documentation, Agent 07 directly closes the finding.

**The SAR story:** BSA obligations apply to most FINRA-member broker-dealers. When Agent 07 detects suspicious activity meeting the $5,000 BSA threshold (insider trading, wash trading, cross-market manipulation), it flags SAR consideration with a Python rule — not an LLM determination — and generates a draft SAR narrative following FinCEN's 5-W standard. The tipping-off prohibition (31 U.S.C. § 5318(g)(2)) is enforced at the LLM system prompt level — no output can alert the subject to the SAR.

**The hard rule story:** INSIDER_TRADING, INFORMATION_BARRIER_BREACH, and CROSS_MARKET_MANIPULATION always escalate to CRITICAL with mandatory HITL — regardless of the composite score. That's Python code, not a configurable threshold. No LLM can reason its way around it.

**Discovery questions:**
- What is your current monthly alert volume, and how many analysts review them?
- What is your estimated false positive rate, and how does your team document disposition decisions?
- Have you received any FINRA findings related to surveillance documentation or supervisory procedures?
- How do you currently handle SAR obligations for suspicious trading activity?
- Do you have documented written supervisory procedures covering each of your alert types and detection thresholds?
- How quickly can your current system adapt when FINRA or the CFTC introduce a new manipulation theory?

---

### Agent 08 · Credit Underwriting Agent
**The headline:** *"Your underwriters spend 3–5 days on a loan decision. Your competitors are offering same-day. AI can close that gap — with better ECOA documentation than you're producing manually."*

**The problem narrative:** A residential lending team processing 300 loans per month has a 3–5 day average underwriting cycle. Each loan requires a human underwriter to pull credit, compute DTI and LTV manually, verify documents against checklist, check OFAC, assess fair lending flags, and write the adverse action if declined — then route for supervisory review. That's 12–20 hours of underwriter time per loan. And every declined application is a regulatory exposure: ECOA requires a specific reason code (not "we looked at everything"), and the reason must be generated from the actual data — not a template. One fair lending examination finding can cost more than Agent 08's entire 3-year NPV.

**The AI-native answer:** Agent 08 runs the full underwriting workflow as a 12-node LangGraph pipeline covering all 12 major loan types: conventional, FHA, VA, USDA, jumbo, SBA 7(a)/504, HELOC, construction, bridge, commercial, and hard money. The 5-factor Python scoring model (credit 30%, DTI 25%, LTV 20%, cash flow 15%, collateral 10%) produces a composite score and tier. Hard decline rules — DTI > 50%, FICO < 580 conventional, Chapter 7 < 2 years — are Python constants that cannot be bypassed by any scoring path. OFAC is the strongest hard block: an OFAC hit returns `is_ofac_block=True` and sets the decision to DECLINE_HARD_BLOCK — no loan can fund to a sanctioned person regardless of score, and this is not reset-able by any application code path.

For adverse action, Agent 08 uses Python `frozensets` to map from scoring factors to the 12 ECOA-compliant reason codes (ECOA Regulation B § 202.9). The LLM drafts the adverse action letter; the reasons are determined by Python. That distinction — LLM drafts, Python decides — is what makes the output defensible in a fair lending exam.

**The Chief Credit Officer story:** Every underwriting decision includes: composite score with factor breakdown, loan type-specific threshold analysis, hard decline flags with regulatory basis, and a complete documentation checklist showing what was reviewed and what gaps remain. The underwriter doesn't assemble data — they evaluate a complete underwriting package and make the judgment call.

**The fair lending story:** HMDA census tract flagging surfaces geographic concentration risk. ECOA-prohibited factors are explicit in the system prompt: `RACE, COLOR, RELIGION, NATIONAL_ORIGIN, SEX, MARITAL_STATUS, AGE, FAMILIAL_STATUS` — Python monitors LLM outputs for prohibited signals. This is the fair lending documentation story regulators want to see.

**Discovery questions:**
- What is your current average underwriting cycle time, and how does that compare to your competitors?
- How do you currently generate ECOA adverse action reason codes — manually selected, or mapped from data?
- Have you had any HMDA or fair lending examination findings in the last 3 years?
- What loan types does your portfolio include, and do different product types have different underwriting workflows today?
- How do you currently handle OFAC screening for loan applicants — is it manual, or integrated into your core system?

---

### Agent 09 · Document Intelligence Agent
**The headline:** *"Every other agent in this suite processes structured data. Most of what arrives at your institution is unstructured — PDFs, scanned forms, SWIFT messages. Agent 09 solves that problem once, for the whole platform."*

**The problem narrative:** A loan operations team processing 300 applications per month spends 40–60 minutes per application re-keying data from PDFs into the core system: pulling borrower information from a 1003 application, extracting income figures from pay stubs and W-2s, transcribing bank statement balances, and capturing address information from identity documents. That's a 200–300 hour/month manually labor cost — before accounting for keying errors that cause downstream rework. The same problem exists in payments: wire operations teams re-key SWIFT MT103 fields into their payments platform. KYC teams manually enter information from passports and utility bills. Compliance teams extract data from regulatory notices.

**The AI-native answer:** Agent 09 processes 25 document types across 5 categories — lending (10 types: 1003, pay stub, W-2, bank statement, tax return, appraisal, title commitment, purchase agreement, credit report, PMI certificate), payments (3: SWIFT MT103, MT202COV, wire instruction), KYC (4: government ID, utility bill, business registration, beneficial ownership certification), capital markets (2: trade confirmation, account statement), and compliance (5: regulatory notice, consent order, CTR form, SAR form, KYC questionnaire).

The critical security design: PII masking happens in Python *before* any LLM API call. Seven regex patterns (SSN, account numbers, credit card numbers, dates of birth, driver's license numbers, passport numbers, and ABA routing numbers) are masked to `[REDACTED]` before text extraction reaches the LLM layer. The raw document bytes never appear in the LangGraph checkpoint database. This is not a logging filter — it's a pre-processing step that runs as the second node in the pipeline before any other processing begins.

For sensitive document types — SAR forms, CTR forms, government IDs, and consent orders — the agent has a `ALWAYS_HITL_DOCUMENT_TYPES` Python `frozenset`. These documents always pause for human review regardless of confidence score. A confident LLM extraction of a SAR form does not bypass the compliance officer — only a human can authorize processing a SAR form downstream.

**The suite multiplier story:** Deploy Agent 09 first. Every agent you deploy after it gets cleaner data: Agent 08 receives structured loan application JSON instead of re-keyed PDFs; Agent 10 receives structured SWIFT data instead of manually parsed wire instructions; Agent 03 receives structured KYC identity verification data instead of manually reviewed passport scans; Agent 07 receives structured trade confirmation data for surveillance analysis. The ROI on Agent 09 compounds across every specialist agent that follows it.

**The 3-week payback story:** At 300 loans/month with 40–60 minutes of manual data entry per application at $35/hour for a loan processor, the manual entry cost is $7,000–$10,500/month. Agent 09 eliminates ~88% of that — $6,160–$9,240/month savings. With implementation cost amortized over 3 months, payback is under 3 weeks.

**Discovery questions:**
- How many document types does your institution process, and how many require manual data entry today?
- What is your current loan processing volume, and how much time do processors spend per application on data re-keying?
- Do you have SWIFT MT103 or wire instruction documents that your payments team processes manually?
- How does your KYC team currently extract data from identity documents and business registrations?
- What is your current error rate in manually keyed data, and how often does that cause downstream rework?

---

### Agent 10 · Payments Compliance Agent
**The headline:** *"Your disputes team spends 143 minutes per ACH dispute. The regulatory SLA is 10 business days for provisional credit. Those two facts together are a compliance time bomb — and it's ticking on every unresolved dispute in your queue."*

**The problem narrative:** A payments compliance analyst processing ACH disputes today manually completes nine steps per case: look up the transaction in the core system, identify the return code and its Nacha return window, determine if Reg E applies (ACH consumer = yes; wire = no; business ACH = no), calculate the provisional credit deadline in business days, calculate the investigation deadline in calendar days, check whether the originating account is in a FATF high-risk country, draft the Reg E written notice, write the compliance memo, and log the case. That's 143 minutes per dispute — fully documented. Multiply by 5,000 disputes per year and the math becomes painful. Miss the 10-business-day provisional credit deadline once, and you have a Reg E violation. Miss it repeatedly and you have a pattern — the kind that generates CFPB examination findings and civil money penalties.

**The AI-native answer:** Agent 10 automates eight of those nine steps in 35 seconds. The regulatory determination path — Reg E applicability, Nacha return window, provisional credit obligation, OFAC country check, SLA deadline computation — is entirely deterministic Python. The LLM does not make any compliance determination. It drafts the Reg E written notice (12 CFR 1005.11(d)) and the compliance narrative for the reviewer — two tasks that currently consume 20–30 minutes of analyst time per case.

The `OFAC_SANCTIONED_COUNTRY_CODES` and `FATF_HIGH_RISK_COUNTRIES` are Python `frozenset` constants defined at module load time. They cannot be modified by any application code path — Python's `frozenset.add()` raises `TypeError`. This is enforced by the language itself, not by application logic. When a wire originates from Iran (country code `IR`), the agent sets risk tier to CRITICAL and routes to BSA Compliance with an OFAC hold — regardless of the amount, regardless of the customer's history, regardless of any other signal. That hard override is not configurable.

For NOC (Notification of Change) codes C01-C09, the agent auto-resolves and generates the originator notification. These administrative events — wrong account number format, incorrect routing number, account name change — don't need a compliance officer. They need a correctly formatted notification sent within 6 banking days. Agent 10 generates and routes that notification automatically, with the NOC correction details embedded and the originator's contact information populated from the fixture data.

**The Reg E timing story for compliance officers:** The agent computes SLA deadlines using Python UTC business-day arithmetic. The provisional credit deadline is 10 business days from the dispute receipt date. The investigation deadline is 45 calendar days (90 for new accounts, POS debit, or foreign-initiated transactions). These are not estimates — they are exact statutory deadlines computed for each specific dispute, displayed in the dashboard's SLA tracker with color-coded urgency. Green = >10 days remaining. Yellow = 5-10 days. Red = <5 days. The compliance manager sees the entire queue prioritized by SLA urgency.

**The BSA officer story for OFAC:** Every OFAC hit generates a blocking report flag with the 10-business-day SLA from OFAC's 31 CFR Part 501.604. The agent flags SAR candidates using Python threshold detection — `amount ≥ $5,000 AND suspicious_activity_indicators_present`. The tipping-off prohibition (31 U.S.C. § 5318(g)(2)) is enforced at the LLM system prompt level: the resolution narrative never discloses to the customer that a SAR may be filed.

**Discovery questions:**
- What is your current average dispute processing time, and how many disputes does your team handle per year?
- How do you currently track Reg E provisional credit and investigation deadlines — manually, or in your payments system?
- Have you had any CFPB or banking regulator findings related to Reg E timing or provisional credit?
- How do you handle OFAC screening for incoming and outgoing wires — is it automated or manual?
- What is your current Nacha return code error rate, and how do you handle NOC notifications to originators?
- Do you process international wires, and how do you screen for FATF high-risk jurisdictions today?

---

## Architecture Differentiation

When you're in a room with a CIO or solutions architect, these are the differentiators that matter.

### 1. Deterministic Routing — Not LLM Output
Every compliance routing decision in the suite is Python code, not LLM output. PEP flag → escalate. OFAC match → block. SAR deadline approaching → surface to BSA Officer. These are not configurable, not overridable by prompt engineering, and not dependent on model behavior. The LLM's role is to draft narratives and assemble evidence — the routing decisions are deterministic.

**Why this matters to regulators:** SR 11-7 requires that model risk be documented and bounded. A model that makes the routing decision is a different risk profile than a model that drafts a narrative. This architecture separates those concerns cleanly.

### 2. Human-in-the-Loop as a First-Class Architectural Primitive
LangGraph's interrupt mechanism means human review gates are not UI add-ons — they are nodes in the graph. Every agent in the suite has at least one mandatory human approval gate before any record is filed, any risk rating is changed, or any client communication is sent. This is the "AI drafts; humans decide" principle implemented at the platform level.

### 3. AWS-Native, Regulation-Grade Architecture
- **Data residency**: AWS Bedrock keeps all inference in-account. Customer data never leaves the customer's AWS environment for LLM processing.
- **Audit trail**: DynamoDB append-only audit log with IAM-enforced immutability (UpdateItem and DeleteItem denied). Every decision, every tool call, every human override is recorded.
- **Retention**: S3 Object Lock (WORM, COMPLIANCE mode) for SAR documents. 5-year BSA retention enforced at the storage layer, not just application policy.
- **Identity**: Cognito + Okta SAML federation. No user credentials in the application. BSA roles derived from Active Directory group membership. Offboarding an investigator means removing them from AD — no Cognito admin action needed.

### 4. MCP Authentication Gateway
All external API calls (TMS, watchlist, adverse media, core banking, network intelligence) flow through a FastAPI MCP Auth Gateway that validates Cognito JWTs (backed by Okta/AD SAML), enforces role-based tool authorization, rate-limits per customer and tool, and writes an immutable audit log entry for every outbound call. This is the compliance-grade integration pattern — examiners see exactly what data was queried and by whom.

### 5. LangGraph State Machine — Reproducible, Auditable, Testable
Same alert, same customer, same investigation steps — every time. Every node transition is loggable. Each node is a pure function that can be unit-tested independently. This is what "explainable AI" looks like in practice for regulated use cases.

---

## Competitive Positioning

### vs. Traditional Compliance Technology Vendors (e.g., Actimize NICE, Oracle FCCM, SAS AML)

| Dimension | Traditional Vendors | This Suite |
|-----------|---------------------|-----------|
| Deployment | 12-18 month enterprise implementation | Docker + Terraform, POC in days |
| Customization | Professional services engagement | Open Python/LangGraph code |
| LLM integration | Bolted on (if at all) | Native — LLM is the core reasoning engine |
| Pricing model | Per-seat / enterprise license | AWS infrastructure cost (~$1,889/month) |
| Regulatory documentation | Vendor-provided (generic) | Generated per-decision, institution-specific |
| Human-in-the-loop | Workflow tool | First-class graph primitive |

**Positioning:** "The enterprise vendors are the system of record. We are the AI layer that makes your analysts 5x more productive without replacing what you already have."

### vs. Fintech Point Solutions (e.g., Resistant AI, Unit21, Hawk AI)

| Dimension | Fintech Point Solutions | This Suite |
|-----------|------------------------|-----------|
| Scope | Single use case (FP reduction OR investigation OR KYC) | End-to-end platform, 10 use cases |
| Architecture | SaaS / shared infrastructure | Customer VPC, fully isolated |
| Data residency | Vendor-managed | Customer-controlled |
| Integration | API-first, modern | MCP pattern, integrates with legacy TMS |
| Transparency | Black box scoring | Full explainability, factor-by-factor |

**Positioning:** "Point solutions solve one problem. This solves the whole financial crime workflow — and your data stays in your house."

### vs. Build-Your-Own (Internal AI/Data Teams)

| Dimension | Build Your Own | This Suite |
|-----------|----------------|-----------|
| Time to value | 12-24 months | POC in days, production in 3-6 months |
| Regulatory controls | Must be designed from scratch | Embedded in every agent |
| LangGraph expertise | Must be hired or trained | Pre-built, documented, tested |
| Maintenance burden | Full internal ownership | Clear architecture, easy to extend |

**Positioning:** "Your data team is valuable — use them to customize and extend this platform, not to build the regulatory controls from scratch."

---

## Common Objections and Responses

**"We're concerned about putting sensitive customer data through an LLM."**
> AWS Bedrock runs inference within your AWS account. Customer data is not sent to Anthropic or any third party. The VPC endpoint for Bedrock means traffic never leaves AWS infrastructure. Your data residency requirements are met.

**"How does this integrate with our existing TMS (Actimize/Verafin/NICE)?"**
> Each agent has a dedicated MCP Connector for the major TMS platforms. The TMS remains your system of record — the agent reads from it (alert details, transaction history) and writes back (alert disposition). Your TMS configuration and tuning are unchanged.

**"What happens if the LLM makes a wrong recommendation?"**
> The LLM never makes a routing decision. It drafts narratives and surfaces evidence. The routing logic is deterministic Python — thresholds, hard rules for PEP/OFAC, 30-day SAR deadlines. Every routing decision has a human review gate before action is taken. SR 11-7 documentation is generated with every model output.

**"Our BSA examiners will ask about model risk management."**
> Every scoring model in the suite includes: factor-by-factor score breakdowns with weights documented, threshold rationale, human override capability, and an audit trail linking every model output to its inputs. The regulatory-compliance.md document in each agent provides a citation-level mapping to BSA, FinCEN, OFAC, FATF, and SR 11-7 requirements.

**"We already have an AI vendor — can this co-exist?"**
> Yes. The suite is designed as an orchestration layer over your existing systems. It reads from your TMS, enriches with your KYC data, and writes back to your case management system. It can use AWS Bedrock (Claude), OpenAI, or Azure OpenAI — configurable per customer.

**"How do we handle access control with our existing Okta/AD setup?"**
> No additional identity infrastructure needed. Cognito federates with your existing Okta SAML configuration. Users authenticate against Okta (which checks AD group membership), Cognito issues a JWT, and that JWT carries the BSA role claim. Adding an investigator means adding them to the correct AD group — IT can do that today.

---

## Demo Flow Recommendations

### Agent 02 — The Fastest Demo
1. Open the Live Scoring Queue tab — load the demo alert batch (500 alerts pre-loaded)
2. Run the full scoring pipeline — watch the live node execution
3. Show the routing outcomes: ~50% suppressed, breakdown of downgrade/pass-through/escalate
4. Open one SUPPRESS decision — show the justification narrative and the factor-by-factor score
5. Open the FP Reduction Metrics tab — show the ROI calculation live
6. Show the Suppression Audit tab — point out the 90-day BSA Officer review queue
7. Change a suppression to an escalation via human override — show the audit trail update

**Key moment:** Show the PEP flag → mandatory ESCALATE override. "See this? Even if the FP score says 92%, a PEP flag sends it to the investigation team. That's not configurable — it's code."

### Agent 01 — The Deep Demo
1. Start with an escalated alert from Agent 02 (HIGH priority, FP score < 15%)
2. Run the full 11-step investigation workflow — let the pipeline run live
3. Show each node result: customer profile, transactions (structuring pattern visible), OFAC hit, adverse media, network map
4. Show the composite risk score — 6 factors, weights, 0-100 scale
5. Open the SAR narrative draft — show the FinCEN FIN-2014-G001 structure
6. Walk through the BSA Officer review gate — approve, modify a sentence, finalize
7. Show the audit trail — every node, every data source, every decision

**Key moment:** Show the network graph visualization — counterparty mapping with shell company indicators. "This took investigators 3-4 hours to build manually. The agent built it in 45 seconds."

### Agent 04 — The Real-Time Demo
1. Start with the account takeover scenario (impossible travel + new device)
2. Run the two-path pipeline — point out the real-time path vs. async enrichment
3. Show the composite score gauge (88/100 → BLOCK)
4. Open the Decision & Evidence tab — show the LLM fraud hypothesis and Reg E draft
5. Switch to the elder financial exploitation scenario — show how the routing changes (different fraud type, different evidence weight)
6. Show the analyst review panel — how an analyst reviews a flagged (score 40-64) transaction
7. Show the audit trail with GLBA-compliant hashed IP and device data

**Key moment:** Show the auto-generated Reg E disclosure. "When you block a transaction, the disclosure is drafted automatically with the correct statutory language. Your compliance team doesn't write it. Your operations team doesn't chase it down."

### Agent 05 — The Executive Demo
1. Select Margaret Chen (the widowed retiree with RMD deadline)
2. Select MEETING_PREP as the request type
3. Run the full copilot pipeline
4. Show the client profile lookup — portfolio, IPS, life events, RMD status
5. Show the suitability check — Python determination, not LLM
6. Show the briefing output — talking points with Margaret's specific situation
7. Run an INVESTMENT_PROPOSAL for David Okafor (the business owner with alternatives underweight)
8. Show the Reg BI rationale — cost analysis, alternatives considered, best-interest documentation
9. Show the RM approval gate — how the RM reviews and approves before anything goes to the client

**Key moment:** Show the suitability block. "If I try to propose something that doesn't fit the client's IPS or risk profile, the agent blocks it before the draft is created — not after. The RM doesn't receive a proposal they'd have to reject."

### Agent 06 — The Compliance Operations Demo
1. Open the Regulatory Feed tab — show the change register with 3 pre-loaded changes
2. Submit a new change: paste in a FinCEN final rule summary (AML Effectiveness rule)
3. Run the pipeline — watch scope determination, policy mapping, and gap analysis execute
4. Open Impact Analysis — show the 5-factor score breakdown chart (bar chart by component)
5. Show the policy mapping table — which of the institution's 12 policies are affected and why
6. HITL gate triggers for this HIGH impact change — submit the CCO review decision
7. Open Remediation Tracker — show the auto-generated task list with owners and deadlines
8. Open Audit Trail — walk through the timestamped entries per node

**Key moment:** Show the compliance window adequacy flag. "This change has a 60-day implementation window but HIGH complexity. The agent automatically escalated the impact tier and triggered HITL — even though the raw score would have been MEDIUM. That's the kind of judgment call your compliance team makes manually today."

### Agent 07 — The Surveillance Demo
1. Open the Alert Queue tab — show the 3 pre-loaded alerts with severity distribution chart
2. Submit a new alert: layering/spoofing, GLOBEX instrument, $3.5M notional, 87% cancel rate
3. Run the pipeline — watch pattern detection, market context, and risk scoring execute in sequence
4. Open Case Investigation — show the risk score breakdown (5 factors, bar chart)
5. Show detected patterns with confidence scores — layering confirmed at 88%
6. HITL gate triggers (HIGH severity) — walk through the compliance officer review panel
7. Submit INVESTIGATE decision — workflow resumes and generates investigation narrative
8. Open Disposition tab — show the disposition memo and SAR consideration flag
9. Open Audit Trail — show every node entry with regulatory basis citations

**Key moment:** Show the insider trading hard override. Pull up the pre-loaded insider trading alert (ACME Corporation, restricted list hit). "See this? The score is 0.93 — already CRITICAL. But even if it weren't, INSIDER_TRADING is hard-coded to CRITICAL with mandatory HITL. That's not a threshold we can configure. It's a Python constant. No prompt, no model version, no configuration change can remove that gate."

### Agent 08 — The Lending Demo
1. Open the Underwriting Queue tab — show the 3 pre-loaded loan applications with different loan types (conventional, FHA, SBA 7(a))
2. Submit a new conventional loan application: $425,000 loan, 740 FICO, 38% DTI, 80% LTV, single-family primary residence
3. Run the full pipeline — watch credit analysis, DTI/LTV scoring, OFAC check, fair lending flags execute in sequence
4. Open the Decision tab — show the composite score (5 factors, bar chart), loan type parameters, and underwriter recommendation
5. Switch to the FHA demo scenario — show how FHA-specific thresholds differ from conventional (different FICO floor, different MIP requirements)
6. Submit the SBA 7(a) scenario — show how cash flow analysis and business financials enter the scoring model
7. Show an adverse action scenario: manually push DTI above 50% — watch the hard decline trigger
8. Open the Adverse Action tab — show the Python-generated ECOA reason codes and the LLM-drafted adverse action letter
9. Walk through the underwriter review gate — approve with modification, show the audit trail update

**Key moment:** Show the OFAC hard block. Create a scenario where the applicant name matches a sanctioned individual. "See this? The score is irrelevant. OFAC hit means DECLINE_HARD_BLOCK — Python constant, immutable. No underwriter can override this in the application. Any override requires a OFAC compliance officer to clear the match through OFAC's process."

### Agent 09 — The Document Intelligence Demo
1. Open the Document Processing tab — show the 4 pre-loaded document scenarios with different types
2. Upload a sample 1003 loan application PDF (or use the pre-loaded scenario)
3. Run the pipeline — watch text extraction, PII masking, classification, field extraction, and confidence scoring execute
4. Open the Extracted Fields tab — show the 47 fields extracted from the 1003, with confidence scores per field
5. Show the PII masking panel — the original text with SSN, account number, and DOB as `[REDACTED]`
6. Switch to the SWIFT MT103 scenario — show how MT103 fields (BIC, IBAN, amount, value date, remittance info) are extracted into structured JSON
7. Run the government ID scenario (passport) — show how it triggers the ALWAYS_HITL_DOCUMENT_TYPES gate
8. Show the Structured Output tab — the JSON that flows to downstream agents (Agent 08, Agent 10, Agent 03)
9. Open the Audit Trail — show the SHA-256 document hash and timestamp for tamper detection

**Key moment:** Show the confidence-based routing. Pull up a low-quality scanned form with a confidence score of 0.52 (LOW tier). "Watch what happens — the agent doesn't guess. Below 0.65 confidence, it routes to the HITL queue for human review. Your operations team reviews the questionable extraction, not the certain one. That's where their time is most valuable."

### Agent 10 — The Payments Compliance Demo
1. Open the Submit tab — show the 4 pre-loaded payment scenarios (ACH R10, OFAC Iran wire, BEC wire, NOC C01)
2. Load the ACH R10 scenario: consumer ACH PPD, $1,247.50, R10 unauthorized return
3. Run the pipeline — watch sanctions screening, Nacha validation, Reg E assessment, dispute analysis, and risk scoring execute
4. Open the Findings tab — show the Reg E assessment: applicable (consumer ACH), 10-business-day provisional credit deadline, 45-day investigation deadline, risk tier MEDIUM
5. Show the SLA Tracker panel — color-coded urgency for each deadline type
6. Walk through the HITL gate (R10 unauthorized triggers HITL) — submit APPROVE decision, workflow resumes
7. Open the Reg E & Notices tab — show the auto-drafted Reg E written notice with the correct statutory language (12 CFR 1005.11(d))
8. Now load the OFAC Iran wire scenario: FEDWIRE $425,000, beneficiary bank in Tehran
9. Run the pipeline — watch the OFAC hard block trigger at node 2 (sanctions_screening)
10. Show the Compliance Findings — CRITICAL tier, OFAC_HOLD event, BSA routing, blocking report SLA flagged
11. Open the Audit Trail — show every node entry including the exact `OFAC_SANCTIONED_COUNTRY_CODES` frozenset check

**Key moment:** Show the NOC auto-resolve. Load the ACH NOC C01 scenario ($4,250, administrative routing correction). "This doesn't need a compliance officer. It's a Nacha administrative notification — wrong routing number format. The agent identifies C01, auto-resolves the event, generates the originator notification with the correction details, and logs it. The compliance team sees a closed case with full documentation. Zero human time required."

---

## ROI Summary by Institution Profile

### Community Bank (Assets $1B–$5B)
| Use Case | Annual Savings | Notes |
|----------|---------------|-------|
| Agent 09 (Document Intelligence) | $450K–$700K | Loan ops + KYC doc processing; suite multiplier |
| Agent 02 (TMS Enhancement) | $1.2M–$2.0M | 4-6 analyst team |
| Agent 01 (Financial Crime Investigation) | $800K–$1.5M | 300-600 SARs/year |
| Agent 03 (KYC/CDD Perpetual) | $500K–$1.0M | 2,000-4,000 customer reviews |
| Agent 04 (Fraud Detection) | $600K–$1.2M | Regional card/ACH volume |
| Agent 10 (Payments Compliance) | $400K–$800K | 2,000-3,000 ACH disputes/year |
| Agent 08 (Credit Underwriting) | $600K–$1.2M | 100-200 loans/month |
| Agent 06 (Regulatory Change Mgmt) | $400K–$700K | 2 compliance analysts |
| **Full Suite** | **$5.0M–$9.1M** | Payback < 5 months |

### Regional Bank (Assets $5B–$50B)
| Use Case | Annual Savings | Notes |
|----------|---------------|-------|
| Agent 09 (Document Intelligence) | $1.0M–$1.9M | High loan/KYC/SWIFT volume; suite multiplier |
| Agent 02 (TMS Enhancement) | $2.5M–$5.0M | 8-15 analyst team |
| Agent 01 (Financial Crime Investigation) | $1.5M–$3.0M | 600-1,500 SARs/year |
| Agent 03 (KYC/CDD Perpetual) | $1.0M–$2.5M | 8,000-20,000 customer reviews |
| Agent 04 (Fraud Detection) | $1.5M–$3.5M | Higher transaction volumes |
| Agent 10 (Payments Compliance) | $713K–$1.95M | 5,000+ ACH/wire disputes |
| Agent 08 (Credit Underwriting) | $1.8M–$3.4M | 300+ loans/month |
| Agent 05 (Wealth Copilot) | $1.5M–$4.0M | 20-50 RMs |
| Agent 06 (Regulatory Change Mgmt) | $849K–$1.5M | 4-analyst compliance team |
| Agent 07 (Trading Surveillance) | $1.5M–$3.0M | Regional trading desk, 3-4 analysts |
| **Full Suite** | **$12.9M–$29.8M** | Payback < 3 months |

### Credit Union (Assets $500M–$5B)
| Use Case | Annual Savings | Notes |
|----------|---------------|-------|
| Agent 09 (Document Intelligence) | $300K–$600K | Loan and member doc processing |
| Agent 02 (TMS Enhancement) | $600K–$1.5M | Smaller alert volumes, fewer analysts |
| Agent 04 (Fraud Detection) | $400K–$1.0M | Card and ACH fraud primary concerns |
| Agent 10 (Payments Compliance) | $300K–$700K | ACH dispute automation; Reg E SLA compliance |
| Agent 03 (KYC/CDD Perpetual) | $300K–$800K | Member reviews |
| Agent 06 (Regulatory Change Mgmt) | $300K–$600K | 1-2 compliance staff |
| **Priority Suite** | **$2.2M–$5.2M** | Agents 09 + 02 + 04 + 10 + 03 + 06 |

### Mortgage Bank / SBA Lender / CDFI
| Use Case | Annual Savings | Notes |
|----------|---------------|-------|
| Agent 09 (Document Intelligence) | $700K–$1.2M | High-volume PDF loan application processing |
| Agent 08 (Credit Underwriting) | $1.8M–$3.4M | 300+ loans/month; ECOA compliance |
| Agent 10 (Payments Compliance) | $300K–$600K | ACH repayment disputes |
| Agent 03 (KYC/CDD Perpetual) | $400K–$900K | Borrower CIP + CDD monitoring |
| Agent 06 (Regulatory Change Mgmt) | $400K–$700K | ECOA/HMDA/Reg Z rule tracking |
| **Priority Suite** | **$3.6M–$6.8M** | Payback < 4 months |

### Broker-Dealer / Bank with Trading Desk
| Use Case | Annual Savings | Notes |
|----------|---------------|-------|
| Agent 07 (Trading Surveillance) | $2.2M–$3.1M | 6-analyst surveillance team, 800 alerts/month |
| Agent 06 (Regulatory Change Mgmt) | $849K–$1.5M | FINRA/SEC rule change volume |
| Agent 01 (Financial Crime Investigation) | $800K–$1.5M | BSA/SAR cross-referrals from Agent 07 |
| Agent 02 (TMS Enhancement) | $1.5M–$3.0M | Trading-related AML alerts |
| Agent 09 (Document Intelligence) | $400K–$800K | Trade confirmation and account statement processing |
| **Full Suite** | **$5.8M–$9.9M** | Payback < 3 months |

### Fintech / MSB / Prepaid Card Issuer
| Use Case | Annual Savings | Notes |
|----------|---------------|-------|
| Agent 10 (Payments Compliance) | $713K–$1.95M | High dispute volume; Reg E and Nacha compliance |
| Agent 09 (Document Intelligence) | $500K–$900K | SWIFT, wire instructions, KYC docs |
| Agent 04 (Fraud Detection) | $800K–$2.0M | CNP/ATO/APP fraud at digital velocity |
| Agent 01 (Financial Crime Investigation) | $600K–$1.2M | SAR filing for MSB BSA obligations |
| Agent 06 (Regulatory Change Mgmt) | $300K–$600K | Prepaid Rule, CFPB, FinCEN rule tracking |
| **Priority Suite** | **$2.9M–$6.7M** | Payback < 4 months |

---

## Infrastructure Cost Reference

All ten agents share the same AWS deployment pattern and common infrastructure layer. Per-customer monthly AWS cost (mid-size bank, full 10-agent suite):

| Component | Cost | Notes |
|-----------|------|-------|
| ECS Fargate (UI tasks — 10 Streamlit frontends) | ~$250–$350 | 256 CPU / 512 MB per agent UI task |
| ECS Fargate (Agent workers + MCP gateways) | ~$500–$650 | LangGraph worker tasks, MCP Auth Gateway |
| RDS Aurora PostgreSQL (shared or per-agent) | ~$300–$600 | LangGraph checkpoint store; shared cluster saves cost |
| DynamoDB (audit trails — all 10 agents) | ~$45 | Append-only audit log; low write unit cost |
| S3 (documents, SAR records, loan files, archives) | ~$30–$50 | Agent 09 document cache; Agent 08 loan files |
| SQS FIFO + Lambda | ~$35 | Agent 06 EventBridge feed; Agent 07 alert ingestor |
| Textract (Agent 09 OCR for scanned documents) | ~$50–$200 | Scales with document volume; ~$1.50/1,000 pages |
| Secrets Manager + KMS (all agents) | ~$30 | KMS CMK annual rotation; Secrets Manager API calls |
| AWS Bedrock (Claude — inference, primary cost driver) | ~$1,200–$5,000 | Haiku for triage nodes; Sonnet for SAR/narrative/underwriting |
| Security, networking, monitoring (WAF, CloudTrail, GuardDuty) | ~$200 | Fixed; scales modestly with agent count |
| **Total** | **~$2,640–$7,130/month** | Scales with usage, not seats |

**Cost optimization guidance:**
- **Claude Haiku** for classification, routing, and pre-scoring nodes (~10x cheaper than Sonnet) — use for Agent 09 document classification, Agent 02 FP pre-scoring, Agent 10 dispute triage
- **Claude Sonnet** for SAR narrative drafting (Agent 01), investment proposals (Agent 05), surveillance disposition memos (Agent 07), adverse action letters (Agent 08), Reg E notices (Agent 10)
- **Provisioned throughput** available for Agent 04 (high-frequency real-time fraud scoring) — contact Anthropic for pricing
- **Shared Aurora cluster** across all 10 agents cuts RDS cost vs. per-agent instances by ~60%

**Incremental cost for Agents 08-10 vs. Agents 01-07 only:** ~$130–$300/month fixed (Fargate tasks + Textract baseline); variable cost scales with loan volume (Agent 08 and 09), document volume (Agent 09), and dispute volume (Agent 10).

---

## Pre-Engagement Technical Checklist

Before a customer POC, collect the following:

### Identity / Authentication
- [ ] Does the customer use Okta, Azure AD, or another SAML 2.0 IdP?
- [ ] What Active Directory groups map to BSA Officer, Investigator, Auditor roles?
- [ ] What MFA method does the customer enforce (Okta Verify, FIDO2, TOTP)?

### TMS / Core Banking
- [ ] Which TMS platform? (Actimize, Verafin, NICE Actimize, Oracle Mantas, Nasdaq Verafin)
- [ ] Does the TMS support webhook alert streaming, or do we need scheduled polling?
- [ ] Which core banking platform? (FIS, Fiserv, Jack Henry, Temenos)
- [ ] API documentation available? OAuth 2.0 or API Key authentication?

### Third-Party Data Vendors
- [ ] Which watchlist screening vendor? (Refinitiv World-Check, LexisNexis Bridger, ComplyAdvantage)
- [ ] Which adverse media vendor? (Dow Jones, LexisNexis Nexis+)
- [ ] Network intelligence? (Sayari, Quantexa, OpenCorporates — or none)

### AWS Environment
- [ ] Does the customer have an existing AWS organization? Preferred region?
- [ ] Separate AWS account per application, or shared account? (Recommend separate)
- [ ] Does the customer use AWS Control Tower or Landing Zone? Any SCPs to be aware of?
- [ ] Network connectivity method to on-premise systems? (VPN, Direct Connect, PrivateLink)

### Compliance / Regulatory
- [ ] Most recent BSA examination date and any relevant findings?
- [ ] Current SAR volume per year?
- [ ] Current TMS alert volume and estimated false positive rate?
- [ ] Any pending regulatory actions or consent orders that affect timeline?

### Trading Surveillance (Agent 07 — Broker-Dealers and Banks with Trading Desks)
- [ ] FINRA member firm? Which FINRA district? Most recent FINRA examination date?
- [ ] Current surveillance platform? (NASDAQ SMARTS, NICE Actimize, Bloomberg Compliance, none)
- [ ] Monthly alert volume and breakdown by alert type?
- [ ] Number of surveillance analysts on the team?
- [ ] Asset classes traded: equities, fixed income, derivatives, FX, commodities, crypto?
- [ ] Any open FINRA or SEC investigations related to surveillance gaps?
- [ ] Who has access to surveillance data today — and who explicitly must not?

### Regulatory Change Management (Agent 06 — All Institution Types)
- [ ] How does the institution currently track regulatory changes? (Email newsletters, LexisNexis, manual monitoring)
- [ ] How many policies are in scope for BSA/AML/compliance? Rough document count?
- [ ] Who owns the regulatory change process? CCO, BSA Officer, or dedicated compliance team?
- [ ] What is the typical implementation window for regulatory changes at this institution?

### Trading Surveillance (Agent 07 — Broker-Dealers and Banks with Trading Desks)
- [ ] FINRA member firm? Which FINRA district? Most recent FINRA examination date?
- [ ] Current surveillance platform? (NASDAQ SMARTS, NICE Actimize, Bloomberg Compliance, none)
- [ ] Monthly alert volume and breakdown by alert type?
- [ ] Number of surveillance analysts on the team?
- [ ] Asset classes traded: equities, fixed income, derivatives, FX, commodities, crypto?
- [ ] Any open FINRA or SEC investigations related to surveillance gaps?
- [ ] Who has access to surveillance data today — and who explicitly must not?

### Credit Underwriting (Agent 08 — Banks, Credit Unions, Mortgage Companies, SBA Lenders)
- [ ] What loan types does the institution originate? (Conventional, FHA, VA, USDA, jumbo, SBA, HELOC, construction, bridge, commercial)
- [ ] Monthly origination volume and average loan size?
- [ ] Current loan origination system? (Encompass, Byte, Calyx, MeridianLink, or custom)
- [ ] How are ECOA adverse action reason codes currently generated — manually, from LOS templates, or from scoring data?
- [ ] Most recent HMDA/CRA examination date and any fair lending findings?
- [ ] How is OFAC screening currently performed for loan applicants? (Integrated in LOS, manual, third-party vendor)
- [ ] What underwriting policy documentation exists (underwriting guidelines document, credit policy manual)?
- [ ] SBA lender? (SBA 7(a)/504 program requires separate underwriting standards — confirm scope)

### Document Intelligence (Agent 09 — All Institution Types)
- [ ] What document types does the institution process in highest volume? (Loan applications, SWIFT messages, ID documents, regulatory filings)
- [ ] How are documents currently digitized — scanning workflow, email, portal upload?
- [ ] What OCR or document processing tools are currently in use? (Kofax, ABBYY, Adobe, none)
- [ ] Average document volume per month by type?
- [ ] Where does manually keyed data currently go? (LOS, core banking system, CRM, spreadsheet)
- [ ] What is the current downstream rework rate from manual keying errors?
- [ ] Are SWIFT MT103/MT202 wire instructions processed by a payments team separately from loan documents? (Helps scope Agent 09 deployment phases)
- [ ] Does the institution have a document retention policy that would affect Agent 09's S3 storage requirements?

### Payments Compliance (Agent 10 — Banks, Credit Unions, Fintechs, MSBs, Prepaid Issuers)
- [ ] Annual ACH dispute volume? Breakdown by return code type (unauthorized vs. administrative vs. insufficient funds)?
- [ ] Current dispute management system? (Manual spreadsheet, CRM case, payment platform built-in)
- [ ] How are Reg E provisional credit deadlines currently tracked? (Manual calendar, payment system SLA, dedicated tracker)
- [ ] Most recent Reg E-related examination finding or CFPB inquiry?
- [ ] OFAC screening vendor for wire transactions? (Fircosoft, Accuity, ComplyAdvantage, none)
- [ ] International wire volume per month and top origination/destination country pairs?
- [ ] How are Nacha NOC notifications (C01-C09) currently handled and sent to originators?
- [ ] Does the institution originate ACH transactions as ODFI? (Affects scope of Nacha return code exposure)
- [ ] Any Nacha audit findings related to return code timelines or unauthorized return handling?
- [ ] Does the institution issue prepaid cards? (CFPB Prepaid Rule applies — confirms Reg E scope)
