from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

DEFAULT_CATEGORIES = ["Rent", "Groceries", "Food", "Transport", "Utilities",
                      "Entertainment", "Education", "Healthcare", "Other"]


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(100), default="")
    currency = db.Column(db.String(5), default="₹")
    savings_goal_pct = db.Column(db.Float, default=20.0)  # target % of income to save
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    name = db.Column(db.String(50), nullable=False)
    __table_args__ = (db.UniqueConstraint("user_id", "name"),)


class Income(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    source = db.Column(db.String(100), nullable=False)  # employer / client
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, default=date.today, nullable=False, index=True)
    note = db.Column(db.String(200), default="")


class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, default=date.today, nullable=False, index=True)
    description = db.Column(db.String(200), default="")
    category = db.relationship("Category")


class BudgetPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    limit_amount = db.Column(db.Float, nullable=False)
    source = db.Column(db.String(10), default="manual")  # manual | ai | rule
    __table_args__ = (db.UniqueConstraint("user_id", "category_id", "year", "month"),)


class SavingsGoal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    target_amount = db.Column(db.Float, nullable=False)
    deadline = db.Column(db.Date, nullable=True)
    entries = db.relationship("SavingsEntry", backref="goal", cascade="all, delete-orphan")

    @property
    def saved(self):
        return sum(e.amount for e in self.entries)

    @property
    def pct(self):
        return min(100, round(self.saved / self.target_amount * 100, 1)) if self.target_amount else 0


class SavingsEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    goal_id = db.Column(db.Integer, db.ForeignKey("savings_goal.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, default=date.today)


class MonthlyReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    total_income = db.Column(db.Float, default=0)
    total_expenses = db.Column(db.Float, default=0)
    savings = db.Column(db.Float, default=0)
    savings_rate = db.Column(db.Float, default=0)
    health_score = db.Column(db.Integer, default=0)
    summary_text = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("user_id", "year", "month"),)


class AIInsight(db.Model):
    """Stores AI recommendations so the dashboard can display them."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    kind = db.Column(db.String(20), nullable=False)  # analysis | emergency | cost | budget
    content = db.Column(db.Text, nullable=False)
    source = db.Column(db.String(10), default="ai")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
