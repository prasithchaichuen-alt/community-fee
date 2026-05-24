import csv
import io
import json
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, make_response

app = Flask(__name__)

def get_db_connection():
    conn = sqlite3.connect('community.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

ORDER_LOGIC = "ORDER BY CAST(SUBSTR(house_number, INSTR(house_number, '/') + 1) AS INTEGER)"

@app.route('/')
def index():
    conn = get_db_connection()
    members_data = conn.execute(f'SELECT * FROM members {ORDER_LOGIC}').fetchall()
    recent_payments = conn.execute('''
        SELECT p.*, m.name FROM payments p
        JOIN members m ON p.house_number = m.house_number
        ORDER BY p.id DESC LIMIT 5
    ''').fetchall()
    current_year = datetime.now().year
    paid_summary = conn.execute('''
        SELECT house_number, SUM(amount) as total FROM payments
        WHERE strftime('%Y', payment_date) = ? GROUP BY house_number
    ''', (str(current_year),)).fetchall()
    conn.close()

    members_dict = {m['house_number']: m['name'] for m in members_data}
    paid_dict = {p['house_number']: p['total'] for p in paid_summary}
    status_dict = {m['house_number']: m['status'] for m in members_data}

    return render_template(
        'index.html',
        members=members_data,
        members_json=json.dumps(members_dict),
        paid_json=json.dumps(paid_dict),
        status_json=json.dumps(status_dict),
        recent_payments=recent_payments,
        today=datetime.now().strftime('%Y-%m-%d')
    )

@app.route('/history')
def history():
    conn = get_db_connection()
    all_payments = conn.execute('''
        SELECT p.*, m.name FROM payments p
        JOIN members m ON p.house_number = m.house_number
        ORDER BY p.payment_date DESC, p.id DESC
    ''').fetchall()
    conn.close()
    return render_template('history.html', payments=all_payments)

@app.route('/admin')
def admin():
    conn = get_db_connection()
    current_year = str(datetime.now().year)
    today_date = datetime.now().strftime('%Y-%m-%d')

    page = int(request.args.get('page', 1))
    per_page = 50
    offset = (page - 1) * per_page

    # 1. ดึงยอดแยกประเภท (สด/โอน)
    stats = conn.execute('''
        SELECT
            SUM(amount) as total_money,
            SUM(CASE WHEN payment_type = 'สด' THEN amount ELSE 0 END) as cash_total,
            SUM(CASE WHEN payment_type = 'โอน' THEN amount ELSE 0 END) as transfer_total,
            COUNT(DISTINCT house_number) as house_count
        FROM payments
        WHERE strftime('%Y', payment_date) = ?
    ''', (current_year,)).fetchone()

    # 2. ดึงรายชื่อสมาชิกแบบแบ่งหน้า
    members_all = conn.execute(
        f'SELECT * FROM members {ORDER_LOGIC} LIMIT ? OFFSET ?',
        (per_page, offset)
    ).fetchall()

    total_members = conn.execute('SELECT COUNT(*) FROM members').fetchone()[0]
    total_pages = (total_members + per_page - 1) // per_page

    # 3. ดึงประวัติการจ่ายเงินทั้งหมด
    all_payments = conn.execute('''
        SELECT p.*, m.name FROM payments p
        JOIN members m ON p.house_number = m.house_number
        ORDER BY p.payment_date DESC, p.id DESC
    ''').fetchall()

    # --- ปิดการเชื่อมต่อตรงนี้จ๊ะ ---
    conn.close()

    # --- ส่งค่ากลับ (มีอันเดียวพอจ๊ะ) ---
    return render_template(
        'admin.html',
        stats=stats,
        payments=all_payments,
        members=members_all,
        year=current_year,
        page=page,
        total_pages=total_pages,
        per_page=per_page,
        total_members=total_members,
        today=today_date
    )

@app.route('/report_print')
def report_print():
    mode = request.args.get('mode', 'summary')
    year = str(datetime.now().year)
    conn = get_db_connection()

    if mode == 'daily':
        report_date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
        filter_type = request.args.get('filter', 'all')

        query = '''
            SELECT m.house_number, m.name, m.status, p.amount as total_paid,
                   p.payment_type, p.payment_date
            FROM payments p
            JOIN members m ON p.house_number = m.house_number
            WHERE p.payment_date = ?
        '''
        params = [report_date]
        if filter_type == 'cash': query += " AND p.payment_type = 'สด'"
        elif filter_type == 'transfer': query += " AND p.payment_type = 'โอน'"
    else:
        condition = request.args.get('condition', 'all')
        query = f'''
            SELECT m.house_number, m.name, m.status, SUM(p.amount) as total_paid,
                   GROUP_CONCAT(DISTINCT p.payment_type) as payment_type,
                   GROUP_CONCAT(DISTINCT p.payment_date) as payment_date
            FROM members m
            LEFT JOIN payments p ON m.house_number = p.house_number AND strftime('%Y', p.payment_date) = ?
            GROUP BY m.house_number
            HAVING 1=1
        '''
        params = [year]
        if condition == 'paid_360': query += ' AND total_paid >= 360'
        elif condition == 'paid_180': query += ' AND total_paid = 180'
        elif condition == 'unpaid': query += ' AND (total_paid IS NULL OR total_paid = 0)'
        elif condition in ['ปกติ', 'ว่าง', 'ยกเว้น']:
            query += ' AND m.status = ?'
            params.append(condition)

    query += f" {ORDER_LOGIC.replace('house_number', 'm.house_number')}"
    data = conn.execute(query, params).fetchall()
    total_houses = len(data)
    total_money = sum(row['total_paid'] or 0 for row in data)
    conn.close()

    r_date = request.args.get('date', '') if mode == 'daily' else ''
    return render_template('report_print.html', data=data, year=year,
                           total_houses=total_houses, total_money=total_money, report_date=r_date)

@app.route('/add_payment', methods=['POST'])
def add_payment():
    raw_date = request.form.get('payment_date')
    house = request.form.get('house_number')
    owner_name = request.form.get('owner_name')
    status = request.form.get('status')
    amount = int(request.form.get('amount'))
    pay_type = request.form.get('payment_type')
    input_year = datetime.strptime(raw_date, '%Y-%m-%d').year
    conn = get_db_connection()

    # --- เปลี่ยนการตรวจสอบ 24 ชั่วโมง เป็น 3 วัน โดยใช้ payment_date ---
    last_payment_date_str = conn.execute(
        'SELECT MAX(payment_date) FROM payments WHERE house_number = ?',
        (house,)
    ).fetchone()[0]

    if last_payment_date_str:
        last_payment_dt = datetime.strptime(last_payment_date_str, '%Y-%m-%d').date()
        today_date = datetime.now().date()
        # ถ้าวันสุดท้ายที่จ่ายคือภายใน 3 วันที่ผ่านมา (ไม่รวมวันนี้)
        if today_date - last_payment_dt < timedelta(days=30):
            conn.close()
            error_msg = f"ไม่สามารถบันทึกได้! มีการชำระเงินสำหรับบ้าน {house} ไปแล้วเมื่อวันที่ {last_payment_date_str} (กรุณารอ 30 วัน)"
            return redirect(url_for('index', error=error_msg))
    # --- สิ้นสุดการตรวจสอบ 3 วัน ---

    existing_paid = conn.execute('''
        SELECT SUM(amount) FROM payments WHERE house_number = ? AND strftime('%Y', payment_date) = ?
    ''', (house, str(input_year))).fetchone()[0] or 0
    if existing_paid + amount > 360:
        conn.close()
        error_msg = f"ยอดเงินเกินกำหนด! หลังนี้จ่ายแล้ว {existing_paid} บาท (รวมครั้งนี้จะเกิน 360 บาท)"
        return redirect(url_for('index', error=error_msg))


    conn.execute(
        'INSERT INTO payments (payment_date, house_number, amount, payment_type) VALUES (?, ?, ?, ?)',
        (raw_date, house, amount, pay_type)
    )
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/update_member', methods=['POST'])
def update_member():
    house = request.form.get('house_number')
    new_name = request.form.get('name')
    new_status = request.form.get('status')
    conn = get_db_connection()
    conn.execute('UPDATE members SET name = ?, status = ? WHERE house_number = ?', (new_name, new_status, house))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

@app.route('/delete_payment/<int:id>')
def delete_payment(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM payments WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(request.referrer or url_for('index'))

@app.route('/edit_basic', methods=['POST'])
def edit_basic():
    house = request.form.get('house_number')
    name = request.form.get('owner_name')
    status = request.form.get('status')
    conn = get_db_connection()
    conn.execute('UPDATE members SET name = ?, status = ? WHERE house_number = ?', (name, status, house))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/edit_payment', methods=['POST'])
def edit_payment():
    house = request.form.get('house_number')
    amount = int(request.form.get('amount'))
    pay_type = request.form.get('payment_type')
    date = request.form.get('payment_date')
    conn = get_db_connection()
    conn.execute('''
        DELETE FROM payments
        WHERE id = (SELECT id FROM payments WHERE house_number = ? ORDER BY id DESC LIMIT 1)
    ''', (house,))
    conn.execute('''
        INSERT INTO payments (payment_date, house_number, amount, payment_type)
        VALUES (?, ?, ?, ?)
    ''', (date, house, amount, pay_type))
    conn.commit()
    conn.close()
    return redirect('/')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
