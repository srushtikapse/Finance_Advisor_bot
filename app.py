from datetime import date, datetime
from flask import (Flask, render_template, request, redirect, url_for, flash, jsonify, abort)
from flask_login import (LoginManager, login_user, logout_user, login_required, current_user)
from flask_wtf.csrf import CSRFProtect
from sqlalchemy.exc import IntegrityError

from config import Config
from models import (db, User, Category, Income, Expense, BudgetPlan, SavingsGoal,
                    SavingsEntry, MonthlyReport, AIInsight, DEFAULT_CATEGORIES)
from services import month_summary, month_range, trend, health_label
import ai_service

csrf = CSRFProtect()
login_manager = LoginManager()
login_manager.login_view = "login"


def parse_amount(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise ValueError("Enter a valid amount.")
    if not 0 < x < 1e9:
        raise ValueError("Amount must be greater than 0.")
    return round(x, 2)


def parse_date(v):
    try:
        return datetime.strptime(v, "%Y-%m-%d").date() if v else date.today()
    except ValueError:
        raise ValueError("Enter a valid date.")


def period():
    v = request.values.get("month") or ""
    try:
        d = datetime.strptime(v, "%Y-%m")
        return d.year, d.month
    except ValueError:
        t = date.today()
        return t.year, t.month


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)

    with app.app_context():
        db.create_all()

    @login_manager.user_loader
    def load_user(uid):
        return db.session.get(User, int(uid))

    @app.context_processor
    def inject():
        y, m = period()
        return dict(cur_month=f"{y}-{m:02d}", health_label=health_label)

    # ---------------- Auth ----------------
    @app.route("/")
    def index():
        return redirect(url_for("dashboard" if current_user.is_authenticated else "login"))

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            pw = request.form.get("password", "")
            if "@" not in email or len(pw) < 8:
                flash("Use a valid email and a password of at least 8 characters.", "error")
            elif User.query.filter_by(email=email).first():
                flash("That email is already registered.", "error")
            else:
                u = User(email=email, full_name=request.form.get("full_name", "").strip()[:100])
                u.set_password(pw)
                db.session.add(u)
                db.session.flush()
                db.session.add_all(Category(user_id=u.id, name=n) for n in DEFAULT_CATEGORIES)
                db.session.commit()
                login_user(u)
                return redirect(url_for("dashboard"))
        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            u = User.query.filter_by(email=request.form.get("email", "").strip().lower()).first()
            if u and u.check_password(request.form.get("password", "")):
                login_user(u)
                nxt = request.args.get("next", "")
                return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("dashboard"))
            flash("Invalid email or password.", "error")
        return render_template("login.html")

    @app.route("/logout", methods=["POST"])
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("login"))

    @app.route("/profile", methods=["GET", "POST"])
    @login_required
    def profile():
        if request.method == "POST":
            current_user.full_name = request.form.get("full_name", "").strip()[:100]
            current_user.currency = (request.form.get("currency") or "₹")[:5]
            try:
                pct = float(request.form.get("savings_goal_pct", 20))
                current_user.savings_goal_pct = min(max(pct, 0), 90)
            except ValueError:
                flash("Savings goal must be a number.", "error")
            new_pw = request.form.get("new_password", "")
            if new_pw:
                if len(new_pw) < 8 or not current_user.check_password(request.form.get("old_password", "")):
                    flash("Old password wrong or new password too short.", "error")
                    return redirect(url_for("profile"))
                current_user.set_password(new_pw)
            db.session.commit()
            flash("Profile updated.", "ok")
            return redirect(url_for("profile"))
        return render_template("profile.html")

    # ---------------- Categories ----------------
    @app.route("/categories", methods=["GET", "POST"])
    @login_required
    def categories():
        if request.method == "POST":
            name = request.form.get("name", "").strip()[:50]
            if name:
                try:
                    db.session.add(Category(user_id=current_user.id, name=name))
                    db.session.commit()
                except IntegrityError:
                    db.session.rollback()
                    flash("Category already exists.", "error")
        cats = Category.query.filter_by(user_id=current_user.id).order_by(Category.name).all()
        return render_template("categories.html", cats=cats)

    @app.route("/categories/<int:cid>/delete", methods=["POST"])
    @login_required
    def delete_category(cid):
        c = Category.query.filter_by(id=cid, user_id=current_user.id).first_or_404()
        if Expense.query.filter_by(category_id=cid).first():
            flash("Category has expenses; delete or move them first.", "error")
        else:
            BudgetPlan.query.filter_by(category_id=cid).delete()
            db.session.delete(c)
            db.session.commit()
        return redirect(url_for("categories"))

    # ---------------- Income ----------------
    @app.route("/income", methods=["GET", "POST"])
    @login_required
    def income():
        if request.method == "POST":
            try:
                db.session.add(Income(user_id=current_user.id,
                                      source=request.form.get("source", "").strip()[:100] or "Income",
                                      amount=parse_amount(request.form.get("amount")),
                                      date=parse_date(request.form.get("date")),
                                      note=request.form.get("note", "")[:200]))
                db.session.commit()
                flash("Income recorded.", "ok")
            except ValueError as e:
                flash(str(e), "error")
            return redirect(url_for("income", month=request.form.get("month", "")))
        y, m = period()
        s, e = month_range(y, m)
        rows = (Income.query.filter(Income.user_id == current_user.id, Income.date.between(s, e))
                .order_by(Income.date.desc()).all())
        return render_template("income.html", rows=rows, total=sum(r.amount for r in rows), today=date.today())

    @app.route("/income/<int:rid>/delete", methods=["POST"])
    @login_required
    def delete_income(rid):
        db.session.delete(Income.query.filter_by(id=rid, user_id=current_user.id).first_or_404())
        db.session.commit()
        return redirect(url_for("income"))

    # ---------------- Expenses ----------------
    @app.route("/expenses", methods=["GET", "POST"])
    @login_required
    def expenses():
        cats = Category.query.filter_by(user_id=current_user.id).order_by(Category.name).all()
        if request.method == "POST":
            try:
                cat = Category.query.filter_by(id=request.form.get("category_id", type=int),
                                               user_id=current_user.id).first()
                if not cat:
                    raise ValueError("Choose a category.")
                db.session.add(Expense(user_id=current_user.id, category_id=cat.id,
                                       amount=parse_amount(request.form.get("amount")),
                                       date=parse_date(request.form.get("date")),
                                       description=request.form.get("description", "")[:200]))
                db.session.commit()
                flash("Expense logged.", "ok")
            except ValueError as e:
                flash(str(e), "error")
            return redirect(url_for("expenses"))
        y, m = period()
        s, e = month_range(y, m)
        q = Expense.query.filter(Expense.user_id == current_user.id, Expense.date.between(s, e))
        cid = request.args.get("category_id", type=int)
        if cid:
            q = q.filter_by(category_id=cid)
        rows = q.order_by(Expense.date.desc(), Expense.id.desc()).all()
        return render_template("expenses.html", rows=rows, cats=cats, cid=cid,
                               total=sum(r.amount for r in rows), today=date.today())

    @app.route("/expenses/<int:rid>/delete", methods=["POST"])
    @login_required
    def delete_expense(rid):
        db.session.delete(Expense.query.filter_by(id=rid, user_id=current_user.id).first_or_404())
        db.session.commit()
        return redirect(url_for("expenses"))

    # ---------------- Budget ----------------
    def save_limits(limits_by_id, y, m, source):
        for cid, val in limits_by_id.items():
            bp = BudgetPlan.query.filter_by(user_id=current_user.id, category_id=cid, year=y, month=m).first()
            if val is None or val <= 0:
                if bp:
                    db.session.delete(bp)
                continue
            if bp:
                bp.limit_amount, bp.source = val, source
            else:
                db.session.add(BudgetPlan(user_id=current_user.id, category_id=cid, year=y,
                                          month=m, limit_amount=val, source=source))
        db.session.commit()

    @app.route("/budget")
    @login_required
    def budget():
        y, m = period()
        s = month_summary(current_user.id, y, m, current_user.savings_goal_pct)
        note = (AIInsight.query.filter_by(user_id=current_user.id, year=y, month=m, kind="budget")
                .order_by(AIInsight.id.desc()).first())
        return render_template("budget.html", s=s, note=note,
                               budget_total=sum(c["limit"] or 0 for c in s["categories"]))

    @app.route("/budget/save", methods=["POST"])
    @login_required
    def budget_save():
        y, m = period()
        lim = {}
        for c in Category.query.filter_by(user_id=current_user.id):
            raw = request.form.get(f"limit_{c.id}", "").strip()
            try:
                lim[c.id] = float(raw) if raw else None
            except ValueError:
                flash(f"Invalid limit for {c.name}.", "error")
                return redirect(url_for("budget", month=f"{y}-{m:02d}"))
        save_limits(lim, y, m, "manual")
        flash("Budget saved.", "ok")
        return redirect(url_for("budget", month=f"{y}-{m:02d}"))

    @app.route("/budget/generate", methods=["POST"])
    @login_required
    def budget_generate():
        y, m = period()
        s = month_summary(current_user.id, y, m, current_user.savings_goal_pct)
        limits, note, source = ai_service.generate_budget(current_user, s)
        if not limits:
            flash(note, "error")
        else:
            ids = {c["name"]: c["id"] for c in s["categories"]}
            save_limits({ids[n]: v for n, v in limits.items()}, y, m, source)
            db.session.add(AIInsight(user_id=current_user.id, year=y, month=m, kind="budget",
                                     content=note, source=source))
            db.session.commit()
            flash("Budget generated" + (" by Gemini AI." if source == "ai" else " (rule-based fallback)."), "ok")
        return redirect(url_for("budget", month=f"{y}-{m:02d}"))

    # ---------------- Dashboard ----------------
    @app.route("/dashboard")
    @login_required
    def dashboard():
        y, m = period()
        s = month_summary(current_user.id, y, m, current_user.savings_goal_pct)
        insights = (AIInsight.query.filter_by(user_id=current_user.id, year=y, month=m)
                    .filter(AIInsight.kind != "budget").order_by(AIInsight.id.desc()).limit(3).all())
        goals = SavingsGoal.query.filter_by(user_id=current_user.id).all()
        return render_template("dashboard.html", s=s, insights=insights, goals=goals)

    @app.route("/api/dashboard-data")
    @login_required
    def dashboard_data():
        y, m = period()
        s = month_summary(current_user.id, y, m, current_user.savings_goal_pct)
        return jsonify(summary=s, trend=trend(current_user.id, y, m))

    @app.route("/api/insights", methods=["POST"])
    @login_required
    def api_insights():
        kind = (request.get_json(silent=True) or {}).get("kind", "analysis")
        if kind not in ("analysis", "cost", "emergency"):
            abort(400)
        y, m = period()
        s = month_summary(current_user.id, y, m, current_user.savings_goal_pct)
        text, source = ai_service.insight(current_user, s, kind)
        db.session.add(AIInsight(user_id=current_user.id, year=y, month=m, kind=kind,
                                 content=text, source=source))
        db.session.commit()
        return jsonify(kind=kind, text=text, source=source)

    # ---------------- Savings ----------------
    @app.route("/savings", methods=["GET", "POST"])
    @login_required
    def savings():
        if request.method == "POST":
            try:
                dl = request.form.get("deadline")
                db.session.add(SavingsGoal(user_id=current_user.id,
                                           name=request.form.get("name", "").strip()[:100] or "Goal",
                                           target_amount=parse_amount(request.form.get("target")),
                                           deadline=parse_date(dl) if dl else None))
                db.session.commit()
            except ValueError as e:
                flash(str(e), "error")
            return redirect(url_for("savings"))
        goals = SavingsGoal.query.filter_by(user_id=current_user.id).all()
        return render_template("savings.html", goals=goals)

    @app.route("/savings/<int:gid>/add", methods=["POST"])
    @login_required
    def savings_add(gid):
        g = SavingsGoal.query.filter_by(id=gid, user_id=current_user.id).first_or_404()
        try:
            db.session.add(SavingsEntry(goal_id=g.id, amount=parse_amount(request.form.get("amount"))))
            db.session.commit()
        except ValueError as e:
            flash(str(e), "error")
        return redirect(url_for("savings"))

    @app.route("/savings/<int:gid>/delete", methods=["POST"])
    @login_required
    def savings_delete(gid):
        db.session.delete(SavingsGoal.query.filter_by(id=gid, user_id=current_user.id).first_or_404())
        db.session.commit()
        return redirect(url_for("savings"))

    # ---------------- Reports ----------------
    @app.route("/reports")
    @login_required
    def reports():
        rows = (MonthlyReport.query.filter_by(user_id=current_user.id)
                .order_by(MonthlyReport.year.desc(), MonthlyReport.month.desc()).all())
        return render_template("reports.html", rows=rows)

    @app.route("/reports/generate", methods=["POST"])
    @login_required
    def report_generate():
        y, m = period()
        s = month_summary(current_user.id, y, m, current_user.savings_goal_pct)
        text, _ = ai_service.insight(current_user, s, "analysis")
        # Next month goal
        goal = current_user.savings_goal_pct / 100 * s["income"]
        text += f"\n\nNext month goal: save at least {current_user.currency}{goal:,.0f} ({current_user.savings_goal_pct:.0f}% of income)."
        r = MonthlyReport.query.filter_by(user_id=current_user.id, year=y, month=m).first() or \
            MonthlyReport(user_id=current_user.id, year=y, month=m)
        r.total_income, r.total_expenses, r.savings = s["income"], s["expenses"], s["savings"]
        r.savings_rate, r.health_score, r.summary_text = s["savings_rate"], s["health_score"], text
        r.created_at = datetime.utcnow()
        db.session.add(r)
        db.session.commit()
        return redirect(url_for("report_view", rid=r.id))

    @app.route("/reports/<int:rid>")
    @login_required
    def report_view(rid):
        r = MonthlyReport.query.filter_by(id=rid, user_id=current_user.id).first_or_404()
        s = month_summary(current_user.id, r.year, r.month, current_user.savings_goal_pct)
        return render_template("report.html", r=r, s=s)

    @app.errorhandler(404)
    def nf(e):
        return render_template("error.html", msg="Page not found."), 404

    @app.errorhandler(500)
    def err(e):
        db.session.rollback()
        return render_template("error.html", msg="Something went wrong."), 500

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5000, debug=False)
