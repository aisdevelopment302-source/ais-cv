---
stepsCompleted: [1, 2, 3, 4, 6, 7, 8, 9, 10, 11]
inputDocuments:
  - 'analysis/product-brief-AIS-2025-12-20.md'
  - 'analysis/brainstorming-session-2025-12-20.md'
documentCounts:
  briefs: 1
  research: 0
  brainstorming: 1
  projectDocs: 0
workflowType: 'prd'
lastStep: 11
status: 'complete'
completedDate: '2025-12-24'
project_name: 'AIS'
user_name: 'Adityajain'
date: '2025-12-23'
partyModeUpdates: 'FR3b, FR6b, FR13b, FR13c, FR16, FR18, FR18b, FR24, FR25-29 note, FR30, FR30b, FR31b, FR33, FR39 expanded, FR40-FR55 (UX Step 7 discoveries: multi-delivery order model, weight precision, rate management, gate pass vs invoice distinction), FR32 removed (electric meter not ground truth for CV validation - per owner clarification), CV Validation Approach updated to photo sampling (Phase 1) and Hydra weight cross-validation (Phase 2)'
---

# Product Requirements Document - AIS

**Author:** Adityajain
**Date:** 2025-12-23

## Executive Summary

**AIS (Aadinath Information System)** is a comprehensive ERP system purpose-built for rolling mill operations under the AA (Double A) brand. It transforms a business currently operating on gut-feel decisions and minor manual unstructured calculations into a data-driven operation with real-time visibility, intelligent planning, and motivated teams.

### The Transformation

**Before AIS:** The owner arrives at 9 AM, spends 2 hours chasing updates from 5 different people. "What was yesterday's production?" requires a phone call. "Why was output low?" gets a shrug. "Should we take this new order?" is answered by gut feel. The day is consumed by firefighting, not strategizing.

**After AIS:** A 2-minute morning glance tells the whole story. Yesterday's production vs target. Any overnight breakdown alerts. Today's orders lined up. Cash position. The owner spends the day on growth decisions, not data hunting.

**For workers:** No more blame games. Clear instructions, fair tracking, and visible contribution to company success.

### The Problem

Rolling mill operations suffer from a **data maturity gap** that varies across departments. The path to operational excellence follows a clear progression:

1. **WHAT** — Do we even know what happened? (Data capture)
2. **WHY** — Can we explain why it happened? (Root cause visibility)
3. **HOW** — Can we act on it to improve? (Actionable insights)

**Current State by Area (Illustrative — not exhaustive):**

| Area | WHAT (Do we know?) | WHY (Can we explain?) | HOW (Can we act?) |
|------|--------------------|-----------------------|-------------------|
| **Production Output** | ✅ Yes — weighed per shift | ❌ No — why was it low/high? | ❌ No |
| **Breakdowns** | ❌ No — not logged | ❌ No — patterns invisible | ❌ No |
| **Purchase Planning** | ❌ Partial — reactive ordering | ❌ No — no forecasting data | ❌ No |
| **Sale Pricing** | ❌ Partial — gut feel | ❌ No — no cost clarity | ❌ No |
| **Weighbridge** | ⚠️ Manual entry — skeptical | ❌ No — no verification | ❌ No |
| **Worker Presence** | ⚠️ Binary attendance only | ❌ No — no hourly tracking | ❌ No |
| **Vehicle Movement** | ❌ No — untracked | ❌ No — no audit trail | ❌ No |

*Note: This is not an exhaustive list. Rolling mill operations span many areas, and additional departments/processes will be identified through ongoing discovery and brainstorming.*

**Decision Types Affected:**

| Decision Type | Time Horizon | Examples | Current State |
|---------------|--------------|----------|---------------|
| **Tactical** | Hour-to-hour | Are garam kaam workers short? Was coal fed to pulveriser? Is stock loaded into furnace? | No visibility — discovered when production stalls |
| **Operational** | Day-to-day | What size to roll this shift? What to purchase? Which orders to prioritize? Edge cases: mid-shift size changes due to raw material mismatch or breakdown recovery | Scattered info, WhatsApp chaos, gut feel |
| **Strategic** | Week/Month | Are we profitable? Should we take this order? Where to invest? | Monthly reconciliation — too late |

*Note: Hour-to-hour tactical decisions will expand significantly as the monitoring system is developed. Current examples focus on labour and resource flow visibility.*

**The Core Challenge:**
- **Some areas lack the WHAT entirely** — breakdowns not logged, purchase planning reactive, vehicle movement untracked
- **Some areas have the WHAT but lack the WHY** — production output is weighed, but why it varied shift-to-shift remains a mystery
- **Almost no area has the HOW** — actionable improvement is impossible without the foundation

**Impact of This Gap:**

| Impact Area | Consequence |
|-------------|-------------|
| **Decision Quality** | Sale prices driven by emotion and competition guessing, not actual cost knowledge |
| **Production Planning** | Next product chosen by "what looks short" — no calculation, pure estimation |
| **Purchase Planning** | Raw materials, tools, machinery ordered reactively — stockouts, rush orders, overstocking |
| **Repetitive Breakdowns** | No logging means the same failures repeat — no pattern recognition, no preventive action, no learning |
| **Growth Planning** | Impossible without knowing daily/weekly/monthly metrics and trends |
| **Accountability** | No objective data means disputes, blame games, and eroded trust |
| **Weighbridge Security** | Manual entry with unwatched CCTV — owner skepticism persists |

### The Solution

**AIS's mission is to systematically move every operational area through the WHAT → WHY → HOW journey:**

1. **Establish the WHAT** — Digital capture at source where it's missing (breakdowns, purchases, vehicle logs, hourly presence)
2. **Enable the WHY** — Data correlation, CV-powered insights, and trend visibility to explain variance
3. **Unlock the HOW** — Actionable dashboards, predictive alerts, and decision support

### What Makes This Special

**Core Value Proposition:** *Transparency about business at all times* — the fundamental need that rolling mill owners value above all else.

AIS delivers this transparency through:

| Differentiator | Strategic Value |
|----------------|-----------------|
| **CV + ERP Integration** | No rolling mill ERP offers this — objective production data without trusting manual logs |
| **Weighbridge + Vehicle Detection** | Auto-captured weights + number plates = unchallengeable material movement proof |
| **Chain of Trust** | Confidence-scored data integrity — every data point traces back to an immutable physical signal or external document (purchase bills, photos, CV, weighbridge readings) |
| **TPS Principles Native** | Visual management, waste elimination, Kaizen loops built into the system DNA |
| **Analysis Playground** | Free-form correlation discovery before formalizing process links |
| **External Intelligence Layer** | Competition rates + market trends integrated for pricing and strategy |

