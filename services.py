"""Financial analytics: summaries, trends, health score."""
from calendar import monthrange
from datetime import date
from sqlalchemy import func
from models import db, Income, Expense, Category, BudgetPlan


def month_range(y, m):
    return date(y, m, 1), date(y, m, monthrange(y, m)[1])


def _sum(model, uid, s, e):
    return float(db.session.query(func.coalesce(func.sum(model.amount), 0))
                 .filter(model.user_id == uid, model.date.between(s, e)).scalar())


def month_summary(uid, y, m, savings_goal_pct=20.0):
    s, e = month_range(y, m)
    income, expenses = _sum(Income, uid, s, e), _sum(Expense, uid, s, e)
    spent = dict(db.session.query(Expense.category_id, func.sum(Expense.amount))
                 .filter(Expense.user_id == uid, Expense.date.between(s, e))
                 .group_by(Expense.category_id).all())
    limits = {b.category_id: b.limit_amount for b in
              BudgetPlan.query.filter_by(user_id=uid, year=y, month=m)}
    cats = []
    for c in Category.query.filter_by(user_id=uid).order_by(Category.name):
        sp, lim = round(float(spent.get(c.id, 0) or 0), 2), limits.get(c.id)
        cats.append(dict(id=c.id, name=c.name, spent=sp, limit=lim,
                         over=bool(lim and sp > lim),
                         pct=round(sp / lim * 100) if lim else None))
    savings = income - expenses
    rate = savings / income if income else 0.0
    budgeted = [c for c in cats if c["limit"]]
    over_n = sum(c["over"] for c in budgeted)
    score = 0
    if income:
        score = 50 * min(max(rate, 0) / (savings_goal_pct / 100 or 0.2), 1)
        score += 30 * (1 - over_n / len(budgeted)) if budgeted else 15
        score += 20 if expenses <= income else 0
    return dict(year=y, month=m, income=round(income, 2), expenses=round(expenses, 2),
                savings=round(savings, 2), savings_rate=round(rate * 100, 1),
                categories=cats, overspent=[c for c in cats if c["over"]],
                health_score=int(round(score)), has_budget=bool(budgeted))


def trend(uid, y, m, n=6):
    """Income/expense/savings for the last n months (oldest first)."""
    out = []
    for i in range(n - 1, -1, -1):
        yy, mm = y, m - i
        while mm <= 0:
            mm += 12
            yy -= 1
        s, e = month_range(yy, mm)
        inc, exp = _sum(Income, uid, s, e), _sum(Expense, uid, s, e)
        out.append(dict(label=f"{yy}-{mm:02d}", income=round(inc, 2),
                        expenses=round(exp, 2), savings=round(inc - exp, 2)))
    return out


def health_label(score):
    return "Excellent" if score >= 80 else "Good" if score >= 60 else "Fair" if score >= 40 else "Needs attention"
