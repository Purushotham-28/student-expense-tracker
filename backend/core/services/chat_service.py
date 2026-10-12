"""
core/services/chat_service.py
Phase 8 — AI Chatbox (Claude API with Function Calling)

Features:
  - Conversational AI powered by Anthropic Claude (claude-sonnet-4-6).
  - Multi-turn function calling with real backend financial data:
      1. add_expense(amount, item, category, date, payee)
      2. get_spending_summary(category, start_date, end_date)
      3. get_runway()
      4. run_whatif(category, reduce_percent)
      5. get_goal_status(goal_name)
      6. get_health_score()
  - Strict guardrails for student budgeting only (no investment/legal advice).
  - Robust tool execution loop with graceful offline fallback when API key is unset.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Sum

from ..models import Transaction, Statement, Goal, ExpenseCategory, ChatMessage
from .forecasting_service import calculate_cash_flow_runway, simulate_whatif_adjustments
from .goal_service import check_goal_progress_and_suggest_cut, calculate_goal_metrics
from .health_score_service import get_user_financial_health_score

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the AI Financial Copilot for the Student Expense Tracker (Campus Edition).
Your mission is to help university students budget intelligently, understand their spending patterns, track savings goals, and maintain financial peace of mind.

Strict Guidelines:
1. Real Data Grounding: Always query real data using your tools before answering questions about expenses, runway, goals, or health score. Always cite the specific figures returned by your tools (amounts, dates, days, scores).
2. Scope Limitation: You ONLY provide personal student budgeting guidance and expense insights. You are STRICTLY PROHIBITED from giving investment advice (stocks, crypto, trading, equity funds), tax advice, or legal counsel. If asked about investments, politely explain that you specialize in student budgeting and campus cash-flow.
3. Friendly & Practical: Keep answers conversational, empathetic to student realities, and actionable."""

# ──────────────────────────────────────────────────────────────────────────────
# Tool Definitions for Anthropic API
# ──────────────────────────────────────────────────────────────────────────────

CLAUDE_TOOLS = [
    {
        "name": "add_expense",
        "description": "Logs a new expense transaction for the student (e.g. coffee, textbooks, food).",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount": {
                    "type": "number",
                    "description": "Amount spent in Indian Rupees (₹).",
                },
                "item": {
                    "type": "string",
                    "description": "Description of the expense or item purchased (e.g. 'Chai and Samosa', 'Metro pass').",
                },
                "category": {
                    "type": "string",
                    "description": "Expense category (Food, Travel, Groceries/Shopping, Subscriptions, Rent/Hostel, Academics, Entertainment, Other).",
                },
                "date": {
                    "type": "string",
                    "description": "Date of transaction in YYYY-MM-DD format (defaults to today if omitted).",
                },
                "payee": {
                    "type": "string",
                    "description": "Name of the merchant or payee (optional).",
                },
            },
            "required": ["amount", "item"],
        },
    },
    {
        "name": "get_spending_summary",
        "description": "Queries the student's historical spending summary, optionally filtered by category and date range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Filter by category like 'Food', 'Travel', 'Entertainment' or 'all'.",
                },
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format.",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format.",
                },
            },
        },
    },
    {
        "name": "get_runway",
        "description": "Calculates the student's cash-flow runway, showing current balance, daily burn rate, and projected date funds will run out.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "run_whatif",
        "description": "Simulates a what-if spending adjustment (e.g. reducing Food spending by 30%) and calculates extended runway days and 30-day savings.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Category to adjust (e.g. 'Food', 'Entertainment', 'Groceries/Shopping').",
                },
                "reduce_percent": {
                    "type": "number",
                    "description": "Percentage reduction (e.g. 20, 30, 50).",
                },
            },
            "required": ["category", "reduce_percent"],
        },
    },
    {
        "name": "get_goal_status",
        "description": "Fetches current savings goal progress, adaptive weekly targets, and checks whether the student is on track or falling behind.",
        "input_schema": {
            "type": "object",
            "properties": {
                "goal_name": {
                    "type": "string",
                    "description": "Specific goal name to check (e.g. 'Laptop', 'Exam fees'), or leave empty for all active goals.",
                },
            },
        },
    },
    {
        "name": "get_health_score",
        "description": "Fetches the student's 0-100 Financial Health Score, including savings rate, budget adherence, spending volatility, and tips.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
]