## Project Classification

**Technical Type:** Custom Enterprise Application (with future SaaS potential)
**Domain:** Manufacturing Operations / Industrial ERP
**Complexity:** Medium-High
**Project Context:** Greenfield — new project

This classification reflects:
- Single-tenant, owner-operated system for immediate use
- Multi-tenant architecture potential for future SaaS offering to other mills
- Role-based access control across 6+ user types
- Hardware integrations (weighbridge, CCTV/CV, mobile devices)
- No heavy regulatory compliance burden (not healthcare, fintech, govtech)
- Custom CV and IoT integration requirements beyond standard ERP capabilities

## Success Criteria

### User Success

**The Moments That Matter:**

| User | Success Moment | Measurable Indicator |
|------|----------------|----------------------|
| **Owner** | Making strategic decisions with confidence because the data is there — and seeing results reflected in changed data | Time on chores <30 min/day; decisions backed by dashboards, not gut feel |
| **Sales & Purchase Head** | Pricing with data, collecting faster, trusting the numbers | Automated reminders sent; collection efficiency improved; pricing decisions data-driven |
| **Production Manager** | Decisions supported by system, not memory — single dashboard instead of chasing 5 people | Planning board used daily; information retrieval time near zero |
| **Foreman** | First predictive alert that *prevents* a breakdown before it happens | Breakdown predicted and avoided; maintenance scheduled proactively |
| **Office Staff** | Zero errors, no re-checking by owner — confidence restored | Edit log volume near zero; owner verification time eliminated |
| **Accountant** | Ledger always current, no re-entry, instant visibility for Sales & Purchase Head | Auto-updated ledgers; no duplicate data entry |

**Emotional Success:**
- **Trust Restoration:** Owner trusts workforce more because data is objective and verifiable — reduction in disputes and confrontations about accuracy
- **Company Growth with People:** Watching the business grow alongside the team that built it — shared success, not surveillance

**Worker Success:**
> *Clear instructions without confusion. Fair recognition without blame. Pride in contributing to a growing company.*

| Worker Metric | Measurement |
|---------------|-------------|
| **Reduction in confusion incidents** | Fewer times workers ask "what should I do?" or receive conflicting instructions |
| **Zero blame incidents** | Disputes resolved by data, not accusations |

### Business Success

**Operational Metrics:**

| Metric | Current State | Target | Timeframe |
|--------|---------------|--------|-----------|
| **Digital Capture (Purchases)** | 0% | 100% | Within 60 days |
| **Digital Capture (Sales)** | 0% | 100% | Within 60 days |
| **Digital Capture (Attendance)** | 0% | 95%+ | Within 30 days |
| **Owner Time on Chores** | 1-2 hours/day | <30 min/day | Within 60 days |
| **Data Entry Errors** | Frequent | Near zero (by category) | Ongoing from Day 1 |
| **Gate Pass Corrections** | Unknown | Zero | Immediate |
| **Report Generation Time** | Hours (manual) | <5 minutes (auto) | Within 60 days |
| **Weighbridge Discrepancy Alerts** | None (undetected) | 100% captured | Immediate |

**Error Categorization (Severity-Based Tolerances):**

| Error Type | Tolerance | Rationale |
|------------|-----------|-----------|
| **Financial errors** (wrong amount, wrong customer) | Zero | Money is sacred |
| **Weight discrepancies** (>20kg) | Zero | Trust metric — unchallengeable proof |
| **Timing errors** (wrong date/shift logged) | Near zero | Affects reporting accuracy |
| **Data entry typos** (name spelling, notes) | Low but acceptable | Annoying, not critical |

**Adoption Indicators (Indirect Measurement):**

Since lead time between actual event and data entry cannot always be known by the system, we measure proxies:

| Indicator | What It Tells Us |
|-----------|------------------|
| **Timestamp patterns** | Entries at 6 PM in bulk = end-of-day catch-up; entries throughout day = real-time adoption |
| **Entry-to-event gap (where known)** | Gate passes have truck arrival time and entry time — that gap is measurable |
| **Batch vs. real-time ratio** | % of entries made within 1 hour of event vs. batch-entered later |

**Problem Visibility (Not Just Reduction):**

Success is not just reducing downtime — it's **making problems visible so they can be solved**:

| Visibility Target | What It Enables |
|-------------------|-----------------|
| **Breakdown Logging** | Patterns emerge → preventive action possible → same failures stop repeating |
| **Purchase Bottlenecks** | Stockouts and rush orders surfaced → proactive ordering |
| **Sale Bottlenecks** | Order delays and fulfillment gaps visible → process improvement |
| **Production Bottlenecks** | Constraints identified → targeted investment decisions |

**Growth Metrics (Tracked Over Time):**

| Growth Indicator | Measurement Approach |
|------------------|----------------------|
| **Revenue Growth** | Monthly/quarterly trend analysis |
| **Production Tonnage** | Output tracking vs historical baseline |
| **Waste/Scale Loss Reduction** | Input vs output weight delta tracked |
| **Goodwill & Brand Image** | Customer retention, repeat orders, referrals |
| **Quality Improvement** | QC rejection rates, customer complaints |

**Trust Metric:**
- **Reduction in data edits/corrections** — fewer edits = more trust in initial capture
- **Reduction in owner re-verification** — owner stops double-checking because system is reliable

### Technical Success

*Detailed specifications deferred to Architecture phase.*

**Non-Negotiable Foundation:**

| Criterion | Target | Rationale |
|-----------|--------|-----------|
| **Data Integrity** | Zero data loss | Every entry persisted reliably, even if entered offline and synced later. If users lose data once, trust is destroyed. This is a survival metric. |

Additional technical requirements to be specified in Architecture:
- CV integration accuracy targets
- System reliability and uptime
- Mobile/offline considerations
- Integration specifications (weighbridge, cameras)

### Measurable Outcomes

**MVP Success Gate (Must achieve before expanding scope):**

| Criteria | Target | Measurement |
|----------|--------|-------------|
| Digital adoption | 100% capture | All purchases, sales, attendance digitally recorded |
| Owner time savings | <30 min/day on chores | Self-reported + edit log volume |
| Weighbridge trust | Zero unexplained discrepancies | Alert log shows no unresolved >20kg variances |
| Gate pass accuracy | Zero corrections | No post-generation edits required |
| Report speed | <5 minutes | Auto-generated daily/weekly/monthly reports |
| Data integrity | Zero data loss | All entries persisted, including offline sync |
| Financial accuracy | Zero errors | No wrong amounts or wrong customers |

