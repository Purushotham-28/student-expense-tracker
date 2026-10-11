# Student Expense Tracker — Viva Demo Script & Walkthrough

A practical 5-step walkthrough guide for presenting the **Student Expense Tracker & Cash-Flow Planner** in a viva or technical presentation.

---

## 🚀 Quick Setup & Credentials

1. **Seed Demo Data**:
   ```bash
   cd backend
   python manage.py seed_demo_data
   ```
   *Creates a demo student with 3 months (Aug–Oct 2026) of realistic UPI transactions, ambiguous items for review, active goals, and precalculated health scores.*

2. **Access App**:
   - URL: **http://127.0.0.1:5173/**
   - Username: `student`
   - Password: `password123`
   - Roll Number: `CS2026-089`

---

## 🎬 5-Step Viva Walkthrough

### Step 1: Login & Unified Dashboard Walkthrough
> **Goal**: Show cohesive dashboard architecture, monthly budget tracking, health score, and active budget alerts.

1. **Log in** with `student` / `password123`.
2. **Explain the Header**:
   - Displays Student Roll Number (`CS2026-089`), Monthly Budget Cap (`₹15,000`), and days remaining in the month.
3. **Point out the Budget Alert Banner**:
   - Notice the amber banner: **"Food Approaching Budget Cap (80%+)"**.
   - *Talking point*: "The backend automatically monitors category burn rates against benchmark allocations. When a category crosses 80% or 100% of its share, a proactive alert banner and toast are generated."
4. **Metrics Row (Budget vs Actual)**:
   - Monthly Cap: `₹15,000` | Total Month Outflow: `₹7,083` | Remaining Allowance: `₹7,917` (approx. `₹395/day` safe allowance).
5. **Category Spending Breakdown**:
   - Toggle between the **Pie Chart** and **Budget vs Actual Bar Chart**.
   - Highlight the category share progress bars showing Food, Travel, Groceries, Subscriptions, and Rent.
6. **Financial Health Score Card (Phase 7)**:
   - Displays a score of **~90/100 (Grade A+)**.
   - Explain the 3 weighted components:
     - **Savings Rate Component (40 pts)**: Monthly savings relative to income/stipend.
     - **Budget Adherence Component (30 pts)**: Category-level limit discipline.
     - **Volatility Component (30 pts)**: Inverse coefficient of variation of weekly spend (steadier spending scores higher).
   - Show the dynamic, rule-based tips generated based on the lowest sub-score.

---

### Step 2: Bank Statement Upload & Pluggable Parsing
> **Goal**: Demonstrate document parsing of bank/UPI statements into structured transaction rows.

1. Click **Upload** in the navigation bar (`/upload`).
2. Drag and drop `backend/core/fixtures/sbi_sample.csv` (or click to browse).
3. Click **Upload Statement**:
   - Watch the animated progress bar.
   - Observe the success banner: *"Successfully parsed 4 transaction(s)"*, displaying date ranges and detected format (`sbi_csv`).
4. *Talking point*: "We implemented a pluggable parser architecture (`StatementParser` base class with concrete subclasses for `SBICSVParser`, `HDFCPDFParser`, and `GenericCSVParser`). Format auto-detection runs synchronously before extraction using `pandas` and `pdfplumber`."

---

### Step 3: Confidence-Based Routing & "Needs Your Help" Review Queue
> **Goal**: Demonstrate the core differentiator — machine learning with human-in-the-loop review.

1. Click **Transactions** in the navigation bar (`/transactions`).
2. Show the summary pills at the top:
   - Total Transactions | Auto-Categorized (≥80%) | Needs Help (<50%) | To Verify (50%–80%).
3. Click the **Review Queue** tab:
   - Notice ambiguous payees grouped cleanly (e.g. `Sharma Xerox & Print`, `AMZN-IN*STUDY-LAMP`, `GPay/Chirag/Mess-Split`).
4. **Demonstrate One-Tap Confirmation**:
   - For `Sharma Xerox & Print`, click **Academics** button.
   - Note that **"Apply to all from this payee"** is checked by default.
   - The transaction immediately confirms with confidence 1.0, upserts a `PayeeMapping` in SQLite, and resolves all past/future transactions from this payee.
5. *Talking point*: "Students only review transactions where the hybrid engine is uncertain (confidence < 0.80). Every manual confirmation trains the user's personal Payee Mapping table, so the system gets smarter with every statement upload."

