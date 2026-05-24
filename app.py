import sqlite3
import json
import shutil
import os
import os
# เพิ่มบรรทัดนี้ลงไปครับ
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
import send_data

app = Flask(__name__)
app.secret_key = "community_secret_key"
DB = 'community.db'

def get_db_connection():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

ORDER_LOGIC = "ORDER BY CAST(SUBSTR(house_number, INSTR(house_number, '/') + 1) AS INTEGER)"

# ======================
# --- ฟังก์ชันสำหรับ Backup (วางไว้ส่วนบนของไฟล์) ---
def perform_backup():
    source_file = 'community.db'
    backup_folder = 'db_backup'
    
    if not os.path.exists(backup_folder):
        os.makedirs(backup_folder)
        
    if os.path.exists(source_file):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"community_backup_{timestamp}.db"
        destination_path = os.path.join(backup_folder, backup_filename)
        shutil.copy2(source_file, destination_path)
        return True, backup_filename
    return False, None

# --- สร้าง Route สำหรับกดปุ่ม ---
@app.route('/backup_now')
def backup_now():
    success, filename = perform_backup()
    if success:
        flash(f'สำรองข้อมูลสำเร็จ: {filename}', 'success')
    else:
        flash('เกิดข้อผิดพลาดในการสำรองข้อมูล', 'danger')
    return redirect(url_for('admin')) # กลับไปหน้า Admin หรือหน้าที่คุณต้องการ
# ======================
# ======================
# INDEX (หน้าแรก)
# ======================
@app.route('/')
def index():
    conn = get_db_connection()
    # ดึงการตั้งค่าเพื่อเปิด/ปิดปุ่ม
    rows = conn.execute("SELECT key, value FROM system_settings").fetchall()
    settings = {row["key"]: int(row["value"]) for row in rows}
    conn.close()
    return render_template('index.html', settings=settings)

@app.route('/edit_basic', methods=['POST'])
def edit_basic():
    house = request.form.get('house_number')
    name = request.form.get('owner_name')
    status = request.form.get('status')
    conn = get_db_connection()
    conn.execute('UPDATE members SET name = ?, status = ? WHERE house_number = ?', (name, status, house))
    conn.commit()
    conn.close()
    return redirect(url_for('payment'))

@app.route('/edit_payment', methods=['POST'])
def edit_payment():
    house = request.form.get('house_number')
    new_amount = request.form.get('amount')
    new_pay_type = request.form.get('payment_type')
    date_str = request.form.get('payment_date')
    
    if not house or house == "410/":
        flash("กรุณาระบุบ้านเลขที่ก่อน", "warning")
        return redirect(url_for('payment'))

    conn = get_db_connection()

    # ✅ ดึงปีจากวันที่ที่กรอก
    current_year = datetime.strptime(date_str, '%Y-%m-%d').strftime('%Y')
    
    # 🔍 ค้นหา "เฉพาะปีเดียวกัน"
    last_record = conn.execute(
        '''
        SELECT id FROM payments 
        WHERE house_number = ?
        AND strftime('%Y', payment_date) = ?
        ORDER BY id DESC LIMIT 1
        ''',
        (house, current_year)
    ).fetchone()

    if last_record:
        # ✅ มีข้อมูลของปีนี้อยู่แล้ว -> แก้ไขยอดล่าสุดของปีนี้
        conn.execute('''
            UPDATE payments 
            SET amount = ?, 
                payment_type = ? 
            WHERE id = ?
        ''', (new_amount, new_pay_type, last_record['id']))
        
        conn.commit()

        flash(
            f"✅ แก้ไขยอดเงินบ้าน {house} ของปี {current_year} เรียบร้อยแล้ว",
            "success"
        )

    else:
        # 🆕 ยังไม่มีข้อมูลในปีนี้ -> บันทึกใหม่
        conn.execute('''
            INSERT INTO payments 
            (payment_date, house_number, amount, payment_type) 
            VALUES (?, ?, ?, ?)
        ''', (date_str, house, new_amount, new_pay_type))

        conn.commit()

        flash(
            f"🆕 ไม่พบข้อมูลของปี {current_year} จึงสร้างรายการใหม่ให้บ้าน {house} เรียบร้อยแล้ว",
            "info"
        )
        
    conn.close()

    return redirect(url_for('payment'))