**Ultimate Success Statement:**

> *For the Owner: "I make decisions looking at tangible data, see results reflected in changed data, trust my workforce because the numbers are objective, and watch the company grow with the people who built it."*

> *For Workers: "Clear instructions without confusion. Fair recognition without blame. Pride in contributing to a growing company."*

## Product Scope

### MVP-Core (8-10 weeks)

**Focus:** Digital records + Gate Pass + Manual Weighbridge + Reports

| Module | Scope |
|--------|-------|
| **Procurement** | Purchase entry, supplier tracking, bill logging with optional photo |
| **Sales** | Order entry (replacing WhatsApp), customer tracking, invoice generation |
| **Attendance** | Daily attendance capture at entrance |
| **Expenses** | Day-to-day expense entry with validation |
| **Salaries** | Automated salary calculations, account allocation |
| **Gate Pass** | Auto-generated from order + hydra weights + manual weighbridge entry |
| **Ledger** | Auto-updated from transactions, real-time debtor/creditor lists |
| **Dashboards** | Full visibility for Owner + Sales & Purchase Head; role-appropriate views for others |
| **Reports** | Daily, weekly, monthly pre-built reports with filters |

**Critical Path: Gate Pass (First Proof of Value)**

Gate Pass is the most visible early win. Its dependencies must be prioritized:

```
CRITICAL PATH: Gate Pass
├── Sprint 1-2: Sales Order Entry (dependency)
├── Sprint 2-3: Hydra Mobile App (dependency)
├── Sprint 3-4: Weighbridge Manual Entry (dependency)
├── Sprint 4: Gate Pass Integration (milestone)
```

### MVP-Plus (4-6 weeks additional)

**Focus:** CV Integration + Weighbridge Auto-Integration + Intelligence

| Feature | Scope |
|---------|-------|
| **Weighbridge Auto-Integration** | Direct hardware connection — auto-capture gross, tare, net |
| **Production CV** | Binary detection: Running vs Break/Downtime from key cameras |
| **Shift Reports** | Production time vs break time per shift, visible next day |
| **Competition Rates** | Auto-fetch from WhatsApp + storage + trend visualization |
| **AI Data Chat** | Simple query interface — "show me X" with basic insights |

### Growth Features (Phase 2: 6-12 months post-MVP)

| Feature | Rationale |
|---------|-----------|
| **Predictive Maintenance** | Requires 6-12 months of breakdown data to train models |
| **Foreman Module** | Breakdown logging, lifecycle tracking, maintenance alerts |
| **Hourly Worker Presence** | CV detection across factory cameras |
| **Supervisor Limited Views** | Role-specific dashboards for Garam Kaam, Chataal, Kenchi, Loading |
| **ANPR Vehicle Detection** | Automatic number plate recognition at gate |
| **Automated Collection Reminders** | WhatsApp reminders with personalized messages |
| **Bottleneck Analysis** | Purchase, sale, and production constraint identification |

### Vision (Phase 3: 12-24 months)

| Feature | Strategic Value |
|---------|-----------------|
| **AI-Assisted Analysis Playground** | Discover correlations, get recommendations |
| **Predictive Business Insights** | "If you do X, expect Y" |
| **Advanced TPS Visual Management** | Factory-wide visual boards |
| **Mobile App Enhancements** | Owner/Sales & Purchase Head on-the-go oversight |
| **SaaS Offering (Optional)** | Productize for other rolling mills |
| **Supplier/Customer Integration** | Seamless ordering and fulfillment |

## SaaS B2B Specific Requirements

### Project-Type Overview
- AIS deploys as a **single-tenant** system today, but every schema and service already includes `tenant_id` so future multi-plant support is straightforward. Each plant will be its own tenant with isolated data, and corporate-level aggregation can be added later.
- DevOps scripts must clone a full tenant stack (database + storage + integrations) so onboarding another plant is a repeatable process.

### Technical Architecture Considerations
- **Tenant boundaries:** All queries, background jobs, and analytics stay scoped by tenant_id. No hard-coded plant assumptions.
- **Integration adapters:** WhatsApp API, CCTV RTSP feeds, weighbridge serial data, accounting exports, and future vendors are wrapped behind adapter interfaces so swaps don’t require core rewrites.
- **Deployment model:** Today: single tenant in a dedicated environment. Future: containerized services per tenant or dedicated namespaces/projects. Infrastructure-as-code should support both.

### Tenant Model
| Metadata | Why it matters |
|----------|----------------|
| Plant name, location, timezone | Drives reporting windows and regulatory settings |
| CCTV endpoints (RTSP/MJPEG) | Linked to CV module per camera |
| Weighbridge device IDs | Maps Raspberry Pi connectors for gross/tare capture |
| WhatsApp group/API identifiers | Feeds competition intelligence and reminders |
| Feature flags | Toggle modules (CV, ANPR, predictive maintenance, etc.) per tenant |

### RBAC Matrix & Granular Permissions
| Role | Capabilities | Example toggles |
|------|-------------|------------------|
| Owner/Admin | Full access, tenant config, approvals | `can_manage_tenant`, `can_export_all`, `can_approve_override` |
| Sales & Purchase Head | Sales orders, pricing, debtors | `can_edit_rates`, `can_view_debtors`, `can_send_whatsapp` |
| Production Manager | Planning board, breakdowns, shifts | `can_edit_plan`, `can_ack_breakdown`, `can_view_attendance` |
| Office Staff | Gate passes, invoices, expenses | `can_generate_gatepass`, `can_edit_expense`, `can_print_invoice` |
| Accountant | Ledger, payments, exports | `can_post_payment`, `can_export_ledger`, read-only ops |
| Supervisors (Garam Kaam/Chataal/Kenchi/Loading) | Limited dashboards, team attendance | `can_view_shift_timeline`, `can_mark_attendance` |
| Hydra Operator | Weight entry app only | `can_log_weight` |
| System Owner (Alerts Admin) | Manage alerts/integrations | `can_manage_integration`, `can_resolve_alert` |
| (Future) Auditor | Read-only subset (placeholder) | Feature flag for view-only |

### Subscription & Feature Flags
- No commercial tiers yet, but feature flags align with roadmap: **Core (MVP-Core)**, **Plus (MVP-Plus)**, **Vision**. Prepares modules for future pricing tiers without forks.

