# Financial Services AI Agent Suite — Solution Field Guide
### A Practitioner's Guide to Positioning, Engagement, and Deployment

> **Audience:** Solutions architects, technical account managers, and pre-sales engineers engaging with financial institutions on AI-driven compliance and revenue modernization.

---

## The Platform Story: One Problem, Five Entry Points

Financial institutions lose **$274 billion annually** to the combined burden of financial crime compliance, KYC overhead, fraud losses, and RM administrative drag. That number isn't going away — regulatory requirements are tightening, not loosening.

The status quo response is more analysts, more tools, and more complexity. The AI-native response is different: **let AI handle the high-volume, low-judgment work so your best people can focus on the 5% of decisions that actually require human expertise.**

This suite is five purpose-built AI agents, each solving one high-cost problem. They are designed to be deployed independently — each delivers ROI on its own — but they share a common architecture, a common data model, and common regulatory controls. When deployed together, they form a closed-loop platform where every agent reinforces the others.

---

## The Five-Agent Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    Financial Services AI Agent Suite                             │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │  FINANCIAL CRIME LOOP (AML)                                              │   │
│  │                                                                          │   │
│  │  [02 · TMS Enhancement] ──────► [01 · Financial Crime Investigation]    │   │
│  │   Pre-queue FP suppression         Alert-to-SAR workflow                │   │
│  │   ~50% queue reduction             80% reduction in hours/SAR           │   │
│  │                          ▲                    │                         │   │
│  │                          │                    ▼                         │   │
│  │  [03 · KYC/CDD Perpetual]◄──────── Risk events feed back to KYC        │   │
│  │   Triggered CDD refresh                                                  │   │
│  │   90% reduction in manual hours                                         │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │  REAL-TIME FRAUD LOOP                                                    │   │
│  │                                                                          │   │
│  │  [04 · Real-Time Fraud Detection]                                        │   │
│  │   Sub-200ms payment fraud prevention                                    │   │
│  │   65% fraud loss reduction · Reg E automation                           │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │  CLIENT INTELLIGENCE LAYER                                               │   │
│  │                                                                          │   │
│  │  [05 · Wealth & RM Copilot]                                              │   │
│  │   RM productivity + Reg BI compliance                                   │   │
│  │   10+ hrs/week per RM reclaimed · $3.5M annually (50 RMs)              │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  SHARED PLATFORM LAYER (All Agents)                                             │
│  LangGraph Orchestration · AWS Bedrock · Cognito + Okta/AD Auth                │
│  Immutable Audit Trail · SR 11-7 Explainability · BSA/FATF Controls            │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### How the Agents Feed Each Other

The AML loop is the strongest linkage story:

1. **Agent 02 (TMS Enhancement)** runs first — it scores every TMS alert before analysts see it, suppressing ~50% as false positives. The true positives that score ≤15% FP probability are automatically escalated to Agent 01 as HIGH priority.

2. **Agent 01 (Financial Crime Investigation)** receives the high-probability alert, runs the full investigation workflow — KYC pull, transaction analysis, OFAC screening, adverse media, network mapping — and drafts a BSA-compliant SAR for BSA Officer review.

3. **Agent 01 findings feed Agent 03**: when an investigation reveals a risk event (SAR filed, adverse media found, ownership change detected), Agent 03 automatically triggers a CDD refresh for that customer.

4. **Agent 03 findings feed Agent 01**: when a KYC refresh produces a risk rating change (customer is now HIGH risk), that signal is available to Agent 01 and Agent 02 as customer context in future alert scoring.

5. **Agent 04 (Fraud Detection)** runs in parallel to the AML loop. Fraud patterns it detects — account takeover, structured payments, new payee fraud — can generate SAR flags routed to Agent 01 for full investigation when patterns suggest money laundering layering.

6. **Agent 05 (Wealth Copilot)** is the client-facing layer — operationally independent, but it uses the same KYC data that Agent 03 maintains. If an RM client triggers an adverse media hit or watchlist match via Agent 03, the Wealth Copilot can surface that context to the RM.

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

### Path D: Full-Suite (Large Regional Bank or Super Community Bank)
**Lead with the platform vision — individual agents are the proof points.**

```
Phase 1: Proof of concept on Agent 02 (fastest to stand up, most dramatic demo)
Phase 2: Expand to Agent 01 + 03 in parallel (6 months post-POC)
Phase 3: Agent 04 for card/payments business unit (12 months)
Phase 4: Agent 05 for wealth/private banking division (12-18 months)
```

