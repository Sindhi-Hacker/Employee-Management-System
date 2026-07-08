import os
import math
import uuid
from datetime import datetime, date, timedelta
from collections import defaultdict, Counter

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__)
CORS(app)

DEFAULT_AVATAR = "https://api.dicebear.com/7.x/initials/svg?backgroundColor=6D28D9"

# =========================================================
# Helpers
# =========================================================

def db():
    if supabase is None:
        raise RuntimeError("Supabase client is not configured. Set SUPABASE_URL and SUPABASE_KEY.")
    return supabase


def ok(data, status=200):
    return jsonify({"success": True, "data": data}), status


def err(message, status=400):
    return jsonify({"success": False, "error": message}), status


def clean_payload(payload, allowed_fields):
    """Only keep keys that are present in payload AND allowed - supports partial updates."""
    return {k: v for k, v in payload.items() if k in allowed_fields}


# =========================================================
# Health check
# =========================================================
@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"}), 200


# =========================================================
# Frontend
# =========================================================
@app.route("/")
def index():
    return render_template("index.html")


# =========================================================
# Auth (mock)
# =========================================================
@app.route("/api/login", methods=["POST"])
def login():
    payload = request.get_json(force=True) or {}
    email = payload.get("email", "").strip().lower()
    password = payload.get("password", "")

    if email == "admin@javagoat.hr" and password == "password123":
        token = "mock-token-" + uuid.uuid4().hex
        return ok({
            "token": token,
            "user": {
                "name": "Admin User",
                "email": "admin@javagoat.hr",
                "role": "Administrator",
                "avatar": "https://api.dicebear.com/7.x/initials/svg?seed=Admin&backgroundColor=6D28D9"
            }
        })
    return err("Invalid email or password", 401)


# =========================================================
# DEPARTMENTS
# =========================================================
DEPARTMENT_FIELDS = {"name", "description"}

@app.route("/api/departments", methods=["GET"])
def get_departments():
    res = db().table("departments").select("*").order("created_at", desc=True).execute()
    return ok(res.data)


@app.route("/api/departments", methods=["POST"])
def create_department():
    payload = clean_payload(request.get_json(force=True) or {}, DEPARTMENT_FIELDS)
    res = db().table("departments").insert(payload).execute()
    return ok(res.data, 201)


@app.route("/api/departments/<dept_id>", methods=["PUT"])
def update_department(dept_id):
    payload = clean_payload(request.get_json(force=True) or {}, DEPARTMENT_FIELDS)
    res = db().table("departments").update(payload).eq("id", dept_id).execute()
    return ok(res.data)


@app.route("/api/departments/<dept_id>", methods=["DELETE"])
def delete_department(dept_id):
    db().table("departments").delete().eq("id", dept_id).execute()
    return ok({"id": dept_id})


# =========================================================
# POSITIONS
# =========================================================
POSITION_FIELDS = {"title", "department_id", "min_salary", "max_salary"}

@app.route("/api/positions", methods=["GET"])
def get_positions():
    positions_res = db().table("positions").select("*").order("created_at", desc=True).execute()
    positions = positions_res.data or []

    employees_res = db().table("employees").select("id,first_name,last_name,profile_pic,position_id").execute()
    employees = employees_res.data or []

    dept_res = db().table("departments").select("id,name").execute()
    dept_map = {d["id"]: d["name"] for d in (dept_res.data or [])}

    emp_by_position = defaultdict(list)
    for e in employees:
        if e.get("position_id"):
            emp_by_position[e["position_id"]].append({
                "id": e["id"],
                "name": f'{e["first_name"]} {e["last_name"]}',
                "profile_pic": e.get("profile_pic") or DEFAULT_AVATAR
            })

    for p in positions:
        p["department_name"] = dept_map.get(p.get("department_id"), "Unassigned")
        p["employees"] = emp_by_position.get(p["id"], [])

    return ok(positions)


@app.route("/api/positions", methods=["POST"])
def create_position():
    payload = clean_payload(request.get_json(force=True) or {}, POSITION_FIELDS)
    res = db().table("positions").insert(payload).execute()
    return ok(res.data, 201)


@app.route("/api/positions/<pos_id>", methods=["PUT"])
def update_position(pos_id):
    payload = clean_payload(request.get_json(force=True) or {}, POSITION_FIELDS)
    res = db().table("positions").update(payload).eq("id", pos_id).execute()
    return ok(res.data)


