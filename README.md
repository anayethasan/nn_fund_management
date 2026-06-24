# nn_fund_management — Odoo 18 Custom Module
 
**Company:** NN Services & Engineering Ltd.
**Position:** Trainee Software Developer — Technical Assessment
**Module:** Fund Management System
 
---
 
## Personal Overview (About This Submission)
 
Before this task, I had zero practical experience with Odoo module development. I started by learning the basics — Odoo's MVC architecture, how models work, what `@api.depends` and `@api.constrains` do, and how XML views connect to Python models. I then built this module with AI assistance, which helped me write boilerplate faster and understand patterns I hadn't seen before.
 
The most important thing I focused on was **understanding every line of code** — not just copying it. I made deliberate decisions about the balance logic, the approval sequence enforcement, and the double-spending prevention mechanism.
 
### What I Learned
- How Odoo models, computed fields, and `store=True` work together
- How to enforce workflow sequences in Python (GM must approve before MD)
- How `_sql_constraints` vs `@api.constrains` differ and when to use each
- How record rules and ACL CSV files provide layered security
- How `noupdate="1"` in XML data works and why it matters for sequences

## Development Process & AI Assistance

This project was developed within a limited timeframe of approximately **5–6 days**. Prior to starting the project, I had no practical experience with Odoo development. Therefore, I first learned the fundamentals of Odoo, including module structure, models, views, security, workflows, and ORM concepts.

The overall system architecture, database design, module structure, workflow planning, and business requirement analysis were designed and planned by me.

To accelerate development and better understand Odoo concepts, I used AI as a learning and development assistant. AI was primarily used for:

- Understanding Odoo 18 development patterns and best practices
- Exploring different implementation approaches
- Generating initial code drafts for models, views, and workflows
- Reviewing business logic ideas
- Assisting with debugging and error resolution

All AI-generated code was manually reviewed, tested, modified, and integrated into the project. Several generated implementations required corrections and adjustments to comply with Odoo 18 standards and project requirements.

### Examples of Changes Made

- Removed deprecated `states={}` field attributes from Python models
- Replaced deprecated XML `<tree>` views with `<list>` views
- Fixed invalid comments in `ir.model.access.csv`
- Corrected fund balance calculations and allocation state handling
- Refined approval workflows and business validation logic
- Added project-specific validations and constraints

The final implementation, business rules, workflow decisions, testing, debugging, and integration were completed and verified manually.

---

## How AI Was Used During Development

AI was used as a development assistant throughout the project. Some examples of assistance received include:

### System Design & Architecture

- Designing data models for the fund management system
- Planning relationships between Fund Account, Incoming Fund, Project, Allocation, Requisition, Transfer, and Bill modules
- Reviewing approaches to prevent double-spending and maintain balance consistency

### Workflow Development

- Generating draft implementations for approval workflows
- Reviewing GM and MD approval processes
- Assisting with state transition logic and validation rules

### Odoo 18 Compatibility

- Creating XML views using Odoo 18 conventions
- Reviewing model definitions and ORM usage
- Identifying deprecated syntax and suggesting alternatives

### Debugging & Improvements

- Investigating validation and workflow issues
- Reviewing balance calculation logic
- Helping identify edge cases and implementation gaps

AI-generated outputs were used as references and starting points. The final codebase was reviewed, customized, corrected, and adapted to meet the project's actual business requirements and Odoo 18 standards.
 
## Odoo Version
 
**Odoo 18.0**
 
---
 
## Module Structure
 
```
nn_fund_management/
├── models/
│   ├── fund_account.py          # FundAccount + computed balances
│   ├── incoming_fund.py         # IncomingFund, unique ref constraint
│   ├── project_expense.py       # Project/ExpenseHead, all balance fields
│   ├── approval_history.py      # Shared immutable audit log
│   ├── fund_allocation.py       # Core hold/release logic ★
│   ├── fund_requisition.py      # Requisition + remaining_billable
│   ├── fund_transfer.py         # Transfer between projects/expenses
│   └── fund_bill.py             # Bill linked to requisition
├── views/
│   ├── fund_account_views.xml
│   ├── incoming_fund_views.xml
│   ├── project_expense_views.xml
│   ├── approval_history_views.xml
│   ├── fund_allocation_views.xml
│   ├── fund_requisition_views.xml
│   ├── fund_transfer_views.xml
│   ├── fund_bill_views.xml
│   └── menu.xml
├── security/
│   ├── security.xml             # 5 security groups
│   ├── ir.model.access.csv      # ACL per model per group
│   └── record_rules.xml         # Company-based row-level rules
├── data/
│   └── sequences.xml            # ALLOC/, REQ/, TRANS/, BILL/
├── docker-compose.yml
├── __manifest__.py
└── __init__.py
```
 