---

## Buyer Persona Map

Different personas care about different agents. Know who's in the room.

| Persona | Primary Pain | Lead With | Supporting ROI Framing |
|---------|-------------|-----------|----------------------|
| **BSA Officer / Chief Compliance Officer** | Regulatory risk, exam findings, SAR quality | Agent 01 + 02 | "examination-ready audit trail, FFIEC-aligned, SR 11-7 compliant" |
| **Financial Crime Ops Leader / VP AML** | Analyst capacity, queue management, FP rates | Agent 02 | "50% queue reduction, analysts focus on real alerts" |
| **CRO / Chief Risk Officer** | Holistic risk posture, model risk, regulatory posture | Full suite | "$7.9M+ annual savings, <6 month payback, regulatory controls as code" |
| **CIO / CTO** | Integration complexity, AWS-native, security | Architecture | "LangGraph DAG, ECS Fargate, Bedrock, Cognito + Okta/AD, Terraform IaC" |
| **CFO / COO** | Fraud losses, operational cost, headcount | Agent 04 + 02 | "65% fraud loss reduction, $4M AML labor savings — hard P&L impact" |
| **Head of Wealth / Private Banking** | RM productivity, Reg BI, client retention | Agent 05 | "10+ hrs/week per RM reclaimed, $3.5M annually (50 RMs)" |
| **Head of Fraud** | False positive rate, real-time detection, Reg E | Agent 04 | "40% FP reduction, sub-200ms detection, auto Reg E disclosure" |
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
| Scope | Single use case (FP reduction OR investigation OR KYC) | End-to-end platform, 5 use cases |
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

---

## ROI Summary by Institution Profile

### Community Bank (Assets $1B–$5B)
| Use Case | Annual Savings | Notes |
|----------|---------------|-------|
| Agent 02 (TMS Enhancement) | $1.2M–$2.0M | 4-6 analyst team |
| Agent 01 (Financial Crime Investigation) | $800K–$1.5M | 300-600 SARs/year |
| Agent 03 (KYC/CDD Perpetual) | $500K–$1.0M | 2,000-4,000 customer reviews |
| Agent 04 (Fraud Detection) | $600K–$1.2M | Regional card/ACH volume |
| **Full Suite** | **$3.1M–$5.7M** | Payback < 6 months |

### Regional Bank (Assets $5B–$50B)
| Use Case | Annual Savings | Notes |
|----------|---------------|-------|
| Agent 02 (TMS Enhancement) | $2.5M–$5.0M | 8-15 analyst team |
| Agent 01 (Financial Crime Investigation) | $1.5M–$3.0M | 600-1,500 SARs/year |
| Agent 03 (KYC/CDD Perpetual) | $1.0M–$2.5M | 8,000-20,000 customer reviews |
| Agent 04 (Fraud Detection) | $1.5M–$3.5M | Higher transaction volumes |
| Agent 05 (Wealth Copilot) | $1.5M–$4.0M | 20-50 RMs |
| **Full Suite** | **$8.0M–$18.0M** | Payback < 4 months |

### Credit Union (Assets $500M–$5B)
| Use Case | Annual Savings | Notes |
|----------|---------------|-------|
| Agent 02 (TMS Enhancement) | $600K–$1.5M | Smaller alert volumes, fewer analysts |
| Agent 04 (Fraud Detection) | $400K–$1.0M | Card fraud primary concern |
| Agent 03 (KYC/CDD Perpetual) | $300K–$800K | Member reviews |
| **Priority Suite** | **$1.3M–$3.3M** | Agents 02 + 04 + 03 |

---

## Infrastructure Cost Reference

All five agents share the same AWS deployment pattern. Per-customer monthly AWS cost (mid-size bank, all 5 agents):

| Component | Cost |
|-----------|------|
| ECS Fargate (UI tasks, all 5 agents) | ~$150 |
| ECS Fargate (Agent workers, MCP gateways) | ~$350 |
| RDS Aurora PostgreSQL (shared or per-agent) | ~$250–$500 |
| DynamoDB (audit trails) | ~$20 |
| S3 (documents + archives) | ~$10 |
| AWS Bedrock (Claude — inference, primary cost driver) | ~$1,000–$4,000 |
| Security, networking, monitoring | ~$150 |
| **Total** | **~$1,930–$5,180/month** |

*Bedrock cost scales with usage. Claude Haiku for triage nodes (10x cheaper), Claude Sonnet for SAR/proposal generation. Provisioned throughput available for high-volume customers.*

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
