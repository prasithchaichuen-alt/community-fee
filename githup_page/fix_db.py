import sqlite3
import os

DB_NAME = 'community.db'

def fix_database():
    print(f"กำลังตรวจสอบและปรับปรุงฐานข้อมูล: {DB_NAME}...")
    
    # เชื่อมต่อฐานข้อมูล (ถ้าไม่มีจะสร้างใหม่ แต่ถ้ามีจะใช้ก้อนเดิม)
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # 1. สร้างตาราง system_settings (ถ้ายังไม่มี)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    # 2. เพิ่มค่าตั้งต้นสำหรับหน้า Admin (ใช้ INSERT OR IGNORE เพื่อไม่ให้ทับค่าเก่าที่ตั้งไว้แล้ว)
    default_settings = [
        ('btn_payment', '1'),
        ('btn_expense', '1'),
        ('show_payment_btn', '1'),
        ('show_report_btn', '1')
    ]
    cursor.executemany('INSERT OR IGNORE INTO system_settings (key, value) VALUES (?, ?)', default_settings)

    # 3. สร้างตารางหลัก (ใช้ IF NOT EXISTS เพื่อป้องกันการเขียนทับข้อมูลเดิม)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS members (
            house_number TEXT PRIMARY KEY, 
            name TEXT, 
            status TEXT DEFAULT 'ปกติ'
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            payment_date TEXT, 
            house_number TEXT, 
            amount REAL, 
            payment_type TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            detail TEXT, 
            amount REAL, 
            category TEXT, 
            expense_date TEXT
        )
    ''')

    # 4. ตรวจสอบและเพิ่มคอลัมน์ created_at (ถ้ายังไม่มี)
    try:
        cursor.execute("SELECT created_at FROM expenses LIMIT 1")
    except sqlite3.OperationalError:
        print("เพิ่มคอลัมน์ created_at...")
        cursor.execute("ALTER TABLE expenses ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP")

    # 5. ตรวจสอบและเพิ่มคอลัมน์ category_id (ถ้ายังไม่มี)
    try:
        cursor.execute("SELECT category_id FROM expenses LIMIT 1")
    except sqlite3.OperationalError:
        print("เพิ่มคอลัมน์ category_id สำหรับระบบจัดหมวดหมู่...")
        cursor.execute("ALTER TABLE expenses ADD COLUMN category_id INTEGER DEFAULT 0")

    # 6. อัปเดต category_id ให้ครอบคลุมรายการใน DB ของอ้าย
    # หมวด 1: ค่าใช้จ่ายส่วนกลาง
    cursor.execute("UPDATE expenses SET category_id = 1 WHERE category = 'ค่าใช้จ่ายส่วนกลาง'")
    
    # หมวด 2: ค่าจ้างและบริการ (เพิ่มคำว่า 'ขยะ' เพื่อให้คลุมรายการค่าดูแลขยะที่อ้ายคีย์ไว้)
    cursor.execute("""
        UPDATE expenses 
        SET category_id = 2 
        WHERE category = 'ค่าจ้างและบริการ' 
        OR (detail LIKE '%จ้าง%' OR detail LIKE '%ขยะ%' OR detail LIKE '%ซ่อม%' OR detail LIKE '%ติดตั้ง%' OR detail LIKE '%แม่บ้าน%')
    """)
    
    # หมวด 3: ค่ากิจกรรม
    cursor.execute("""
        UPDATE expenses 
        SET category_id = 3 
        WHERE category = 'ค่ากิจกรรม' 
        OR (detail LIKE '%รดน้ำ%' OR detail LIKE '%ดำหัว%' OR detail LIKE '%สงกรานต์%' OR detail LIKE '%กระเช้า%')
    """)
    
    # หมวด 4: ค่าดำเนินการ (และรายการที่ยังไม่เข้าพวก)
    cursor.execute("""
        UPDATE expenses 
        SET category_id = 4 
        WHERE category = 'ค่าดำเนินการ' 
        OR (category_id = 0 OR category_id IS NULL)
    """)

    conn.commit()
    
    # สรุปผล
    print("-" * 30)
    print("✅ ปรับปรุงฐานข้อมูลเรียบร้อย (ข้อมูลเดิมปลอดภัย 100%)")
    cursor.execute("SELECT category_id, COUNT(*), SUM(amount) FROM expenses GROUP BY category_id")
    for r in cursor.fetchall():
        print(f"หมวด ID {r[0]}: {r[1]} รายการ | ยอดเงินรวม: {r[2]:,.2f}")
        
    conn.close()

if __name__ == "__main__":
    fix_database()