@app.route("/api/positions/<pos_id>", methods=["DELETE"])
def delete_position(pos_id):
    db().table("positions").delete().eq("id", pos_id).execute()
    return ok({"id": pos_id})


@app.route("/api/positions/<pos_id>/assign", methods=["POST"])
def assign_employee_to_position(pos_id):
    payload = request.get_json(force=True) or {}
    employee_id = payload.get("employee_id")
    if not employee_id:
        return err("employee_id is required")
    res = db().table("employees").update({"position_id": pos_id}).eq("id", employee_id).execute()
    return ok(res.data)


# =========================================================
# EMPLOYEES
# =========================================================
EMPLOYEE_FIELDS = {
    "first_name", "last_name", "email", "phone", "profile_pic",
    "department_id", "position_id", "salary", "status", "hire_date", "address"
}

@app.route("/api/employees", methods=["GET"])
def get_employees():
    search = request.args.get("search", "").strip().lower()
    department_id = request.args.get("department_id")
    status = request.args.get("status")

    query = db().table("employees").select("*").order("created_at", desc=True)
    res = query.execute()
    employees = res.data or []

    dept_res = db().table("departments").select("id,name").execute()
    dept_map = {d["id"]: d["name"] for d in (dept_res.data or [])}
    pos_res = db().table("positions").select("id,title").execute()
    pos_map = {p["id"]: p["title"] for p in (pos_res.data or [])}

    for e in employees:
        e["department_name"] = dept_map.get(e.get("department_id"), "Unassigned")
        e["position_title"] = pos_map.get(e.get("position_id"), "Unassigned")
        if not e.get("profile_pic"):
            e["profile_pic"] = DEFAULT_AVATAR

    if search:
        employees = [
            e for e in employees
            if search in f'{e["first_name"]} {e["last_name"]} {e["email"]}'.lower()
        ]
    if department_id:
        employees = [e for e in employees if e.get("department_id") == department_id]
    if status:
        employees = [e for e in employees if e.get("status") == status]

    return ok(employees)


@app.route("/api/employees/<emp_id>", methods=["GET"])
def get_employee(emp_id):
    res = db().table("employees").select("*").eq("id", emp_id).single().execute()
    return ok(res.data)


@app.route("/api/employees", methods=["POST"])
def create_employee():
    payload = clean_payload(request.get_json(force=True) or {}, EMPLOYEE_FIELDS)
    if not payload.get("profile_pic"):
        payload["profile_pic"] = DEFAULT_AVATAR
    res = db().table("employees").insert(payload).execute()
    return ok(res.data, 201)


@app.route("/api/employees/<emp_id>", methods=["PUT"])
def update_employee(emp_id):
    # Partial update: only fields present in the JSON body are touched.
    payload = clean_payload(request.get_json(force=True) or {}, EMPLOYEE_FIELDS)
    payload["updated_at"] = datetime.utcnow().isoformat()
    res = db().table("employees").update(payload).eq("id", emp_id).execute()
    return ok(res.data)


@app.route("/api/employees/<emp_id>", methods=["DELETE"])
def delete_employee(emp_id):
    db().table("employees").delete().eq("id", emp_id).execute()
    return ok({"id": emp_id})


# =========================================================
# ATTENDANCE
# =========================================================
ATTENDANCE_FIELDS = {"employee_id", "date", "check_in", "check_out", "status", "notes"}

@app.route("/api/attendance", methods=["GET"])
def get_attendance():
    res = db().table("attendance").select("*").order("date", desc=True).execute()
    records = res.data or []

    emp_res = db().table("employees").select("id,first_name,last_name,profile_pic").execute()
    emp_map = {e["id"]: e for e in (emp_res.data or [])}

    for r in records:
        emp = emp_map.get(r.get("employee_id"))
        r["employee_name"] = f'{emp["first_name"]} {emp["last_name"]}' if emp else "Unknown"
        r["employee_pic"] = (emp.get("profile_pic") if emp else None) or DEFAULT_AVATAR

    status = request.args.get("status")
    search = request.args.get("search", "").strip().lower()
    if status:
        records = [r for r in records if r.get("status") == status]
    if search:
        records = [r for r in records if search in r["employee_name"].lower()]

    return ok(records)


