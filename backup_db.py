import shutil
import os
from datetime import datetime

def backup_database():
    # 1. ตั้งค่าชื่อไฟล์และโฟลเดอร์
    source_file = 'community.db'
    backup_folder = 'db_backup'
    
    # 2. ตรวจสอบว่ามีโฟลเดอร์ db_backup หรือยัง ถ้าไม่มีให้สร้างใหม่
    if not os.path.exists(backup_folder):
        os.makedirs(backup_folder)
        print(f"สร้างโฟลเดอร์ {backup_folder} เรียบร้อยแล้ว")

    # 3. ตรวจสอบว่าไฟล์ฐานข้อมูลต้นฉบับมีอยู่จริงไหม
    if os.path.exists(source_file):
        # สร้างชื่อไฟล์สำรองตามวันที่และเวลา (เช่น community_backup_20260427_2030.db)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"community_backup_{timestamp}.db"
        destination_path = os.path.join(backup_folder, backup_filename)

        # 4. ทำการก๊อปปี้ไฟล์
        try:
            shutil.copy2(source_file, destination_path)
            print(f"สำรองข้อมูลสำเร็จ: {destination_path}")
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการสำรองข้อมูล: {e}")
    else:
        print(f"ไม่พบไฟล์ {source_file} ในโฟลเดอร์ปัจจุบัน")

if __name__ == "__main__":
    backup_database()