### Integration List
| Integration | Approach |
|-------------|----------|
| WhatsApp Business API | Adapter for chosen vendor (Twilio/360dialog/etc.)
| Accounting software | Export adapters for Tally/Zoho/SAP to avoid double entry
| CCTV / CV | RTSP ingestion via Raspberry Pi edge nodes with buffering
| Weighbridge | Raspberry Pi serial/USB interface for gross/tare capture
| Power/Electric meters (future) | Modbus/REST adapters for runtime insight
| SMS/Email gateways (optional) | Abstracted notification service as fallback |

### Security & Compliance Foundations
- Even without formal compliance targets, practice security-by-default: TLS everywhere, encryption at rest, per-tenant daily backups, audit logs for sensitive actions. Document retention and data flows now to simplify future ISO/GST work.

### Implementation Considerations
- Stories reference tenant context (“As Owner of tenant X…”). RBAC tasks list exact permission toggles. Integration stories build mocked adapters before real hardware.
- Security backlog includes TLS enforcement, backup automation, audit log reporting, and least-privilege defaults.

## Project Scoping & Phased Development

### MVP Strategy & Philosophy

**MVP Approach:** Problem-Solving MVP for a complex project — deliver undeniable transparency and trust inside a single plant before expanding. Remove the day-to-day fog (gate pass errors, missing logs, pricing confusion) so the owner and team feel immediate relief.

**Resource Requirements:** Lean core team with expertise in (1) full-stack web + RBAC, (2) hardware/IoT integration (Raspberry Pi, weighbridge, CCTV), (3) CV/data engineer for runtime detection, (4) PM/ops lead embedded in the plant. Security + DevOps support needed to enforce backups and tenant-aware infrastructure.

### MVP Feature Set (Phase 1)

**Core User Journeys Supported:**
- Owner dashboard (“2-minute morning glance”)
- Office Staff gate pass automation (hydra ↔ weighbridge ↔ invoice)
- Sales & Purchase Head pricing + debtor workflows
- Production Manager control tower (planning, breakdown logging)
- Supervisors’ limited dashboards + attendance
- Admin alert queue and approvals

**Must-Have Capabilities:**
- Digital capture of purchases, sales, attendance, expenses, salaries
- Gate pass workflow (order entry, hydra mobile weight logging, weighbridge integration, variance alerts, printing)
- Ledgers + accounting exports (no double entry)
- Dashboards for roles with CV runtime/break detection, shift reports, receivables/payables, expense tracking
- WhatsApp ingestion (competitive rates, reminders)
- RBAC with granular permissions + audit logging
- Security foundations: TLS everywhere, encryption at rest, daily backups, alert log

### Post-MVP Features

**Phase 2 (Growth):**
- Predictive maintenance + Foreman module (breakdown lifecycle)
- Hourly worker presence (CV per camera)
- Supervisor limited views expansion + ANPR vehicle detection
- Automated collection reminders with templates
- Bottleneck analysis and advisor dashboards

**Phase 3 (Expansion):**
- AI Analysis Playground + predictive business insights
- Advanced TPS visual management boards
- Mobile app enhancements for Owner/Sales & Purchase Head
- SaaS multi-plant offering + tenant management console
- Supplier/customer portal integration

### Risk Mitigation Strategy

**Technical Risks:**
- CV + hardware integrations may slip → build mocked adapters, keep manual fallback until validation targets met; track each integration as its own milestone (WhatsApp, CCTV, weighbridge, accounting).

**Market Risks:**
- Need proof AIS works beyond your plant → capture metrics (owner time saved, zero discrepancies, revenue/tonnage change) to use as case study before pitching other mills.

**Resource Risks:**
- If team bandwidth shrinks, keep MVP scope to the six journeys above, defer CV advanced analytics and ANPR; ensure feature flags let you pause non-critical modules without code rework.

## Functional Requirements

### Tenant & User Management

- FR1: Tenant Admin can configure plant metadata (name, timezone, CCTV endpoints, weighbridge device IDs, WhatsApp identifiers).
- FR2: Tenant Admin can invite, activate, deactivate, and reset credentials for users across all roles.
- FR3: Tenant Admin can assign granular permissions (e.g., can_edit_rates, can_generate_gatepass, can_export_ledger) to each role or individual user.
- FR3b: Permission conflicts shall resolve using a deny-by-default principle — if any applicable permission denies access, access is denied regardless of other grants.
- FR4: Tenant Admin can view an audit history of user logins, permission changes, and role assignments.
- FR5: Tenant Admin can enable or disable modules for the tenant via feature flags.

### Sales & Procurement Operations

#### Multi-Delivery, Multi-Size Order Model

*Note: A single truck/order can carry multiple deliveries (UP, MIDDLE, DOWN — different destinations), each delivery containing multiple product sizes with independent weight tracking and rates. This complexity was discovered during UX Step 7 sessions with the Owner (Adityajain) and reflects real-world rolling mill operations.*

- FR40: System shall support orders with multiple deliveries per truck, each delivery having a distinct destination identifier (UP/MIDDLE/DOWN or equivalent).
- FR41: System shall support multiple product sizes per delivery, each with independent weight tracking and rate calculation.
- FR42: Gate Pass shall display per-delivery weight breakdown and per-size rates for verification.

#### Order & Customer Management

- FR6: Sales & Purchase Head can create, edit, and track sales orders with customer, product, size, rate, and delivery instructions.
- FR6b: Customer records shall include default weighbridge preference (Internal Only / Third-Party Required / Ask Each Time), applied automatically to new orders for that customer.
- FR7: Office Staff can log purchase bills with supplier, material, quantity, rate, attachments, and payment terms.
- FR8: Sales & Purchase Head can update active rates and automatically notify relevant users of changes. *(See Rate Management section FR43-FR51 for detailed rate components, types, and variance workflows.)*
- FR9: Sales & Purchase Head can record payment collections, update debtor status, and assign follow-up dates.
- FR10: Procurement users can view purchase backlog, vendor history, and pending bills filtered by timeline.

### Rate Management

*Note: Rate management complexity was discovered during UX Step 7 sessions. Rolling mill pricing involves multiple components that vary by market and size. This section captures the business rules for rate calculation, variance handling, and approval workflows. Source: UX Design Specification, Step 7.*

#### Rate Components & Configuration

- FR43: System shall support configurable rate components: Base Rate (daily, per market), Fix Cut Rate (standard processing addition), Size Parity (varies by size AND market), and Loading Rate (varies by market).
- FR44: System shall support market-based rate configuration (e.g., Mumbai, Gujarat markets) with independent base rates and size parities per market. Architecture shall support adding additional markets.
- FR45: Rate configuration shall be date-versioned, maintaining an immutable audit trail of historical rates for dispute resolution and pricing analysis.