@app.route("/api/attendance", methods=["POST"])
def create_attendance():
    payload = clean_payload(request.get_json(force=True) or {}, ATTENDANCE_FIELDS)
    res = db().table("attendance").insert(payload).execute()
    return ok(res.data, 201)


@app.route("/api/attendance/<att_id>", methods=["PUT"])
def update_attendance(att_id):
    payload = clean_payload(request.get_json(force=True) or {}, ATTENDANCE_FIELDS)
    res = db().table("attendance").update(payload).eq("id", att_id).execute()
    return ok(res.data)


@app.route("/api/attendance/<att_id>", methods=["DELETE"])
def delete_attendance(att_id):
    db().table("attendance").delete().eq("id", att_id).execute()
    return ok({"id": att_id})


# =========================================================
# LEAVES
# =========================================================
LEAVE_FIELDS = {"employee_id", "leave_type", "start_date", "end_date", "reason", "status"}

@app.route("/api/leaves", methods=["GET"])
def get_leaves():
    res = db().table("leaves").select("*").order("created_at", desc=True).execute()
    records = res.data or []

    emp_res = db().table("employees").select("id,first_name,last_name,profile_pic").execute()
    emp_map = {e["id"]: e for e in (emp_res.data or [])}

    for r in records:
        emp = emp_map.get(r.get("employee_id"))
        r["employee_name"] = f'{emp["first_name"]} {emp["last_name"]}' if emp else "Unknown"
        r["employee_pic"] = (emp.get("profile_pic") if emp else None) or DEFAULT_AVATAR

    status = request.args.get("status")
    search = request.args.get("search", "").strip().lower()
    if status:
        records = [r for r in records if r.get("status") == status]
    if search:
        records = [r for r in records if search in r["employee_name"].lower()]

    return ok(records)


@app.route("/api/leaves", methods=["POST"])
def create_leave():
    payload = clean_payload(request.get_json(force=True) or {}, LEAVE_FIELDS)
    res = db().table("leaves").insert(payload).execute()
    return ok(res.data, 201)


@app.route("/api/leaves/<leave_id>", methods=["PUT"])
def update_leave(leave_id):
    payload = clean_payload(request.get_json(force=True) or {}, LEAVE_FIELDS)
    res = db().table("leaves").update(payload).eq("id", leave_id).execute()
    return ok(res.data)


@app.route("/api/leaves/<leave_id>", methods=["DELETE"])
def delete_leave(leave_id):
    db().table("leaves").delete().eq("id", leave_id).execute()
    return ok({"id": leave_id})


# =========================================================
# PAYROLL
# =========================================================
PAYROLL_FIELDS = {
    "employee_id", "pay_period", "basic_salary", "bonus",
    "deductions", "net_pay", "status", "pay_date"
}

@app.route("/api/payroll", methods=["GET"])
def get_payroll():
    res = db().table("payroll").select("*").order("created_at", desc=True).execute()
    records = res.data or []

    emp_res = db().table("employees").select("id,first_name,last_name,profile_pic").execute()
    emp_map = {e["id"]: e for e in (emp_res.data or [])}

    for r in records:
        emp = emp_map.get(r.get("employee_id"))
        r["employee_name"] = f'{emp["first_name"]} {emp["last_name"]}' if emp else "Unknown"
        r["employee_pic"] = (emp.get("profile_pic") if emp else None) or DEFAULT_AVATAR

    status = request.args.get("status")
    search = request.args.get("search", "").strip().lower()
    if status:
        records = [r for r in records if r.get("status") == status]
    if search:
        records = [r for r in records if search in r["employee_name"].lower()]

    return ok(records)


@app.route("/api/payroll", methods=["POST"])
def create_payroll():
    payload = clean_payload(request.get_json(force=True) or {}, PAYROLL_FIELDS)
    basic = float(payload.get("basic_salary", 0) or 0)
    bonus = float(payload.get("bonus", 0) or 0)
    deductions = float(payload.get("deductions", 0) or 0)
    payload["net_pay"] = basic + bonus - deductions
    res = db().table("payroll").insert(payload).execute()
    return ok(res.data, 201)