# ======================
# PAYMENT (บันทึกรับเงิน)
# ======================
@app.route('/payment')
def payment():
    conn = get_db_connection()
    current_year = str(datetime.now().year)
    
    # 1. ดึงข้อมูลสมาชิกทั้งหมด
    members = conn.execute('SELECT * FROM members').fetchall()
    members_dict = {m['house_number']: m['name'] for m in members}
    status_dict = {m['house_number']: m['status'] for m in members}

    # 2. ดึงยอดที่จ่ายแล้วในปีนี้
    paid_rows = conn.execute('''
        SELECT house_number, SUM(amount) as total 
        FROM payments 
        WHERE strftime('%Y', payment_date) = ? 
        GROUP BY house_number
    ''', (current_year,)).fetchall()
    paid_dict = {row['house_number']: row['total'] for row in paid_rows}
    
    conn.close()

    # ส่งข้อมูลแบบ JSON ไปให้ JavaScript ใน HTML ใช้งาน
    return render_template('payment.html', 
                           today=datetime.now().strftime('%Y-%m-%d'),
                           members_json=json.dumps(members_dict),
                           paid_json=json.dumps(paid_dict),
                           status_json=json.dumps(status_dict))

@app.route('/add_payment', methods=['POST'])
def add_payment():
    house = request.form.get('house_number')
    amount = request.form.get('amount')
    pay_type = request.form.get('payment_type')
    date_str = request.form.get('payment_date')
    
    # แปลงวันที่จาก String เป็น Object เพื่อคำนวณ
    payment_date = datetime.strptime(date_str, '%Y-%m-%d')
    # คำนวณหาย้อนหลัง 30 วัน
    thirty_days_ago = (payment_date - timedelta(days=30)).strftime('%Y-%m-%d')

    conn = get_db_connection()
    
    # 🔍 ขั้นตอนตรวจสอบ: ค้นหาว่ามีการจ่ายเงินของบ้านนี้ในช่วง 30 วันที่ผ่านมาไหม
    existing_payment = conn.execute('''
        SELECT payment_date FROM payments 
        WHERE house_number = ? 
        AND payment_date > ? 
        ORDER BY payment_date DESC LIMIT 1
    ''', (house, thirty_days_ago)).fetchone()

    if existing_payment:
        last_date = existing_payment['payment_date']
        conn.close()
        # ส่งกลับไปหน้าเดิมพร้อมแจ้งเตือน (ผ่าน JavaScript alert)
        return f"<script>alert('บ้านเลขที่ {house} มีการบันทึกเงินไปแล้วเมื่อวันที่ {last_date} (ยังไม่ครบ 30 วัน)'); window.history.back();</script>"

    # ✅ หากผ่านการตรวจสอบ (ไม่มีการจ่ายใน 30 วัน) ให้บันทึกตามปกติ
    conn.execute('INSERT INTO payments (payment_date, house_number, amount, payment_type) VALUES (?, ?, ?, ?)',
                 (date_str, house, amount, pay_type))
    conn.commit()
    conn.close()
    
    return redirect(url_for('payment'))

