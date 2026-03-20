import sqlite3
import os

db_path = "db.sqlite3"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT nome, uuid_acesso FROM nucleo_devedor LIMIT 5;")
    rows = cursor.fetchall()
    for row in rows:
        print(row)
    conn.close()
else:
    print("Database not found.")