@app.route("/api/payroll/<pay_id>", methods=["PUT"])
def update_payroll(pay_id):
    payload = clean_payload(request.get_json(force=True) or {}, PAYROLL_FIELDS)
    if any(k in payload for k in ("basic_salary", "bonus", "deductions")):
        existing = db().table("payroll").select("*").eq("id", pay_id).single().execute().data or {}
        basic = float(payload.get("basic_salary", existing.get("basic_salary", 0)) or 0)
        bonus = float(payload.get("bonus", existing.get("bonus", 0)) or 0)
        deductions = float(payload.get("deductions", existing.get("deductions", 0)) or 0)
        payload["net_pay"] = basic + bonus - deductions
    res = db().table("payroll").update(payload).eq("id", pay_id).execute()
    return ok(res.data)


@app.route("/api/payroll/<pay_id>", methods=["DELETE"])
def delete_payroll(pay_id):
    db().table("payroll").delete().eq("id", pay_id).execute()
    return ok({"id": pay_id})


# =========================================================
# DASHBOARD STATS
# =========================================================
@app.route("/api/dashboard/stats", methods=["GET"])
def dashboard_stats():
    employees = db().table("employees").select("*").execute().data or []
    departments = db().table("departments").select("*").execute().data or []
    positions = db().table("positions").select("*").execute().data or []
    attendance = db().table("attendance").select("*").execute().data or []
    leaves = db().table("leaves").select("*").execute().data or []
    payroll = db().table("payroll").select("*").execute().data or []

    dept_map = {d["id"]: d["name"] for d in departments}
    pos_map = {p["id"]: p["title"] for p in positions}

    total_employees = len(employees)
    active_employees = len([e for e in employees if e.get("status") == "active"])
    total_departments = len(departments)
    pending_leaves = len([l for l in leaves if l.get("status") == "pending"])
    total_payroll_paid = sum(float(p.get("net_pay") or 0) for p in payroll if p.get("status") == "paid")

    cards = [
        {"label": "Total Employees", "value": total_employees, "icon": "users", "gradient": "blue"},
        {"label": "Active Employees", "value": active_employees, "icon": "user-check", "gradient": "green"},
        {"label": "Departments", "value": total_departments, "icon": "building-2", "gradient": "orange"},
        {"label": "Pending Leaves", "value": pending_leaves, "icon": "calendar-clock", "gradient": "pink"},
        {"label": "Payroll Paid (Total)", "value": round(total_payroll_paid, 2), "icon": "wallet", "gradient": "cyan"},
    ]

    # Hiring trend (last 6 months, by hire_date)
    months = []
    today = date.today()
    for i in range(5, -1, -1):
        m = (today.replace(day=1) - timedelta(days=1)) if i == 0 else today
        year = today.year
        month = today.month - i
        while month <= 0:
            month += 12
            year -= 1
        months.append((year, month))

    month_labels = [datetime(y, m, 1).strftime("%b %Y") for (y, m) in months]
    hiring_counts = [0] * len(months)
    for e in employees:
        hd = e.get("hire_date")
        if not hd:
            continue
        try:
            hd_date = datetime.strptime(hd[:10], "%Y-%m-%d")
        except Exception:
            continue
        for idx, (y, m) in enumerate(months):
            if hd_date.year == y and hd_date.month == m:
                hiring_counts[idx] += 1

    # Department mix
    dept_counts = Counter(dept_map.get(e.get("department_id"), "Unassigned") for e in employees)

    # Status breakdown
    status_counts = Counter(e.get("status", "unknown") for e in employees)

    # Attendance trend (last 7 days)
    attendance_days = []
    attendance_present_counts = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        attendance_days.append(d.strftime("%a"))
        count = len([a for a in attendance if a.get("date") == d.isoformat() and a.get("status") == "present"])
        attendance_present_counts.append(count)

    # Employees by position (for list panel)
    employees_by_position = []
    for e in employees[:50]:
        employees_by_position.append({
            "id": e["id"],
            "name": f'{e["first_name"]} {e["last_name"]}',
            "profile_pic": e.get("profile_pic") or DEFAULT_AVATAR,
            "position_title": pos_map.get(e.get("position_id"), "Unassigned")
        })

    return ok({
        "cards": cards,
        "hiring_trend": {"labels": month_labels, "data": hiring_counts},
        "department_mix": {"labels": list(dept_counts.keys()), "data": list(dept_counts.values())},
        "status_breakdown": {"labels": list(status_counts.keys()), "data": list(status_counts.values())},
        "attendance_trend": {"labels": attendance_days, "data": attendance_present_counts},
        "employees_by_position": employees_by_position
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