#### Rate Types & Variance Handling

- FR46: System shall support two rate types per order:
  - **FLAT:** Customer-negotiated all-in rate (e.g., "₹47,000 for everything")
  - **CALCULATED:** Computed from components (Base + Fix Cut + Size Parity + Loading)
- FR47: For FLAT rate orders, system shall accept the customer rate as-is and generate an informational notification to Sales person. No approval required — notification is for awareness only.
- FR48: For CALCULATED rate orders, system shall compare order rate against system-calculated rate. Any difference (no threshold — even ₹10 requires decision) shall block gate pass generation until resolved.
- FR49: Rate variance resolution shall require explicit selection: "Approve Order Rate", "Use Calculated Rate", or "Cancel Order". Resolution reason is mandatory. All resolutions logged with actor, timestamp, and justification.

#### Rate Configuration Interface

- FR50: Sales & Purchase Head or Owner can update active rate components (Base Rate, Fix Cut, Size Parity, Loading) per market. Changes trigger notification to Office Staff and Production Manager.
- FR51: *(Phase 2)* System shall support market survey capture and competitor rate tracking, feeding into pricing intelligence dashboards.

### Gate Pass & Logistics

#### Weight Precision

*Note: This business rule reflects Hydra scale precision and was confirmed during UX Step 7 sessions. All weights in the system must be in multiples of 5 kg only.*

- FR52: All weight values (Hydra entries, weighbridge readings, calculated weights, adjustments) shall be stored and displayed in multiples of 5 kg only. System shall auto-round user entries to nearest 5 kg with visible feedback (e.g., "3852 → 3850").

#### Gate Pass Generation

- FR11: Office Staff can generate gate passes by selecting an order, entering hydra weights per turn, and reconciling weighbridge readings.
- FR12: Hydra Operator can record weight per pick via a mobile interface tied to the scheduled truck.
- FR13: System can automatically calculate gross, tare, net weights from connected weighbridge devices and highlight variance vs hydra totals.
- FR13b: System shall support graceful degradation to manual weighbridge entry when hardware connection is interrupted, logging the disconnection event with timestamp.
- FR13c: System shall automatically detect hardware reconnection and offer to sync any manually-entered readings captured during the outage.
- FR53: Internal weighbridge readings shall be captured per delivery (not cumulative across the entire truck load). This enables variance detection at each delivery stage before proceeding to the next delivery.
- FR14: Office Staff can print, export, or regenerate gate passes with audit trail and version history.
- FR15: Loading Supervisor can view truck assignments and mark loading progress per turn.

#### Gate Pass vs Invoice Distinction

*Note: Gate Pass and Invoice are distinct documents with different purposes. This distinction was clarified during UX Step 7 sessions.*

- FR54: Gate Pass shall display weights (Hydra, Internal, Third-Party, Final) and rates per size for verification purposes. Gate Pass shall NOT display calculated amounts.
- FR55: Invoice is a separate document generated after Gate Pass approval. Amount calculation (weight × rate) shall occur during Invoice generation, not in Gate Pass.

### Production Planning & Maintenance

- FR16: Production Manager can view a prioritized backlog of orders, default sorted by Order ID (ascending), with configurable sort options including delivery date, margin, customer, and product type.
- FR17: Production Manager can schedule shifts, assign sizes to furnace queues, and issue mid-shift change commands that notify downstream roles.
- FR18: Production Manager can log breakdowns with: timestamp (required, auto-populated), breakdown type tag (required, enumerated: Mechanical, Electrical, Labor, Other), cause description (optional free text, can be added later), corrective action (optional, can be added later), and attached evidence (optional photos/files).
- FR18b: Breakdowns logged without cause description shall appear in a 'Pending Details' queue visible to Production Manager and Foreman, with daily reminder until completed.
- FR19: Supervisors can view shift timelines (target vs actual runtime/break/downtime) for their sections.
- FR20: Production Manager can reassign labour or flag labour shortages directly from the dashboard.

### Financials & Accounting Sync

- FR21: Accountant can view synchronized ledgers of payables/receivables that update automatically from sales, purchases, and expenses.
- FR22: Accountant can export ledger transactions in accounting software formats (e.g., Tally/Zoho/SAP-ready CSV).
- FR23: Owner can review cash expenses, kharchi advances, and salary calculations with supporting records.
- FR24: System can schedule automated daily/weekly/monthly reports covering: Production (tonnage, runtime, downtime, breakdowns), Sales (orders, fulfillment, revenue), Purchases (bills, suppliers, outstanding), and Financials (receivables, payables, expenses, cash position). Report content specifications align with Success Criteria section.

### Analytics & Dashboards

*Note: Dashboards are role-filtered views of a unified data layer. Each role sees a curated subset of widgets and metrics appropriate to their responsibilities as defined in the RBAC matrix.*

- FR25: Owner can view a consolidated dashboard showing yesterday's production/break/downtime, today's plan, receivables/payables, attendance, and expense summaries.
- FR26: Sales & Purchase Head can view competition rate trends, order fulfillment status, and collector performance.
- FR27: Production Manager can monitor live shift metrics sourced from CV + manual logs, including variance alerts.
- FR28: Supervisors can view limited dashboards with their team's attendance, workloads, and delays.
- FR29: System can store and display historical trends (daily/weekly/monthly) for production, sales, purchases, and expenses.

### Intelligence & External Data

- FR30: System can ingest WhatsApp messages from configured groups, extract competition rates or collection notes using pattern matching, and present ALL parsed messages for manual review by Sales & Purchase Head before inclusion in system data. No auto-acceptance in MVP.
- FR30b: *(Phase 2)* System shall implement AI/NLP parsing with confidence scoring for WhatsApp messages. Messages above configurable confidence threshold (default 85%) may be auto-accepted; messages below threshold require manual review. Parsing accuracy shall be tracked and reported monthly.
- FR31: Sales & Purchase Head can trigger WhatsApp reminders or messages to customers based on debtor status, using approved templates.
- FR31b: Customer-specific WhatsApp reminder templates shall be managed per customer record, with no system-wide standardization required. Templates support variable substitution for outstanding amount, invoice numbers, and days overdue.

### Alerts, Approvals & Audit

