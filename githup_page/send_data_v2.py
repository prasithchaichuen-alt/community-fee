import sqlite3
import requests
import json
from datetime import datetime
import os

# --- ตั้งค่าการเชื่อมต่อ ---
DB_PATH = 'community.db' 
GIST_ID = '3c6ddfd75ff359beff201d22c8a34cd9'
TOKEN = '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'

def get_data_and_send():
    try:
        if not os.path.exists(DB_PATH):
            print("ไม่พบไฟล์ฐานข้อมูล")
            return False

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        current_year = str(datetime.now().year)

        # 1. สรุปงบรวมรายปี
        cursor.execute("SELECT COUNT(DISTINCT house_number) FROM payments WHERE strftime('%Y', payment_date) = ?", (current_year,))
        paid_count = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT SUM(amount) FROM payments WHERE strftime('%Y', payment_date) = ?", (current_year,))
        total_income = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT SUM(amount) FROM expenses WHERE strftime('%Y', expense_date) = ?", (current_year,))
        total_expense = cursor.fetchone()[0] or 0

        # 2. ข้อมูลรายบ้าน
        cursor.execute("""
            SELECT m.house_number, m.name, m.status, SUM(p.amount)
            FROM members m
            LEFT JOIN payments p ON m.house_number = p.house_number 
                 AND strftime('%Y', p.payment_date) = ?
            GROUP BY m.house_number
        """, (current_year,))
        member_list = [
            {"house": r[0], "name": r[1], "status": r[2] or "ปกติ", "paid": r[3] or 0} 
            for r in cursor.fetchall()
        ]

        # 3. สรุปรายจ่ายแยกตาม Category ID (บังคับเป็น String และตั้งค่าเริ่มต้น 0)
        cursor.execute("""
            SELECT CAST(category_id AS TEXT), SUM(amount) 
            FROM expenses 
            WHERE strftime('%Y', expense_date) = ? AND category_id IS NOT NULL
            GROUP BY category_id
        """, (current_year,))
        
        ex_id_dict = {"1": 0, "2": 0, "3": 0, "4": 0}
        for row in cursor.fetchall():
            if row[0] in ex_id_dict:
                ex_id_dict[row[0]] = row[1]

        conn.close()

        balance = total_income - total_expense
        now = datetime.now().strftime("%d/%m/%Y %H:%M")

        payload = {
            "files": {
                "data.json": {
                    "content": json.dumps({
                        "paid_count": paid_count,
                        "total_income": total_income,
                        "total_expense": total_expense,
                        "balance": balance,
                        "update_at": now,
                        "members": member_list,
                        "expense_by_id": ex_id_dict
                    }, ensure_ascii=False, indent=2)
                }
            }
        }

        headers = {"Authorization": f"token {TOKEN}"}
        response = requests.patch(f"https://api.github.com/gists/{GIST_ID}", headers=headers, json=payload, timeout=10)
        
        if response.status_code == 200:
            print(f"[{now}] อัปเดตข้อมูลปี {current_year} สำเร็จ!")
            return True
        else:
            print(f"Error: {response.status_code}")
            return False

    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    get_data_and_send()