---

### Step 4: Cash-Flow Runway & What-If Simulator
> **Goal**: Show forecasting and adaptive goal planning backed by statistical modeling.

1. Click **Runway** in the navigation bar (`/runway`) or click **"Try What-If Simulator"** from the Dashboard.
2. **Inspect the Baseline Forecast**:
   - View the historical spending curve (actuals) followed by the 30-day forecasted spending line (ARIMA / Prophet model) and declining balance trajectory.
   - View the projected **Runway Depletion Date** (e.g. `November 11, 2026 — 31 days of funds remaining`).
3. **Simulate a What-If Scenario**:
   - Under the simulator controls, slide the **Food** slider to **30% reduction** and **Entertainment** to **40% reduction**.
   - Notice the live recalculation:
     - Extended runway date (saves +6 to +8 additional days).
     - Projected 30-day savings: `₹1,200+`.
4. Click **Goals** in the navigation bar (`/goals`):
   - Show active goals: *"MacBook Pro for Coding"* and *"Placement Coding Bootcamp"*.
   - Point out the **Adaptive Weekly Target** (`target - saved / weeks_remaining`).
   - Click **"I'm Behind — What to Cut?"** to show discretionary cut suggestions driven by Phase 5 forecasting.

---

### Step 5: Conversational AI Copilot (Claude API Function Calling)
> **Goal**: Demonstrate grounded, multi-turn AI chatbox backed by real database data, not LLM hallucinations.

1. Click the floating **AI Copilot** button at the bottom right (or navigate to **Chat** in the nav bar).
2. **Query 1 — Spending Summary**:
   - Click the chip: *"How much did I spend on food this month?"*
   - **Observe the result**:
     - Assistant cites the exact amount: `₹3,970.00 across 5 transactions`, top payees (`Hostel Mess Advance`, `Dominos`, `Swiggy`), and daily average.
     - Notice the badge: `⚡ get_spending_summary`.
3. **Query 2 — Affordability & Runway Check**:
   - Type: *"Can I afford ₹500 for a concert this weekend?"*
   - Assistant executes `get_runway` tool, compares against the daily burn rate (₹643/day) and remaining allowance (₹7,917), and gives concrete, non-hallucinated advice.
4. **Query 3 — Natural Language Expense Logging**:
   - Type: *"Log ₹120 for Nescafe iced tea under Food"*
   - Assistant executes `add_expense` tool, creates a real `Transaction` in the database, and responds: *"Successfully logged ₹120.00 for 'Nescafe iced tea' under Food"*.
   - Refresh the dashboard to show the new expense immediately reflected in the ledger.
5. *Talking point*: "The Claude API key is kept strictly in the backend `.env`. The backend uses Anthropic tool definitions (`add_expense`, `get_spending_summary`, `get_runway`, `run_whatif`, `get_goal_status`, `get_health_score`). When the model requests a tool, Django executes the service locally and returns real numbers in a multi-turn execution loop."

---

## 💡 Viva Q&A Reference

| Expected Examiner Question | Recommended Response |
| :--- | :--- |
| **Why use a Hybrid Categorizer instead of asking Claude for every transaction?** | Querying an LLM for 100+ transactions per statement is slow (10–20s) and costly. Our hybrid engine checks exact `PayeeMapping` first (O(1) database lookup, 100% precision), falls back to a calibrated scikit-learn classifier (5ms latency), and uses Claude strictly for high-level conversational advice. |
| **How does Confidence-Based Routing reduce student fatigue?** | Transactions with confidence ≥0.80 are auto-cleared. Transactions with 0.50–0.80 are marked 'verify', and <0.50 marked 'pending'. Students only review 5–10% of transactions, sorted by amount descending so large unknowns are resolved first. |
| **How does the Runway Forecasting handle new users with few transactions?** | We implement a cold-start fallback hierarchy: If historical days < 14 or ARIMA non-stationary fit fails, it falls back to a rolling 7-day weighted average daily burn rate, preventing crashes and guaranteeing a projected runway date. |
| **How is the AI Chatbox prevented from giving legal or investment advice?** | System prompt guardrails strictly restrict Claude to student budgeting advice and enforce citing actual database numbers. Multi-turn execution is capped at `max_turns=5` to prevent infinite tool loops. |
