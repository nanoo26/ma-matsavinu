from flask import Flask, render_template, request, redirect, url_for, Response

import sqlite3
import os
import io
import csv

DB_PATH = "expenses.db"
app = Flask(__name__)


def init_db():
    """
    יוצר את טבלת ההוצאות אם היא לא קיימת
    שם העמודות מותאם למה שהקוד משתמש בו: description ולא notes
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            payment_method TEXT NOT NULL,
            description TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# נוודא שהטבלה קיימת כבר בזמן עליית האפליקציה (גם לוקאלי וגם ב־Render)
init_db()


# קטגוריות ברירת מחדל (יתווספו למה שיש במסד)
DEFAULT_CATEGORIES = [
    "בילויים",
    "בית",
    "ילדים",
    "בריאות",
    "רכב",
    "חוגים",
    "קניות",
    "שונות",
    "טבק",
]

# אמצעי תשלום קבועים
PAYMENT_METHODS = [
    "מקס שלום",
    "מקס חגית",
    "כאל ויזה",
    "לאומי שלום",
    'עו"ש',
]


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


def get_available_months(conn):
    """
    מחזיר רשימת חודשים קיימים במסד הנתונים, מהחדש לישן.
    כל פריט הוא dict עם:
    key = YYYY-MM
    label = MM/YYYY
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT
               SUBSTR(date, 7, 4) AS year,
               SUBSTR(date, 4, 2) AS month
        FROM expenses
        WHERE date IS NOT NULL AND date != ''
        ORDER BY year DESC, month DESC
    """)
    rows = cur.fetchall()
    months = []
    for row in rows:
        year = row["year"]
        month = row["month"]
        key = f"{year}-{month}"
        label = f"{month}/{year}"
        months.append({"key": key, "label": label})
    return months


def parse_year_month(selected_month):
    """
    מקבל מחרוזת בפורמט YYYY-MM ומחזיר (year, month)
    אם הפורמט לא תקין מחזיר (None, None)
    """
    if not selected_month or "-" not in selected_month:
        return None, None
    parts = selected_month.split("-")
    if len(parts) != 2:
        return None, None
    year, month = parts
    if len(year) != 4 or len(month) != 2:
        return None, None
    return year, month


# ראוט שורש - תמיד מפנה למסך הרשימה
@app.route("/")
def root():
    return redirect(url_for("index"))


# המסך הראשי האמיתי - רשימת הוצאות
@app.route("/expenses")
def index():
    conn = get_db_connection()

    # רשימת חודשים זמינים
    months = get_available_months(conn)

    # קביעת חודש נבחר
    selected_month = request.args.get("month")
    valid_keys = {m["key"] for m in months}
    if not months:
        selected_month = None
    else:
        if not selected_month or selected_month not in valid_keys:
            selected_month = months[0]["key"]

    year = month = None
    if selected_month:
        year, month = parse_year_month(selected_month)

    cur = conn.cursor()

    if year and month:
        # הוצאות לחודש הנבחר בלבד
        cur.execute("""
            SELECT id, date, category, amount, payment_method, description
            FROM expenses
            WHERE SUBSTR(date, 7, 4) = ? AND SUBSTR(date, 4, 2) = ?
            ORDER BY date DESC, id DESC
        """, (year, month))
        expenses = cur.fetchall()

        cur.execute("""
            SELECT COUNT(*)
            FROM expenses
            WHERE SUBSTR(date, 7, 4) = ? AND SUBSTR(date, 4, 2) = ?
        """, (year, month))
        total_rows = cur.fetchone()[0]

        cur.execute("""
            SELECT SUM(amount)
            FROM expenses
            WHERE SUBSTR(date, 7, 4) = ? AND SUBSTR(date, 4, 2) = ?
        """, (year, month))
        total_amount = cur.fetchone()[0] or 0
    else:
        # ברירת מחדל אם אין נתונים
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
        total_amount=total_amount,
        months=months,
        selected_month=selected_month
    )


@app.route("/add_expenses", methods=["GET", "POST"])
def add_expense():
    conn = get_db_connection()
    cur = conn.cursor()

    # קטגוריות: מתוך המסד + ברירות מחדל
    cur.execute("SELECT DISTINCT category FROM expenses WHERE category != ''")
    db_categories = [row["category"] for row in cur.fetchall()]
    categories = sorted(set(db_categories + DEFAULT_CATEGORIES))

    # אמצעי תשלום קבועים
    payment_methods = PAYMENT_METHODS

    if request.method == "POST":
        raw_date = request.form.get("date", "")
        date = normalize_date(raw_date)
        category = request.form.get("category", "").strip()
        amount_raw = request.form.get("amount", "").strip()
        payment_method = request.form.get("payment_method", "").strip()
        description = request.form.get("description", "").strip()

        # בדיקה שכל השדות מולאו
        if not date or not category or not amount_raw or not payment_method or not description:
            conn.close()
            return render_template(
                "add_expense.html",
                error="נא למלא את כל השדות",
                categories=categories,
                payment_methods=payment_methods
            )

        # בדיקת אמצעי תשלום מתוך הרשימה בלבד
        if payment_method not in PAYMENT_METHODS:
            conn.close()
            return render_template(
                "add_expense.html",
                error="יש לבחור אמצעי תשלום מתוך הרשימה",
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

    # קטגוריות: מתוך המסד + ברירות מחדל
    cur.execute("SELECT DISTINCT category FROM expenses WHERE category != ''")
    db_categories = [row["category"] for row in cur.fetchall()]
    categories = sorted(set(db_categories + DEFAULT_CATEGORIES))

    # אמצעי תשלום קבועים
    payment_methods = PAYMENT_METHODS

    if request.method == "POST":
        raw_date = request.form.get("date", "")
        date = normalize_date(raw_date)
        category = request.form.get("category", "").strip()
        amount_raw = request.form.get("amount", "").strip()
        payment_method = request.form.get("payment_method", "").strip()
        description = request.form.get("description", "").strip()

        # בדיקה שכל השדות מולאו
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

        # בדיקת אמצעי תשלום מתוך הרשימה בלבד
        if payment_method not in PAYMENT_METHODS:
            conn.close()
            return render_template(
                "edit_expense.html",
                expense=expense,
                categories=categories,
                payment_methods=payment_methods,
                date_input=raw_date,
                error="יש לבחור אמצעי תשלום מתוך הרשימה"
            )

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


@app.route("/reports")
def reports():
    conn = get_db_connection()

    # רשימת חודשים זמינים
    months = get_available_months(conn)

    # קביעת חודש נבחר
    selected_month = request.args.get("month")
    valid_keys = {m["key"] for m in months}
    if not months:
        selected_month = None
    else:
        if not selected_month or selected_month not in valid_keys:
            selected_month = months[0]["key"]

    year = month = None
    if selected_month:
        year, month = parse_year_month(selected_month)

    cur = conn.cursor()

    # סיכום לפי חודש לחודש הנבחר
    if year and month:
        cur.execute("""
            SELECT 
                SUBSTR(date, 4, 2) AS month,
                SUBSTR(date, 7, 4) AS year,
                SUM(amount) AS total
            FROM expenses
            WHERE SUBSTR(date, 7, 4) = ? AND SUBSTR(date, 4, 2) = ?
            GROUP BY year, month
        """, (year, month))
        monthly_summary = cur.fetchall()

        # סיכום לפי קטגוריה לחודש הנבחר
        cur.execute("""
            SELECT category, SUM(amount) AS total
            FROM expenses
            WHERE SUBSTR(date, 7, 4) = ? AND SUBSTR(date, 4, 2) = ?
            GROUP BY category
            ORDER BY total DESC
        """, (year, month))
        category_summary = cur.fetchall()
    else:
        monthly_summary = []
        category_summary = []

    conn.close()

    return render_template(
        "reports.html",
        monthly_summary=monthly_summary,
        category_summary=category_summary,
        months=months,
        selected_month=selected_month
    )

@app.route("/export")
def export_csv():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT date, category, amount, payment_method, description
        FROM expenses
        ORDER BY date ASC, id ASC
    """)
    rows = cur.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["date", "category", "amount", "payment_method", "description"])
    for row in rows:
        writer.writerow([
            row["date"],
            row["category"],
            row["amount"],
            row["payment_method"],
            row["description"],
        ])

    csv_data = output.getvalue()
    output.close()

    return Response(
        csv_data,
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=expenses_export.csv"
        }
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
