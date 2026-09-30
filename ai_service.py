"""Gemini-powered advisory engine with rule-based fallbacks (works without an API key)."""
import json
import re
from flask import current_app
from services import trend

NEEDS = {"rent", "groceries", "utilities", "transport", "healthcare", "education"}


def _call(prompt):
    key = current_app.config.get("GEMINI_API_KEY")
    if not key:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=key)
        model = genai.GenerativeModel(current_app.config["GEMINI_MODEL"])
        return model.generate_content(prompt).text
    except Exception as exc:  # network / quota / bad key -> fall back gracefully
        current_app.logger.warning("Gemini call failed: %s", exc)
        return None


def _context(user, summary, uid):
    cur = user.currency
    lines = [f"Currency: {cur}. Target savings rate: {user.savings_goal_pct}%.",
             f"Month {summary['year']}-{summary['month']:02d}: income {summary['income']}, "
             f"expenses {summary['expenses']}, savings {summary['savings']} "
             f"({summary['savings_rate']}%). Health score {summary['health_score']}/100.",
             "Categories (spent / budget limit):"]
    for c in summary["categories"]:
        lines.append(f"- {c['name']}: {c['spent']} / {c['limit'] or 'no limit'}")
    lines.append("Last 6 months (income, expenses): " + "; ".join(
        f"{t['label']}: {t['income']}, {t['expenses']}" for t in trend(uid, summary["year"], summary["month"])))
    return "\n".join(lines)


def _basis_income(summary, uid):
    if summary["income"]:
        return summary["income"]
    past = [t["income"] for t in trend(uid, summary["year"], summary["month"]) if t["income"]]
    return sum(past) / len(past) if past else 0


# ---------- Budget generation ----------
def generate_budget(user, summary):
    """Returns (limits {category_name: amount}, note, source)."""
    income = _basis_income(summary, user.id)
    if income <= 0:
        return {}, "Add income first so a budget can be generated.", "rule"
    names = [c["name"] for c in summary["categories"]]
    target_save = income * user.savings_goal_pct / 100
    prompt = (f"You are a personal finance advisor.\n{_context(user, summary, user.id)}\n"
              f"Budget basis income: {income:.0f}. Create a monthly budget using ONLY these categories: {names}. "
              f"Keep the total of limits <= {income - target_save:.0f} (so the user saves at least "
              f"{user.savings_goal_pct}%). If income is irregular, be conservative. "
              'Respond with ONLY JSON: {"limits": {"Category": number}, "note": "2-3 sentence rationale"}')
    raw = _call(prompt)
    if raw:
        try:
            data = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
            limits = {k: float(v) for k, v in data["limits"].items() if k in names and float(v) >= 0}
            total, cap = sum(limits.values()), income - target_save
            if limits and total > cap:  # enforce cap even if the model overshoots
                limits = {k: v * cap / total for k, v in limits.items()}
            if limits:
                return {k: round(v, 2) for k, v in limits.items()}, str(data.get("note", "")), "ai"
        except Exception:
            pass
    return _rule_budget(names, summary, income, target_save)


def _rule_budget(names, summary, income, target_save):
    """50/30/20-style fallback, weighted by past spending."""
    spend_avail = income - target_save
    past = {c["name"]: c["spent"] for c in summary["categories"]}
    needs = [n for n in names if n.lower() in NEEDS]
    wants = [n for n in names if n.lower() not in NEEDS]
    limits = {}
    for group, share in ((needs, 0.625), (wants, 0.375)):  # ~50/30 of the spendable amount
        pool = spend_avail * share if group and (needs and wants) else spend_avail if group else 0
        weights = [past.get(n, 0) or 1 for n in group]
        for n, w in zip(group, weights):
            limits[n] = round(pool * w / sum(weights), 2)
    return limits, ("Rule-based plan (needs ~50%, wants ~30%, savings target kept aside), "
                    "weighted by your past spending."), "rule"


# ---------- Insights ----------
def insight(user, summary, kind):
    """kind: analysis | cost | emergency. Returns (text, source)."""
    tasks = {
        "analysis": "Analyse spending, detect overspending, evaluate financial health and give 4-5 concise, actionable recommendations.",
        "cost": "Suggest 4-5 concrete cost-optimisation ideas focused on the highest or most over-budget categories.",
        "emergency": "Give emergency-fund guidance: target size (3-6 months of expenses; 6+ if income is variable), monthly contribution and a timeline.",
    }
    raw = _call(f"You are a friendly, practical personal finance advisor. Use short bullet points. "
                f"Do not give investment guarantees.\n{_context(user, summary, user.id)}\nTask: {tasks[kind]}")
    return (raw.strip(), "ai") if raw else (_rule_insight(user, summary, kind), "rule")


def _rule_insight(user, s, kind):
    cur, pts = user.currency, []
    if kind == "emergency":
        monthly = s["expenses"] or 0
        vals = [t["income"] for t in trend(user.id, s["year"], s["month"]) if t["income"]]
        variable = len(vals) > 1 and (max(vals) - min(vals)) > 0.3 * max(vals)
        months = 6 if variable else 3
        target = monthly * months
        pts.append(f"• Aim for {months} months of expenses: about {cur}{target:,.0f}"
                   f"{' (income looks variable, so a bigger cushion helps)' if variable else ''}.")
        if s["savings"] > 0 and target:
            pts.append(f"• Saving {cur}{s['savings']:,.0f}/month would get you there in ~{target / s['savings']:.0f} months.")
        else:
            pts.append("• Free up cash first by trimming the top discretionary categories.")
        return "\n".join(pts)
    if s["income"] == 0:
        return "• Log your income and expenses for this month to get personalised insights."
    if s["overspent"]:
        for c in s["overspent"]:
            pts.append(f"• {c['name']} is over budget by {cur}{c['spent'] - c['limit']:,.0f}. Set a weekly cap for it.")
    top = sorted(s["categories"], key=lambda c: -c["spent"])[:2]
    for c in top:
        if c["spent"]:
            pts.append(f"• {c['name']} is a top spend ({cur}{c['spent']:,.0f}); review it for savings.")
    if s["savings_rate"] < user.savings_goal_pct:
        gap = s["income"] * user.savings_goal_pct / 100 - s["savings"]
        pts.append(f"• You're {cur}{max(gap, 0):,.0f} short of your {user.savings_goal_pct:.0f}% savings goal.")
    else:
        pts.append("• You met your savings goal. Consider moving the surplus to an emergency fund.")
    return "\n".join(pts)