---
 
## Required Dependencies
 
- **Odoo 18.0** (Community or Enterprise)
- **Python 3.10+**
- **PostgreSQL 14+**
- **Docker & Docker Compose** (for containerized setup)
Odoo module dependencies (declared in `__manifest__.py`):
- `base`
- `mail` (for chatter and tracking)
- `account` (for monetary fields and currency)
---
 
## Installation Instructions
 
### Option A — Docker (Recommended)
 
```bash
# 1. Clone or place the module
git clone <your-repo-url>
cd <project-folder>
 
# 2. Start containers
docker-compose up -d
 
# 3. Wait ~30 seconds for Odoo to start, then open browser
open http://localhost:8069
 
# 4. Create a new database (or use existing)
#    Database name: odoo18
#    Email: admin@admin.com
#    Password: admin
 
# 5. Enable developer mode
#    Settings → General Settings → scroll to bottom → Activate Developer Mode
 
# 6. Install the module
#    Apps → search "NN Fund Management" → Install
```
 
### Option B — Manual (existing Odoo 18 instance)
 
```bash
# 1. Copy module to Odoo addons path
cp -r nn_fund_management /path/to/odoo/custom_module/
 
# 2. Restart Odoo server
./odoo-bin -c odoo.conf --stop-after-init -u all
 
# 3. Update module list in Odoo UI
#    Apps → Update Apps List
 
# 4. Install "NN Fund Management" from Apps menu
```
 
---
 
## Configuration Steps
 
1. **Assign Security Groups** — Go to Settings → Users → select a user → assign one of:
   - `Fund User` — can create requests
   - `Finance User` — can confirm incoming funds and post bills
   - `GM Approver` — first-level approval
   - `MD Approver` — final approval
   - `Fund Administrator` — full access (admin user gets this automatically)
2. **Create Fund Accounts** — Fund Management → Configuration → Fund Accounts → New
   - Set name, account type (bank/cash/other), currency
3. **Create Projects / Expense Heads** — Fund Management → Budget → Projects / Expense Heads
4. **Record Incoming Funds** — Fund Management → Fund Accounts → Incoming Funds → New
   - Finance User must confirm each incoming fund to add it to the unassigned balance
---
 
## Testing Instructions
 
Follow the assessment demo scenario step by step:
 
```
1.  Log in as Finance User
    → Record BDT 1,000,000 incoming fund → Confirm it
    → Fund Account should show: Available = 1,000,000
 
2.  Log in as Fund User
    → Create Allocation Request: BDT 600,000 → Project A → Submit
    → Fund Account should show: Available = 400,000 | On Hold = 600,000
 
3.  Try to create another allocation for BDT 500,000
    → System should BLOCK with "Insufficient unassigned balance"
 
4.  Log in as GM Approver → Reject the 600,000 allocation
    → Fund Account should show: Available = 1,000,000 | On Hold = 0
 
5.  Resubmit the 600,000 allocation → GM Approve → MD Approve
    → Project A: Available = 600,000
 
6.  Create Transfer: Project A → Project B, BDT 200,000 → Submit
    → Project A: Available = 400,000 | Transfer Hold = 200,000
 
7.  GM Approve → MD Approve the transfer
    → Project A: Available = 400,000 | Project B: Available = 200,000
 
8.  Create Requisition for Project B: BDT 150,000 → Submit → Approve
    → Project B: Available = 50,000 | Req Hold = 150,000
 
9.  Create Bill: BDT 100,000 against the requisition → Post
    → Requisition: Remaining Billable = 50,000
 
10. Try to create Bill for BDT 60,000
    → System should BLOCK: "exceeds remaining billable"
 
11. Try to use Project B's requisition for Project A
    → System should BLOCK: project_expense_id is locked to the requisition
```
 