# ──────────────────────────────────────────────────────────────────────────────
# Local Tool Execution Logic (Phases 2-7 Services)
# ──────────────────────────────────────────────────────────────────────────────

def execute_chat_tool(user: User, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Executes a requested tool function using real backend data for the user.
    """
    try:
        if tool_name == "add_expense":
            amount = float(tool_args.get("amount", 0.0))
            item = str(tool_args.get("item", "Expense"))
            cat = tool_args.get("category") or "Other"
            payee = tool_args.get("payee") or item
            tx_date_str = tool_args.get("date")

            if tx_date_str:
                try:
                    tx_date = datetime.strptime(tx_date_str, "%Y-%m-%d").date()
                except ValueError:
                    tx_date = date.today()
            else:
                tx_date = date.today()

            # Ensure an active statement exists for manual logging
            stmt, _ = Statement.objects.get_or_create(
                user=user,
                original_filename="manual_chat_entries.csv",
                defaults={"status": Statement.Status.DONE, "bank_format": "manual"},
            )

            tx = Transaction.objects.create(
                statement=stmt,
                user=user,
                date=tx_date,
                amount=Decimal(str(amount)),
                is_debit=True,
                payee_name=payee,
                remark=item,
                category=cat,
                confidence=1.0,
                status=Transaction.ParseStatus.AUTO,
            )
            return {
                "success": True,
                "message": f"Successfully logged ₹{amount:,.2f} for '{item}' in category '{cat}'.",
                "transaction_id": tx.id,
                "amount": float(tx.amount),
                "item": tx.remark,
                "category": tx.category,
                "date": tx.date.isoformat(),
            }

        elif tool_name == "get_spending_summary":
            cat = tool_args.get("category")
            start_date_str = tool_args.get("start_date")
            end_date_str = tool_args.get("end_date")

            qs = Transaction.objects.filter(user=user, is_debit=True, is_deleted=False, is_duplicate=False)

            if cat and cat.lower() != "all":
                qs = qs.filter(category__iexact=cat)

            if start_date_str:
                try:
                    s_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
                    qs = qs.filter(date__gte=s_date)
                except ValueError:
                    pass

            if end_date_str:
                try:
                    e_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
                    qs = qs.filter(date__lte=e_date)
                except ValueError:
                    pass

            total_spent = float(qs.aggregate(s=Sum("amount"))["s"] or 0.0)
            count = qs.count()
            avg_per_tx = round(total_spent / count, 2) if count > 0 else 0.0

            # Group top 3 payees
            payees = {}
            for t in qs:
                p = t.payee_name or t.remark or "Unknown"
                payees[p] = payees.get(p, 0.0) + float(t.amount or 0.0)
            top_payees = sorted(payees.items(), key=lambda x: x[1], reverse=True)[:3]

            return {
                "category": cat or "All",
                "total_spent": round(total_spent, 2),
                "transaction_count": count,
                "average_transaction": avg_per_tx,
                "top_payees": [{"payee": p, "amount": round(a, 2)} for p, a in top_payees],
            }

        elif tool_name == "get_runway":
            runway_data = calculate_cash_flow_runway(user=user)
            return {
                "current_balance": runway_data.get("current_balance"),
                "runway_date": runway_data.get("runway_date"),
                "runway_days": runway_data.get("runway_days"),
                "daily_burn_rate": runway_data.get("daily_burn_rate"),
                "is_exhausted": runway_data.get("is_exhausted"),
                "method": runway_data.get("method"),
            }

        elif tool_name == "run_whatif":
            category = tool_args.get("category", "Food")
            reduce_percent = float(tool_args.get("reduce_percent", 30))
            res = simulate_whatif_adjustments(
                user=user, adjustments={category: reduce_percent}
            )
            return {
                "category": category,
                "reduce_percent": reduce_percent,
                "original_runway_date": res.get("original_runway_date"),
                "adjusted_runway_date": res.get("adjusted_runway_date"),
                "days_saved": res.get("days_saved"),
                "money_saved_30d": res.get("money_saved_30d"),
                "adjusted_daily_burn": res.get("adjusted_daily_burn"),
            }

        elif tool_name == "get_goal_status":
            goal_name = tool_args.get("goal_name")
            qs = Goal.objects.filter(user=user)
            if goal_name:
                qs = qs.filter(name__icontains=goal_name)

            goals_list = [calculate_goal_metrics(g) for g in qs]
            diag = check_goal_progress_and_suggest_cut(user=user)
            return {
                "goals": goals_list,
                "is_behind": diag.get("is_behind"),
                "needed_weekly_rate": diag.get("needed_weekly_rate"),
                "weekly_deficit": diag.get("weekly_deficit"),
                "suggested_cut_category": diag.get("suggested_category"),
                "recommended_reduction_percent": diag.get("recommended_reduction_percent"),
            }

        elif tool_name == "get_health_score":
            return get_user_financial_health_score(user=user)

        else:
            return {"error": f"Unknown tool: '{tool_name}'"}
    except Exception as e:
        logger.exception(f"Error executing tool {tool_name}: {e}")
        return {"error": f"Tool execution failed: {str(e)}"}


# ──────────────────────────────────────────────────────────────────────────────
# Smart Offline Fallback Engine (when API key is unset or in mock mode)
# ──────────────────────────────────────────────────────────────────────────────

def run_offline_agent(user: User, user_message: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Intelligent tool-augmented fallback agent used when ANTHROPIC_API_KEY is not configured.
    Detects user intent, executes the real backend tool, and constructs an authoritative,
    grounded response citing the real numbers.
    """
    text = user_message.lower()
    tools_used = []

    # 1. Add expense intent (e.g. "log 150 for chai", "add expense 200 on food")
    log_match = re.search(r'(?:log|add|spent|spend)\s+(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?)\s*(?:for|on)?\s*([a-zA-Z0-9\s&]+)?', text)
    if ("log" in text or "add" in text or "spent" in text) and log_match:
        amount = float(log_match.group(1))
        item = (log_match.group(2) or "General Expense").strip()
        category = "Food"
        if any(w in item.lower() for w in ["uber", "metro", "auto", "bus", "travel"]):
            category = "Travel"
        elif any(w in item.lower() for w in ["book", "exam", "college", "tuition"]):
            category = "Academics"
        elif any(w in item.lower() for w in ["movie", "game", "netflix"]):
            category = "Entertainment"

        res = execute_chat_tool(user, "add_expense", {"amount": amount, "item": item, "category": category})
        tools_used.append({"tool": "add_expense", "result": res})
        return (
            f"✅ Done! I've logged an expense of **₹{amount:,.2f}** for **'{item}'** under **{category}**.\n\n"
            f"This has been recorded to your transaction history and factored into your live budget.",
            tools_used,
        )

    # 2. Runway intent (e.g. "when will money run out", "runway", "can i afford 500")
    if any(w in text for w in ["runway", "run out", "afford", "balance", "how long", "weekend"]):
        res = execute_chat_tool(user, "get_runway", {})
        tools_used.append({"tool": "get_runway", "result": res})
        bal = res.get("current_balance", 0.0)
        days = res.get("runway_days", 0)
        r_date = res.get("runway_date", "N/A")
        burn = res.get("daily_burn_rate", 0.0)

        # Afford check
        num_match = re.search(r'(\d+)', text)
        check_amt = float(num_match.group(1)) if num_match and "afford" in text else None

        if check_amt is not None:
            if bal >= check_amt and days > 5:
                return (
                    f"Yes, you have **₹{bal:,.2f}** in available funds with **{days} days** of cash runway remaining (until **{r_date}**).\n\n"
                    f"Spending ₹{check_amt:,.2f} will leave you with approximately ₹{max(0.0, bal - check_amt):,.2f}, so you can comfortably afford it while staying on track.",
                    tools_used,
                )
            else:
                return (
                    f"⚠️ Caution: Your current balance is **₹{bal:,.2f}** and your runway is projected to end on **{r_date}** ({days} days remaining at ₹{burn:,.2f}/day).\n\n"
                    f"Spending ₹{check_amt:,.2f} would take up a significant share of your remaining buffer. Consider trimming discretionary spend first.",
                    tools_used,
                )

        return (
            f"📊 **Cash-Flow Runway Report**:\n"
            f"• Current Balance: **₹{bal:,.2f}**\n"
            f"• Daily Burn Rate: **₹{burn:,.2f}/day**\n"
            f"• Projected Depletion Date: **{r_date}** ({days} days left)\n\n"
            f"Based on your daily spending pattern, funds are estimated to last until {r_date}.",
            tools_used,
        )

    # 3. Spending summary intent (e.g. "how much did i spend on food", "spending")
    if any(w in text for w in ["spend", "spent", "food", "travel", "summary"]):
        cat = "Food" if "food" in text else ("Travel" if "travel" in text else "All")
        res = execute_chat_tool(user, "get_spending_summary", {"category": cat})
        tools_used.append({"tool": "get_spending_summary", "result": res})
        total = res.get("total_spent", 0.0)
        count = res.get("transaction_count", 0)
        avg = res.get("average_transaction", 0.0)
        return (
            f"🍽️ **Spending Summary ({cat})**:\n"
            f"• Total Spent: **₹{total:,.2f}** across {count} transactions\n"
            f"• Average per Transaction: **₹{avg:,.2f}**\n\n"
            f"Keep tabs on this category in your Runway simulator to extend your end-of-month runway.",
            tools_used,
        )

    # 4. Goals intent (e.g. "goal", "laptop", "save")
    if any(w in text for w in ["goal", "goals", "laptop", "save", "saving", "behind"]):
        res = execute_chat_tool(user, "get_goal_status", {})
        tools_used.append({"tool": "get_goal_status", "result": res})
        goals = res.get("goals", [])
        is_behind = res.get("is_behind", False)

        if not goals:
            return (
                "🎯 You don't have any active goals right now. Head over to the **Goals** tab to set a target for a laptop, exam fees, or placement prep!",
                tools_used,
            )

        g = goals[0]
        status_line = (
            f"⚠️ You are falling behind by ₹{res.get('weekly_deficit', 0):,.2f}/week. Consider trimming {res.get('suggested_cut_category', 'Food')}."
            if is_behind
            else "✅ Your savings velocity is currently on schedule!"
        )
        return (
            f"🎯 **Goal Progress: {g['name']}**\n"
            f"• Saved: **₹{g['saved_so_far']:,.2f}** of **₹{g['target_amount']:,.2f}** ({g['progress_percentage']}%)\n"
            f"• Adaptive Weekly Target: **₹{g['weekly_target']:,.2f}/week** ({g['days_remaining']} days left)\n"
            f"• Status: {status_line}",
            tools_used,
        )

    # 5. Health score intent
    if any(w in text for w in ["health", "score", "financial health"]):
        res = execute_chat_tool(user, "get_health_score", {})
        tools_used.append({"tool": "get_health_score", "result": res})
        score = res.get("total_score", 0)
        grade = res.get("grade", "B")
        status_lbl = res.get("status", "Good")
        tips = res.get("tips", [])
        tips_bullets = "\n".join(f"• {t}" for t in tips)
        return (
            f"🏆 **Financial Health Score: {score}/100 (Grade {grade} — {status_lbl})**\n\n"
            f"**Key Recommendations**:\n{tips_bullets}",
            tools_used,
        )

    # 6. What-if simulation intent
    if any(w in text for w in ["what if", "cut", "reduce", "trim"]):
        res = execute_chat_tool(user, "run_whatif", {"category": "Food", "reduce_percent": 30})
        tools_used.append({"tool": "run_whatif", "result": res})
        days_gained = res.get("days_saved", 0)
        saved_30d = res.get("money_saved_30d", 0.0)
        return (
            f"💡 **What-If Simulation Result (Food -30%)**:\n"
            f"• Estimated 30-Day Savings: **₹{saved_30d:,.2f}**\n"
            f"• Additional Runway Gained: **+{days_gained} days**\n\n"
            f"Cutting food delivery by 30% gives your cash flow a meaningful boost!",
            tools_used,
        )

    # General greeting / fallback
    return (
        "👋 Hello! I'm your AI Financial Copilot. I have live access to your transactions, cash runway, goals, and financial health score.\n\n"
        "Try asking me:\n"
        "• *'How much did I spend on food?'*\n"
        "• *'Can I afford ₹500 this weekend?'*\n"
        "• *'Log ₹120 for Chai & Samosa'*\n"
        "• *'What is my financial health score?'*",
        [],
    )


# ──────────────────────────────────────────────────────────────────────────────
# Main Chat Service Orchestrator (Claude API Multi-turn Tool Loop)
# ──────────────────────────────────────────────────────────────────────────────

def process_chat_message(
    user: User,
    message_content: str,
    max_turns: int = 5,
) -> Dict[str, Any]:
    """
    Main entry point for handling chat interactions.
    Executes multi-turn tool calling with Claude API, or uses smart offline engine
    if API key is unset. Persists ChatMessage history to database.
    """
    api_key = getattr(settings, "ANTHROPIC_API_KEY", "") or ""
    model_name = getattr(settings, "ANTHROPIC_MODEL", "claude-sonnet-4-6")

    # 1. Persist student user message
    user_msg_obj = ChatMessage.objects.create(
        user=user,
        role=ChatMessage.Role.USER,
        content=message_content,
    )

    tools_executed: List[Dict[str, Any]] = []
    final_reply = ""

    # Check if Anthropic client can be used
    if api_key and not api_key.startswith("sk-ant-api-placeholder"):
        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=api_key)

            # Assemble conversation history for context
            recent_msgs = ChatMessage.objects.filter(user=user).order_by("-created_at")[:10]
            recent_msgs = list(reversed(recent_msgs))

            claude_messages = []
            for m in recent_msgs:
                if m.role in ["user", "assistant"]:
                    claude_messages.append({
                        "role": m.role,
                        "content": m.content,
                    })

            # Multi-turn tool execution loop
            turns = 0
            while turns < max_turns:
                turns += 1
                resp = client.messages.create(
                    model=model_name,
                    max_tokens=1024,
                    system=SYSTEM_PROMPT,
                    messages=claude_messages,
                    tools=CLAUDE_TOOLS,
                )

                # Check if model wants to call tools
                if resp.stop_reason == "tool_use":
                    # Collect assistant's tool-call response content block
                    claude_messages.append({
                        "role": "assistant",
                        "content": resp.content,
                    })

                    # Run each tool use block
                    tool_result_contents = []
                    for block in resp.content:
                        if getattr(block, "type", "") == "tool_use":
                            t_name = block.name
                            t_args = block.input or {}
                            t_id = block.id

                            result = execute_chat_tool(user, t_name, t_args)
                            tools_executed.append({
                                "tool": t_name,
                                "arguments": t_args,
                                "result": result,
                            })

                            tool_result_contents.append({
                                "type": "tool_result",
                                "tool_use_id": t_id,
                                "content": json.dumps(result),
                            })

                    # Send tool results back to model
                    claude_messages.append({
                        "role": "user",
                        "content": tool_result_contents,
                    })
                else:
                    # Model provided text answer (stop_reason == "end_turn")
                    text_parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
                    final_reply = "\n".join(text_parts)
                    break

        except Exception as e:
            logger.warning(f"Anthropic API call failed ({e}), falling back to offline engine.")
            final_reply, tools_executed = run_offline_agent(user, message_content)
    else:
        # Offline mode / test suite
        final_reply, tools_executed = run_offline_agent(user, message_content)

    # 2. Persist assistant response
    asst_msg_obj = ChatMessage.objects.create(
        user=user,
        role=ChatMessage.Role.ASSISTANT,
        content=final_reply,
        tool_calls=tools_executed if tools_executed else None,
    )

    return {
        "reply": final_reply,
        "tools_executed": tools_executed,
        "message_id": asst_msg_obj.id,
        "created_at": asst_msg_obj.created_at.isoformat(),
    }