- FR33: System can queue alerts for variance thresholds (weighbridge, production gaps, missing breakdown logs) and route them to the appropriate approver based on RBAC-defined escalation rules.
- FR34: Owner/Admin can approve or reject pricing overrides, variance acceptances, and module-level changes with mandatory comments.
- FR35: Every sensitive action (rate change, gate pass regeneration, ledger export) is recorded with actor, timestamp, and context for audit review.
- FR36: Users with permission can search and filter historical alerts, approvals, and audit entries.

### Security & Data Integrity

- FR37: System can enforce TLS-secured access for all user interactions and APIs.
- FR38: System can perform daily tenant-level backups and support restore operations on request.

#### FR39: Data Integrity Framework (Chain of Trust)

The system shall maintain a multi-point data integrity chain for material movement, performing automated comparisons at each checkpoint:

**FR39a: Hydra vs Internal Weighbridge Comparison**
- Trigger: When Office Staff initiates gate pass generation
- Tolerance: ±20kg (configurable per tenant)
- **Within tolerance:** Proceed with gate pass, log variance for trending
- **Exceeds tolerance:** 
  - Block gate pass generation
  - Alert Office Staff immediately with variance details
  - If unresolved within 15 minutes (wall-clock time), escalate to Production Manager
  - If unresolved within 30 minutes, escalate to Owner
  - If variance is negative (Hydra < Weighbridge) AND >50kg, alert Owner immediately (theft flag)

**FR39b: Invoice Weight Determination**
- When third-party weighbridge is used: 
  - Third-party weighbridge shall capture **two independent readings**
  - System shall calculate and store the **average** of both readings as the authoritative invoice weight
  - Both individual readings (Weigh 1, Weigh 2) retained in audit trail for verification
  - Gate pass and invoice auto-update to reflect third-party average weight
  - Internal weighbridge reading retained for audit trail only
  - Variance between internal and third-party logged for calibration trending (FR39c), but does NOT block or require resolution
- When third-party weighbridge is NOT used: Internal weighbridge net weight becomes the invoice weight. Gate pass generated from internal reading. Customer acceptance of internal weight implied by not requesting third-party verification.

**FR39c: Trend Analysis for Calibration Detection**
- Trigger: Automated daily analysis
- Pattern: 5+ consecutive variances in same direction (even if each is within tolerance)
- Action: Generate "Calibration Review Required" alert to Owner + Production Manager
- This catches systematic drift before it becomes a dispute

**FR39d: Variance Audit Trail**
- Every variance event logged with: timestamp, hydra total, weighbridge reading, calculated difference, resolution action, resolver ID
- Audit log immutable — no edits, only append
- Owner can query variance history by date range, truck, customer, or Hydra Operator

**FR39e: Variance Resolution Workflow**

When a variance blocks progression:

1. **Initial Review (Office Staff)** — 0-15 minutes
   - Office Staff sees variance alert with side-by-side comparison
   - Can request Hydra Operator to re-verify counts (mobile notification)
   - Can request Production Manager to physically verify weighbridge
   - If explainable variance (e.g., documented spillage), can log reason and proceed with approval

2. **Escalation Level 1 (Production Manager)** — 15-30 minutes
   - Production Manager receives escalation alert
   - Can authorize proceeding with documented variance
   - Can order re-weighing
   - Can flag for Owner review

3. **Escalation Level 2 (Owner)** — >30 minutes OR financial flag
   - Owner receives critical alert
   - Final authority to approve, reject, or investigate
   - Theft-flagged variances (FR39a) route here immediately

4. **Resolution Recording**
   - All resolutions require: resolution type (enumerated: Approved, Re-weighed, Spillage Documented, Calibration Issue, Investigation Required), resolution note (free text), approver ID

**FR39f: Invoice Weight Mode Selection**
- System shall support two invoice weight modes per order: (1) Third-party weighbridge as billing authority, or (2) Internal weighbridge as billing authority
- Mode selection recorded at order creation based on customer default preference (FR6b)
- Mode displayed on gate pass for clarity

**FR39g: Weight Adjustment Distribution**

*Note: When third-party authoritative weight differs from internal weighbridge total, the difference must be distributed across deliveries. This business rule was clarified during UX Step 7 sessions.*

- When third-party authoritative weight differs from internal weighbridge total:
  - System shall calculate the total difference (e.g., Internal: 24,200 kg vs Third-Party Avg: 24,170 kg = -30 kg difference)
  - System shall distribute the adjustment proportionally across deliveries based on each delivery's weight share
  - All adjusted weights shall remain multiples of 5 kg (per FR52)
  - Example distribution: If difference is -30 kg across 3 deliveries of roughly equal weight, each delivery adjusts by -10 kg
  - Adjustment breakdown displayed on Gate Pass for transparency (per delivery)
  - Audit trail captures original internal weights, third-party weights, and final adjusted weights

## Innovation & Novel Patterns

### Detected Innovation Areas

1. **CV + ERP Integration for Rolling Mills**  
   - Real-time CV signals (runtime vs break vs downtime) feed directly into ERP planning, pricing, maintenance, and morale dashboards.  
   - First time production truth, security feeds, and HR accountability share the same data layer, giving supervisors a moment where they trust the screen more than their own eyes.

2. **Gate Pass Automation Across Physical Devices**  
   - Hydra mobile logging → automatic reconciliation with weighbridge → rate & invoice generation.  
   - Creates a “chain of trust” so a single truck movement has indisputable digital + physical proof.

3. **WhatsApp-Sourced Market Intelligence**  
   - Competition rates, collection chatter, and supplier updates are captured straight from WhatsApp into structured pricing guidance, eliminating transcription errors and delay.

### Market Context & Competitive Landscape

- Rolling mill ERPs today either ignore CV entirely or bolt it on as CCTV monitoring. AIS makes CV the core data signal (production, attendance, maintenance).  
- Gate pass and hydra/weighbridge reconciliation is typically manual, living in notebooks like Gate Pass #085. AIS treats it as a unified workflow with variance alerts.  
- Competitor rate tracking is phone-call folklore; AIS formalizes it by scraping WhatsApp groups the team already uses.

### Validation Approach

| Innovation | Validation Plan |
|------------|-----------------|
| **CV + ERP** | **Phase 1 (MVP-Plus):** Sample 5-7 photos per detected break/run period, manually verified by supervisor/manager. CV accuracy validated against human review of sampled frames. Target: ≥95% agreement before CV becomes primary source. **Phase 2 (Future):** CV piece counting cross-validated against Hydra production weights from next-day reconciliation. Systematic variance between CV piece count (×expected weight per piece) and Hydra totals triggers calibration review. |
| **Gate Pass Automation** | For the first 50 automated gate passes, keep manual slips in parallel. Automation becomes primary only after two straight weeks of 100% hydra ↔ weighbridge ↔ invoice agreement, with variances explained in AIS. |
| **WhatsApp Intelligence** | Daily manual review of parsed messages for the first month. Any mismatch triggers an alert to Sales & Purchase Head, and the entry is corrected immediately; automation is trusted only after the mismatch rate stays <2% for 4 consecutive weeks. |