# ฟังก์ชันสำหรับลบรายการชำระเงินในหน้าประวัติ
@app.route('/delete_payment/<int:id>')
def delete_payment(id):
    conn = get_db_connection()
    # ลบข้อมูลจากตาราง payments โดยใช้ ID
    conn.execute('DELETE FROM payments WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    
    # เมื่อลบเสร็จ ให้กลับไปที่หน้าประวัติเหมือนเดิม
    return redirect(url_for('history'))

# ======================
 # ลบบรรทัด @app.app_context() ออกไปเลยครับ
@app.route('/force-sync')
def force_sync():
    # เรียกฟังก์ชันอัปเดตจากไฟล์ send_data.py
    success, message = send_data.get_data_and_send()
    
    if success:
        flash(f"✅ {message}", "success")
    else:
        flash(f"❌ เกิดข้อผิดพลาด: {message}", "danger")
        
    # พอกดเสร็จ ให้เด้งกลับไปหน้าหลัก (หรือหน้า admin ของอ้าย)
    return redirect(url_for('index')) # ถ้าหน้าแรกอ้ายชื่อ index ก็ใช้ตามนี้ครับ
# ======================
# EXPENSE (บันทึกรายจ่าย)
# ======================

@app.route('/expense')
def expense_entry():
    conn = get_db_connection()
    # เรียงตาม expense_date DESC, id DESC (วันที่ใหม่สุดขึ้นก่อน ถ้าวันเดียวกันเรียงตามลำดับบันทึก)
    expenses = conn.execute("SELECT * FROM expenses ORDER BY expense_date DESC, id DESC LIMIT 10").fetchall()
    conn.close()
    return render_template('expense.html', expenses=expenses, today=datetime.now().strftime('%Y-%m-%d'))

@app.route('/add_expense', methods=['POST'])
def add_expense():
    conn = get_db_connection()
    conn.execute('INSERT INTO expenses (detail, amount, category, expense_date) VALUES (?, ?, ?, ?)',
                 (request.form['detail'], request.form['amount'], request.form['category'], request.form['expense_date']))
    conn.commit()
    conn.close()
    return redirect(url_for('expense_entry'))

# ======================
# ADMIN (ระบบจัดการ)
# ======================
@app.route('/admin')
def admin():
    conn = get_db_connection()
    year = str(datetime.now().year)
    
    # สถิติรายรับ
    stats = conn.execute('''
        SELECT SUM(amount) as total_money, 
        SUM(CASE WHEN payment_type = 'สด' THEN amount ELSE 0 END) as cash_total,
        SUM(CASE WHEN payment_type = 'โอน' THEN amount ELSE 0 END) as transfer_total,
        COUNT(DISTINCT house_number) as house_count FROM payments WHERE strftime('%Y', payment_date) = ?
    ''', (year,)).fetchone()

    # สถิติรายจ่าย
    expense_stats = conn.execute("SELECT SUM(amount) as total_expense FROM expenses WHERE strftime('%Y', expense_date) = ?", (year,)).fetchone()

    # การตั้งค่าปุ่ม
    rows = conn.execute("SELECT key, value FROM system_settings").fetchall()
    settings = {row["key"]: int(row["value"]) for row in rows}

    # รายชื่อสมาชิก (Pagination)
    page = int(request.args.get('page', 1))
    per_page = 50
    offset = (page - 1) * per_page
    members = conn.execute(f'SELECT * FROM members {ORDER_LOGIC} LIMIT ? OFFSET ?', (per_page, offset)).fetchall()
    
    conn.close()
    return render_template('admin.html', stats=stats, expense_stats=expense_stats, settings=settings, members=members, year=year, today=datetime.now().strftime('%Y-%m-%d'))

# ======================
# REPORTS (รายงาน)

@app.route('/report_print')
def report_print():
    mode = request.args.get('mode')
    date_str = request.args.get('date')
    filter_val = request.args.get('filter', 'all')
    condition = request.args.get('condition', 'all')
    
    current_year = datetime.now().year
    conn = get_db_connection()
    data = []
    title_condition = ""

    # ==========================================
    # 1. รายงานรายวัน (Daily Report)
    # ==========================================
    if mode == 'daily':
        # ดึงข้อมูลดิบออกมาก่อน แล้วค่อยมากรองด้วย Python เพื่อความแม่นยำสูงสุด
        sql = '''
            SELECT p.house_number, p.amount as total_paid, p.payment_type, p.payment_date, 
                   m.name, m.status
            FROM payments p
            JOIN members m ON p.house_number = m.house_number
            WHERE p.payment_date = ?
        '''
        raw_data = conn.execute(sql, [date_str]).fetchall()
        
        if filter_val == 'cash':
            # กรองโดยหาคำว่า 'สด' หรือ 'cash' (ไม่สนตัวเล็กตัวใหญ่และช่องว่าง)
            data = [r for r in raw_data if 'สด' in (r['payment_type'] or '') or 'cash' in (r['payment_type'] or '').lower()]
            title_condition = f"ประจำวันที่ {date_str} (เฉพาะเงินสด)"
        elif filter_val == 'transfer':
            # กรองโดยหาคำว่า 'โอน' หรือ 'transfer'
            data = [r for r in raw_data if 'โอน' in (r['payment_type'] or '') or 'transfer' in (r['payment_type'] or '').lower()]
            title_condition = f"ประจำวันที่ {date_str} (เฉพาะเงินโอน)"
        else:
            data = raw_data
            title_condition = f"ประจำวันที่ {date_str} (ทุกรายการ)"
            
        # เรียงลำดับบ้านเลขที่หลังกรอกเสร็จ
        data.sort(key=lambda x: int(x['house_number'].split('/')[-1]) if '/' in x['house_number'] else 0)

    # ==========================================
    # 2. รายงานสรุปปี (Summary Report)
    # ==========================================
    elif mode == 'summary':
        sql_base = f'''
            SELECT m.house_number, m.name, m.status,
                   (SELECT SUM(amount) FROM payments 
                    WHERE house_number = m.house_number 
                    AND strftime('%Y', payment_date) = ?) as total_paid,
                   (SELECT payment_type FROM payments 
                    WHERE house_number = m.house_number 
                    AND strftime('%Y', payment_date) = ? 
                    ORDER BY id DESC LIMIT 1) as payment_type,
                   (SELECT payment_date FROM payments 
                    WHERE house_number = m.house_number 
                    AND strftime('%Y', payment_date) = ? 
                    ORDER BY id DESC LIMIT 1) as payment_date
            FROM members m
        '''
        params = [str(current_year), str(current_year), str(current_year)]
        
        if condition == 'paid_360':
            sql = f"SELECT * FROM ({sql_base}) WHERE total_paid >= 360"
            title_condition = f"สรุปปี {current_year}: จ่ายครบ (360.-)"
        elif condition == 'paid_180':
            sql = f"SELECT * FROM ({sql_base}) WHERE total_paid = 180"
            title_condition = f"สรุปปี {current_year}: จ่ายบางส่วน (180.-)"
        elif condition == 'unpaid':
            sql = f"SELECT * FROM ({sql_base}) WHERE (total_paid IS NULL OR total_paid = 0) AND status = 'ปกติ'"
            title_condition = f"สรุปปี {current_year}: ยังไม่ได้ชำระเงิน"
        elif condition == 'ว่าง':
            sql = f"SELECT * FROM ({sql_base}) WHERE status = 'ว่าง'"
            title_condition = "สถานะ: บ้านว่าง"
        elif condition == 'ยกเว้น':
            sql = f"SELECT * FROM ({sql_base}) WHERE status = 'ยกเว้น'"
            title_condition = "สถานะ: ยกเว้นการเก็บ"
        else:
            sql = sql_base
            title_condition = f"สรุปภาพรวมปี {current_year} (ทั้งหมด)"

        sql += " ORDER BY CAST(SUBSTR(house_number, INSTR(house_number, '/') + 1) AS INTEGER)"
        data = conn.execute(sql, params).fetchall()

    # คำนวณยอดเงินรวม
    total_money = sum(row['total_paid'] or 0 for row in data)
    total_houses = len(data)
    conn.close()

    return render_template('report_print.html', 
                           data=data, 
                           year=current_year, 
                           condition=title_condition,
                           total_money=total_money,
                           total_houses=total_houses)

# ======================

# แก้ไข Route เดิมให้เรียกไฟล์ manage_expenses.html และเพิ่มระบบค้นหา
@app.route('/admin/expenses')
def admin_expenses():
    search = request.args.get('search', '')
    conn = get_db_connection()
    if search:
        query = "SELECT * FROM expenses WHERE detail LIKE ? OR expense_date LIKE ? ORDER BY expense_date DESC, id DESC"
        expenses = conn.execute(query, (f'%{search}%', f'%{search}%')).fetchall()
    else:
        expenses = conn.execute("SELECT * FROM expenses ORDER BY expense_date DESC, id DESC").fetchall()
    conn.close()
    return render_template('manage_expenses.html', expenses=expenses, search=search)

@app.route('/delete_expense/<int:id>')
def delete_expense(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM expenses WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash("ลบรายการรายจ่ายเรียบร้อยแล้ว", "success")
    return redirect(url_for('admin_expenses'))
# ======================

@app.route('/report_expense')
def report_expense():
    date_str = request.args.get('date')
    filter_type = request.args.get('filter')
    conn = get_db_connection()
    if filter_type == 'daily':
        title = f"รายงานรายจ่ายประจำวันที่ {date_str}"
        expenses = conn.execute("SELECT * FROM expenses WHERE expense_date = ? ORDER BY expense_date DESC, id DESC", (date_str,)).fetchall()
    else:
        month_str = date_str[:7]
        title = f"รายงานรายจ่ายประจำเดือน {month_str}"
        expenses = conn.execute("SELECT * FROM expenses WHERE expense_date LIKE ? ORDER BY expense_date DESC, id DESC", (f'{month_str}%',)).fetchall()
    total_amount = sum(item['amount'] for item in expenses)
    conn.close()
    return render_template('report_expense_print.html', expenses=expenses, title=title, total_amount=total_amount, datetime=datetime)

@app.route('/report_expense_summary')
def report_expense_summary():
    category = request.args.get('category')
    year = request.args.get('year')
    
    conn = get_db_connection()
    if category == 'all':
        title = f"รายงานสรุปรายจ่ายทุกหมวดหมู่ ปี {year}"
        expenses = conn.execute("SELECT * FROM expenses WHERE strftime('%Y', expense_date) = ? ORDER BY expense_date DESC, id DESC", (year,)).fetchall()
    else:
        cat_names = {'1': 'ค่าใช้จ่ายส่วนกลาง', '2': 'ค่าจ้างบริการ', '3': 'ค่าใช้จ่ายกิจกรรม', '4': 'ค่าดำเนินการ'}
        title = f"รายงานสรุปรายจ่ายหมวด: {cat_names.get(category)} ปี {year}"
        expenses = conn.execute("SELECT * FROM expenses WHERE strftime('%Y', expense_date) = ? AND category = ? ORDER BY expense_date DESC, id DESC", (year, category)).fetchall()
    
    total_amount = sum(item['amount'] for item in expenses)
    conn.close()
    
    return render_template('report_expense_print.html', 
                           expenses=expenses, 
                           title=title, 
                           total_amount=total_amount,
                           datetime=datetime)

# ======================

@app.route('/update_setting', methods=['POST'])
def update_setting():
    key = request.form.get('key')
    value = request.form.get('value')
    conn = get_db_connection()
    conn.execute("UPDATE system_settings SET value = ? WHERE key = ?", (value, key))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

@app.route('/history')
def history():
    conn = get_db_connection()
    payments = conn.execute('''
        SELECT p.*, m.name FROM payments p 
        JOIN members m ON p.house_number = m.house_number 
        ORDER BY p.payment_date DESC
    ''').fetchall()
    conn.close()
    return render_template('history.html', payments=payments)
# ======================
# API สำหรับแอป Android
# ======================
@app.route('/api/members', methods=['GET'])
def api_get_members():
    conn = get_db_connection()
    # ดึงข้อมูลจากตาราง members (หรือจะดึงยอดจ่ายมาด้วยก็ได้)
    # ในที่นี้ดึงตามโครงสร้างที่แอป Android ของคุณต้องการ (Member.kt)
    query = f"SELECT house_number, name, status FROM members {ORDER_LOGIC}"
    rows = conn.execute(query).fetchall()
    conn.close()

    # แปลงข้อมูลจาก SQLite Row เป็น List ของ Dictionary เพื่อให้ส่งเป็น JSON ได้
    members_list = []
    for row in rows:
        members_list.append({
            "house_number": row["house_number"],
            "name": row["name"],
            "status": row["status"]
        })

    return jsonify(members_list)

# ======================
# API สำหรับแอป Android - ดึงประวัติชำระเงิน
# ======================
@app.route('/api/payments/<house_number>', methods=['GET'])
def api_get_payments(house_number):
    # แปลงเลขที่บ้านกลับเป็นรูปแบบที่ถูกต้อง (เปลี่ยน _ เป็น /)
    real_house_number = house_number.replace('_', '/')
    
    conn = get_db_connection()
    # ดึงข้อมูลจากตาราง payments ตามเลขที่บ้าน สั่งเรียงตามวันที่ใหม่สุดขึ้นก่อน
    rows = conn.execute('''
        SELECT p.id, m.name as owner_name, p.payment_date, p.amount, p.payment_type 
        FROM payments p
        JOIN members m ON p.house_number = m.house_number
        WHERE p.house_number = ?
        ORDER BY p.payment_date DESC
    ''', (real_house_number,)).fetchall()
    
    conn.close()

    # แปลงข้อมูลเป็น List ของ Dictionary สำหรับส่งเป็น JSON
    payments_list = []
    for row in rows:
        payments_list.append({
            "id": row["id"],
            "owner_name": row["owner_name"],
            "payment_date": row["payment_date"],
            "amount": row["amount"],
            "payment_type": row["payment_type"]
        })

    return jsonify(payments_list)

# API สำหรับเพิ่มหรือแก้ไขข้อมูลสมาชิก
@app.route('/api/members/save', methods=['POST'])
def api_save_member():
    data = request.json
    house_number = data.get('house_number')
    name = data.get('name')
    status = data.get('status')
    
    conn = get_db_connection()
    # ใช้ INSERT OR REPLACE: ถ้ามีเลขที่บ้านนี้อยู่แล้วจะอัปเดต ถ้าไม่มีจะเพิ่มใหม่
    conn.execute('''
        INSERT OR REPLACE INTO members (house_number, name, status) 
        VALUES (?, ?, ?)
    ''', (house_number, name, status))
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": f"บันทึกบ้านเลขที่ {house_number} เรียบร้อย"})

# API สำหรับลบสมาชิก
@app.route('/api/members/delete/<house_id>', methods=['DELETE'])
def api_delete_member(house_id):
    # เปลี่ยน / เป็น _ เพื่อความปลอดภัยใน URL (เช่น 410_1)
    real_house_number = house_id.replace('_', '/')
    conn = get_db_connection()
    conn.execute('DELETE FROM members WHERE house_number = ?', (real_house_number,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": "ลบข้อมูลเรียบร้อย"})

@app.route('/verify_admin', methods=['POST'])
def verify_admin():
    user_input = request.form.get('password')
    # อ่านรหัสจากไฟล์ลับ
    try:
        with open(os.path.join(BASE_DIR, '.admin_pwd'), 'r') as f:
            secret_password = f.read().strip()
        
        if user_input == secret_password:
            return jsonify({"status": "success"})
        else:
            return jsonify({"status": "error", "message": "รหัสผ่านไม่ถูกต้อง!"})
    except FileNotFoundError:
        # ถ้าหาไฟล์ไม่เจอ ให้ใช้รหัสสำรองป้องกันเข้าไม่ได้
        if user_input == "gmail@123456":
            return jsonify({"status": "success"})
        return jsonify({"status": "error", "message": "ไม่พบไฟล์รหัสผ่าน!"})
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
