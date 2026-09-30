# 💰 Personal Finance Advisor Bot

AI-powered budgeting, expense tracking and savings planning built with **Flask, SQLAlchemy, SQLite/PostgreSQL, Jinja2, JavaScript (Chart.js) and Gemini AI**, deployable publicly via **Ngrok**.

## Features (mapped to the project brief)
| Brief section | Where |
|---|---|
| 1. Environment & AI config | `config.py`, `.env`, `requirements.txt`, `ai_service.py` |
| 2. Auth & profile | `/register /login /logout /profile`, Flask-Login, hashed passwords, CSRF, protected routes |
| 3. Tracking & budgets | `/income /expenses /categories /budget /savings`, `services.py` |
| 4. AI engine | `ai_service.py`: budget generation, spending analysis, cost optimisation, emergency fund, health score, overspending detection (Gemini + rule-based fallback) |
| 5. Dashboard & reports | `/dashboard` (Chart.js), `/reports` (monthly summary + next-month goal, printable) |
| 6. Database | `models.py`: User, Category, Income, Expense, BudgetPlan, SavingsGoal, SavingsEntry, MonthlyReport, AIInsight |
| 7. Frontend-backend | Jinja2 templates, JSON APIs (`/api/dashboard-data`, `/api/insights`), validation + error pages |
| 8. Ngrok | `run_ngrok.py` |
| 9. Testing | `tests/test_app.py` (pytest) |

Scenarios covered: salaried user (monthly summary), student (category limits + cost tips), freelancer (multi-source income, 6-month trend, larger emergency-fund target when income varies), household (shared categories, consolidated report).

## Setup
```bash
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # then edit values
python app.py                                          # http://localhost:5000
```
Get a Gemini key at https://aistudio.google.com/apikey. Without a key the app still works using rule-based advice. For PostgreSQL set `DATABASE_URL=postgresql://user:pass@host/db` and `pip install psycopg2-binary`.

## Public deployment with Ngrok
1. Create a free account at ngrok.com and copy your authtoken into `.env` (`NGROK_AUTHTOKEN`).
2. Run `python run_ngrok.py` and open the printed `https://….ngrok-free.app` URL.

## Tests
```bash
pytest -q
```
Covers auth, validation, income/expense flows, budget generation, AI fallback, reports, savings and per-user data isolation.

## Notes
- Amounts use `Float` for simplicity; switch to `Numeric` for production accounting.
- Set a strong `SECRET_KEY`. Never commit `.env`.
- Ideas to extend: predictive spending (time-series), recurring transactions, CSV export, investment suggestions.