### Risk Mitigation

| Risk | Mitigation |
|------|------------|
| CV false positives/negatives | Keep manual logging as fallback until accuracy target hit; disagreements feed model improvement. |
| Hardware/device failure in gate pass flow | Manual override path remains with audit log; variance alerts prompt double-check before truck leaves. |
| WhatsApp policy or privacy changes | Maintain opt-in storage, purge logs per policy, and design a fallback input (manual rate entry or email import) so pricing intelligence continues even if WhatsApp access is restricted. |

## User Journeys

### Journey 1: Prakash (Office Staff) — Gate Pass Transformation
Prakash arrives with chai in one hand and yesterday's gate pass book in the other. Orders arrive via WhatsApp voice notes, hydra weights on scrap slips, weighbridge numbers on carbon copies. If he mishears a turn weight or the loading manager writes 3830 twice, the gate pass fails and the invoice must be cancelled. Panic sets in whenever a customer spot-checks: "Which truck? Which rate?"

**AIS Storyline:** Sales orders enter the system, hydra operators log turns via mobile forms, and weighbridge data auto-syncs. When a turn weight is typed incorrectly, AIS highlights the discrepancy before the gate pass prints. Weighbridge variance prompts a decision (within tolerance? escalate?). Gate Pass #085 generates instantly, with audit trail intact. Instead of rewriting numbers six times, Prakash approves and moves on.

**Requirements revealed:** Sales order intake, hydra logging with validation, weighbridge integration + variance alerts, gate pass auto-generation, audit trail, history search, export to accounting.

### Journey 2: Adityajain (Owner) — From Firefighting to Strategy
You reach the mill around 10:30 AM, take a floor walk to read the room, then sit down to manually enter purchase data, reconcile cash expenses, approve kharchi, and verify attendance. Breakdown logs are missing, rates change verbally, and invoices pile up. Reliability equals gut feel. When you discover an invoice error, you cancel it and call the customer personally — the worst moment of your day.

**AIS Storyline:** A two-minute dashboard brings yesterday's production time, break time, downtime, sales, purchases, expenses (coal, electricity, burning loss), live "today so far," receivables/payables, and attendance. Failed breakdown logs show as red tiles until resolved. If someone edits a rate after invoicing, the audit trail pinpoints who, when, and why. You still walk the mill, but now you operate strategically, not reactively. Data exports plug into your accounting tool automatically, so no double entry remains.

**Requirements revealed:** Executive dashboard, CV vs manual reconciliation, expense trends, financial snapshot, data exports, audit logging, live operations view.

### Journey 3: Rajesh (Sales & Purchase Head) — Pricing with Confidence
Rajesh juggles 20 WhatsApp groups, tries to guess competition rates, and chases payments manually. If he updates a rate mid-day, Office Staff often misses the change, leading to wrong invoices. Debtor follow-ups rely on memory and whiteboards.

**AIS Storyline:** A Sales Intelligence board shows competition rates (auto-captured from WhatsApp), margin per order, pending deliveries, and debtor aging. Rajesh enters a new price; AIS pings Office Staff and Production instantly. When he prices an order at ₹200 above tolerance, AIS warns "Margin drops below target — proceed or adjust?" He schedules automated WhatsApp reminders for overdue clients, each tied to actual outstanding amounts. For the first time, he negotiates using signals, not noise.

**Requirements revealed:** Competition data ingestion, shared rate updates with alerting, order-to-delivery tracking, debtor dashboard with messaging, supplier planning tied to production.

### Journey 4: Imran (Production Manager) — Control Tower Planning
Imran keeps the entire plan in his head. A midnight furnace stall might be relayed as "we fixed it" with no data captured. If coal wasn't fed or labour is short, he hears only after the furnace idles. Mid-shift size changes rely on gut feel, causing cascading confusion.

**AIS Storyline:** The Production Control Board shows order backlog ranked by margin and delivery date, raw material inventory, furnace queue, hydra progress, breakdown logs, and attendance per department. When AIS flags that the hydra team double-entered a load or coal wasn't fed, Imran sees the downstream impact. He switches the shift from 32×5 to 25×3 mid-run with a single action; AIS alerts loading, gate pass, and sales automatically. If a breakdown log is missing, AIS keeps the ticket open until the root cause is recorded. Planning becomes proactive, not retrospective.

**Requirements revealed:** Production board, raw material visibility, furnace scheduling, breakdown logging with mandatory fields, attendance linkage, mid-shift change workflow, alerting.

### Journey 5: Raju (Garam Kaam Supervisor) — From Blame to Clarity
Raju runs the hottest section of the mill. Before AIS, he gets calls like "Why did the hydra take so long?" or "Why aren't we feeding the furnace?" He keeps his own handwritten notes, but when production dips, he gets blamed. Workers resent constant questioning: "We were there, sir, but nobody believed us."

**AIS Storyline:** The floor tablet shows "Shift plan: 25×3, target 15 tons, expected break time 40 minutes." Attendance auto-syncs when workers tap in. If labour is short or coal isn't fed, AIS flags it immediately; Raju reassigns labour without guesswork. When Owner or Production asks "Why a delay?" he taps the timeline: "Hydra lag—load 3 took 15 minutes longer." Workers see that accountability now rests on data, not accusations. The emotional arc is panic → calm: fewer disputes, more transparency.

**Requirements revealed:** Limited supervisor dashboard, attendance vs task view, quick reassign flows, shift timelines, alert acknowledgements.

### Journey 6: Admin/Alerts (System Owner)
The AIS admin console shows open alerts: weighbridge variance unresolved, breakdown log incomplete, pricing override awaiting approval. Previously, you would hear of these only during reconciliation; now AIS keeps them in a queue. You review a weighbridge variance (10 kg difference), decide "Within tolerance, note and close," and AIS files the decision. A breakdown ticket missing "Cause" cannot be closed until the Foreman fills it; you can nudge or escalate.

When Rajesh overrides margin limits twice in one day, AIS prompts "Approve temporary exception? (Y/N)." You approve once with a note, and the second request is auto-rejected. This journey ensures no alert is silent and every decision is traceable.

**Requirements revealed:** Admin console, alert queue, approval flows, variance decision logging, audit trails tied to user actions.