---
 
## Implemented Features 
 
| Feature | Status |
|---------|--------|
| Fund Accounts with computed balances 
| Incoming Funds with unique transaction reference 
| Projects and Expense Heads with full balance tracking 
| Fund Allocation with GM + MD approval workflow 
| Double-spending prevention (hold/release logic) 
| Fund Requisition with remaining_billable tracking
| Fund Transfers between projects/expense heads
| Fund Bills linked to requisitions 
| Immutable Approval History (audit log)
| 5 Security Groups with ACL and record rules
| Company-based row-level security
| Auto-numbering sequences (ALLOC/, REQ/, TRANS/, BILL/)
| Odoo 18 compatible XML views
| Docker setup
 
## Skipped Features  
 
| Feature | Reason Skipped |
|---------|----------------|
| Email / Bank notification integration | Bonus feature — requires IMAP setup and external credentials |
| Dashboard with charts | Bonus feature |
| Odoo activity/notification system | Bonus feature |
| Configurable approval rules by amount range | Bonus feature — current workflow is hardcoded GM → MD |
| Automated tests (`tests/` folder) | Time constraint — manual testing covered via demo scenario |
 
---
 
## Assumptions
 
1. A single approval chain (GM → MD) applies to all request types and all amounts. Configurable rules by amount range were not implemented.
2. One `nn.project.expense` model handles both Projects and Expense Heads, differentiated by the `budget_type` field.
3. Currency is fixed per Fund Account and inherited by all related documents.
4. "Company" multi-tenancy is supported through record rules — users only see records from their own company.
5. Approved allocations cannot be directly cancelled — a reverse transfer must be used to move funds back. This prevents accidental loss of audit trail.
6. Bills are a custom model (`nn.fund.bill`) rather than Odoo's native `account.move` — this keeps the module simpler and avoids dependency on full accounting configuration.
7. The `account` module is listed as a dependency only for monetary field currency support, not full accounting integration.
---
 
## Known Limitations
 
1. **No automated tests** — `tests/` directory and `TransactionCase` unit tests are not included. All validation was done manually following the demo scenario.
2. **Single approval chain** — the GM → MD sequence is fixed. The bonus "configurable approval rules" feature (e.g., amounts under BDT 50,000 need only GM approval) is not implemented.
3. **No dashboard** — there is no summary dashboard view. Balance information is visible per-record on Fund Accounts and Project/Expense Head forms.
4. **No email notifications** — Odoo activities and email alerts when approval is required are not set up.
5. **No bank email integration** — the bonus email parsing feature is not implemented.
6. **Bill model is custom** — bills are not linked to Odoo's native vendor bill (`account.move`). This means bills do not appear in accounting reports.
7. **Balance recompute is triggered manually** — `_compute_balances()` is called explicitly in workflow methods. In rare concurrent scenarios, a full recompute may be needed: `Settings → Technical → Scheduled Actions`.
---
 
## Architecture Notes
 
### Double-Spending Prevention
 
The core mechanism works at the database transaction level:
 
```
Allocation Submit:
  unassigned_balance -= amount   (computed field: state moves to 'submitted')
  held_amount       += amount
 
  → Any new request calling action_submit() checks unassigned_balance BEFORE
    changing state. Since held funds are excluded from unassigned, concurrent
    requests are automatically blocked.
 
Allocation Approve:
  held_amount       -= amount
  assigned_amount   += amount   (project.available_balance increases)
 
Allocation Reject/Cancel:
  held_amount       -= amount
  unassigned_balance += amount  (money returns to pool)
```
 
The same pattern applies to Requisitions (requisition_hold) and Transfers (transfer_hold).
 
### Computed vs Stored Fields
 
All balance fields use `store=True` so they are queryable and displayable in list views without N+1 queries. They are recalculated automatically when dependencies change via `@api.depends`.
 
Manual writes to balance fields are blocked both by Odoo's computed field system and by an explicit `write()` override that raises `UserError`.