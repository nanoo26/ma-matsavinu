from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import os

DB_PATH = "expenses.db"
app = Flask(__name__)


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def normalize_date(date_str: str) -> str:
    """
    קולט תאריך בפורמט YYYY-MM-DD מהטופס
    ומחזיר בפורמט DD/MM/YYYY לשמירה בבסיס הנתונים
    """
    if not date_str:
        return ""
    parts = date_str.split("-")
    if len(parts) != 3:
        return date_str
    year, month, day = parts
    return f"{day}/{month}/{year}"


def date_for_input(db_date: str) -> str:
    """
    קולט תאריך בפורמט DD/MM/YYYY מהמסד
    ומחזיר בפורמט YYYY-MM-DD בשביל input type="date"
    """
    if not db_date:
        return ""
    parts = db_date.split("/")
    if len(parts) != 3:
        return db_date
    day, month, year = parts
    return f"{year}-{month}-{day}"


@app.route("/")
def index():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, date, category, amount, payment_method, description
        FROM expenses
        ORDER BY date DESC, id DESC
    """)
    expenses = cur.fetchall()

    cur.execute("SELECT COUNT(*) FROM expenses")
    total_rows = cur.fetchone()[0]

    cur.execute("SELECT SUM(amount) FROM expenses")
    total_amount = cur.fetchone()[0] or 0

    conn.close()

    return render_template(
        "expenses.html",
        expenses=expenses,
        total_rows=total_rows,
        total_amount=total_amount
    )


@app.route("/add", methods=["GET", "POST"])
def add_expense():
    conn = get_db_connection()
    cur = conn.cursor()

    # טעינת רשימות קיימות לבחירה
    cur.execute("SELECT DISTINCT category FROM expenses WHERE category != ''")
    categories = [row["category"] for row in cur.fetchall()]

    cur.execute("SELECT DISTINCT payment_method FROM expenses WHERE payment_method != ''")
    payment_methods = [row["payment_method"] for row in cur.fetchall()]

    if request.method == "POST":
        raw_date = request.form.get("date", "")
        date = normalize_date(raw_date)
        category = request.form.get("category", "").strip()
        amount_raw = request.form.get("amount", "").strip()
        payment_method = request.form.get("payment_method", "").strip()
        description = request.form.get("description", "").strip()

        if not date or not category or not amount_raw or not payment_method or not description:
            conn.close()
            return render_template(
                "add_expense.html",
                error="נא למלא את כל השדות",
                categories=categories,
                payment_methods=payment_methods
            )

        try:
            amount = float(amount_raw.replace(",", ""))
        except ValueError:
            conn.close()
            return render_template(
                "add_expense.html",
                error="סכום לא תקין",
                categories=categories,
                payment_methods=payment_methods
            )

        cur.execute("""
            INSERT INTO expenses (date, category, amount, payment_method, description)
            VALUES (?, ?, ?, ?, ?)
        """, (date, category, amount, payment_method, description))
        conn.commit()
        conn.close()
        return redirect(url_for("index"))

    conn.close()
    return render_template(
        "add_expense.html",
        error=None,
        categories=categories,
        payment_methods=payment_methods
    )


@app.route("/edit/<int:expense_id>", methods=["GET", "POST"])
def edit_expense(expense_id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,))
    expense = cur.fetchone()

    if not expense:
        conn.close()
        return redirect(url_for("index"))

    cur.execute("SELECT DISTINCT category FROM expenses WHERE category != ''")
    categories = [row["category"] for row in cur.fetchall()]

    cur.execute("SELECT DISTINCT payment_method FROM expenses WHERE payment_method != ''")
    payment_methods = [row["payment_method"] for row in cur.fetchall()]

    if request.method == "POST":
        raw_date = request.form.get("date", "")
        date = normalize_date(raw_date)
        category = request.form.get("category", "").strip()
        amount_raw = request.form.get("amount", "").strip()
        payment_method = request.form.get("payment_method", "").strip()
        description = request.form.get("description", "").strip()

        try:
            amount = float(amount_raw.replace(",", ""))
        except ValueError:
            conn.close()
            return render_template(
                "edit_expense.html",
                expense=expense,
                categories=categories,
                payment_methods=payment_methods,
                date_input=raw_date,
                error="סכום לא תקין"
            )

        if not date or not category or not amount_raw or not payment_method or not description:
            conn.close()
            return render_template(
                "edit_expense.html",
                expense=expense,
                categories=categories,
                payment_methods=payment_methods,
                date_input=raw_date,
                error="נא למלא את כל השדות"
            )

        cur.execute("""
            UPDATE expenses
            SET date = ?, category = ?, amount = ?, payment_method = ?, description = ?
            WHERE id = ?
        """, (date, category, amount, payment_method, description, expense_id))
        conn.commit()
        conn.close()
        return redirect(url_for("index"))

    date_input = date_for_input(expense["date"])
    conn.close()
    return render_template(
        "edit_expense.html",
        expense=expense,
        categories=categories,
        payment_methods=payment_methods,
        date_input=date_input,
        error=None
    )


@app.route("/delete/<int:expense_id>")
def delete_expense(expense_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