### Journey Requirements Summary

| Capability | Driven by |
|------------|-----------|
| Sales order intake & shared pricing | Prakash, Rajesh |
| Hydra & weighbridge logging with validation | Prakash, Imran |
| Gate pass automation & accounting exports | Prakash |
| Owner dashboard, CV reconciliation, financial snapshot | Adityajain |
| Competition and debtor intelligence | Rajesh |
| Production board, breakdown logging, shift adjustments | Imran |
| Limited supervisor views & alerting | Raju |
| Admin alert queue and approvals | System Owner |
| Audit trails everywhere | All journeys |

### MVP-Plus (4-6 weeks additional)

**Focus:** CV Integration + Weighbridge Auto-Integration + Intelligence

| Feature | Scope |
|---------|-------|
| **Weighbridge Auto-Integration** | Direct hardware connection — auto-capture gross, tare, net |

## Non-Functional Requirements

### Performance

| Requirement | Target | Rationale |
|-------------|--------|-----------|
| **NFR-P1: Dashboard Load Time** | Owner/Sales dashboards load within 3 seconds on standard connection | "2-minute morning glance" requires instant visibility |
| **NFR-P2: Gate Pass Generation** | Gate pass generates and displays within 2 seconds after final weight entry | Trucks waiting = operational bottleneck |
| **NFR-P3: Mobile App Response** | Hydra weight entry confirms within 1 second on 3G connection | Factory floor has variable connectivity |
| **NFR-P4: Report Generation** | Daily/weekly reports generate within 30 seconds; monthly within 2 minutes | Auto-scheduled reports run overnight; on-demand must be fast |
| **NFR-P5: Search & Filter** | Order/transaction searches return results within 2 seconds for up to 10,000 records | Historical lookups must not frustrate users |

### Reliability & Availability

| Requirement | Target | Rationale |
|-------------|--------|-----------|
| **NFR-R1: Data Durability** | Zero data loss — all entries persisted, including offline-captured data | Trust metric; single data loss event destroys adoption |
| **NFR-R2: Offline Capability** | Mobile apps (Hydra, Supervisor) function fully offline with automatic sync when connectivity restored | Factory floor connectivity is unreliable |
| **NFR-R3: Sync Conflict Resolution** | Offline-to-online sync conflicts resolved automatically with clear audit trail; user notified of any manual resolution required | Prevents data corruption during reconnection |
| **NFR-R4: System Uptime** | 99% uptime during operational hours (6 AM - 10 PM); planned maintenance windows outside peak hours | Mill operates extended hours; downtime = lost visibility |
| **NFR-R5: Backup & Recovery** | Daily automated backups; point-in-time recovery within 1 hour if needed | Disaster recovery for financial and operational data |
| **NFR-R6: Hardware Failover** | Weighbridge hardware disconnection triggers graceful degradation to manual entry within 5 seconds | Per FR13b — no blocking on hardware failure |

### Security

| Requirement | Target | Rationale |
|-------------|--------|-----------|
| **NFR-S1: Data Encryption** | All data encrypted at rest (AES-256) and in transit (TLS 1.2+) | Financial data, pricing, competitive intelligence |
| **NFR-S2: Authentication** | Secure login with session timeout (configurable, default 8 hours for factory shift length) | Prevent unauthorized access; balance with usability |
| **NFR-S3: RBAC Enforcement** | All API endpoints enforce role-based permissions; no data leakage across roles | Supervisors must not see pricing; contractors must not see production quantities |
| **NFR-S4: Audit Immutability** | Audit logs append-only; no user (including Admin) can delete or modify audit entries | Per FR39d — unchallengeable proof |
| **NFR-S5: Sensitive Data Masking** | Financial totals, pricing margins, and debtor amounts masked in supervisor views | Competitive protection from contractor-linked supervisors |
| **NFR-S6: Session Security** | Concurrent session limit per user (default: 2 devices); forced logout on password change | Prevent credential sharing |

### Industrial UX (Factory Floor Conditions)

| Requirement | Target | Rationale |
|-------------|--------|-----------|
| **NFR-U1: Touch Target Size** | Minimum 48dp touch targets on all mobile interfaces | Workers may wear gloves; precision tapping impractical |
| **NFR-U2: High Contrast Display** | UI meets WCAG AA contrast ratios; sunlight-readable mode available | Factory floor has variable lighting |
| **NFR-U3: Minimal Text Entry** | Factory floor interfaces prioritize selection/tap over keyboard input; <3 required text fields per screen | Reduce errors, increase speed |
| **NFR-U4: Sync Status Visibility** | Clear, persistent indicator showing online/offline status and pending sync count | Users must know if their data has uploaded |
| **NFR-U5: Error Recovery** | All mobile actions reversible or confirmable; no destructive single-tap actions | Prevent accidental data loss |
| **NFR-U6: Voice Input (Phase 2)** | Voice-to-text option for notes/comments on mobile interfaces | Hands-busy scenarios during loading |

### Integration Reliability

| Requirement | Target | Rationale |
|-------------|--------|-----------|
| **NFR-I1: Weighbridge Connection** | Auto-reconnect within 30 seconds of connection restoration; no data loss during disconnection | Per FR13c — seamless hardware recovery |
| **NFR-I2: CV Feed Resilience** | CV module continues processing from last known state after camera feed interruption; gap logged for manual review | Production visibility must not have silent gaps |
| **NFR-I3: WhatsApp API Fallback** | If WhatsApp API unavailable, manual rate entry interface remains functional; no blocking on external service | Per FR30 — competition intelligence must flow |
| **NFR-I4: Accounting Export Reliability** | Export to Tally/Zoho formats validated before delivery; failed exports retry 3x then alert Accountant | Prevent silent export failures |
| **NFR-I5: API Rate Limiting** | External API calls (WhatsApp, accounting) respect rate limits with exponential backoff | Prevent service bans |

### Scalability (Future-Proofing)

| Requirement | Target | Rationale |
|-------------|--------|-----------|
| **NFR-SC1: Tenant Isolation** | All data queries scoped by tenant_id; no cross-tenant data leakage | Per SaaS B2B requirements — multi-plant future |
| **NFR-SC2: Data Growth** | System handles 3 years of transaction history without performance degradation | Historical analysis requires long retention |
| **NFR-SC3: Concurrent Users** | Support 15 concurrent users per tenant without performance impact | All roles active during peak operational hours |

*Note: Accessibility (WCAG compliance beyond contrast ratios) is not included as AIS serves internal factory users only with no public-facing interface or regulatory requirement.*