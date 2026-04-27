import sqlite3
import os
import json

DB_PATH = r"c:\Documents\GitHub\Gramsetu\gramsetu\data\gramsetu.db"

import sys
import io

# Force UTF-8 output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def check_errors():

    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("--- Audit Log Status Distribution ---")
    rows = cursor.execute("SELECT status, COUNT(*) as count FROM audit_logs GROUP BY status").fetchall()
    for row in rows:
        print(dict(row))

    print("\n--- Recent Audit Logs (All) ---")
    rows = cursor.execute("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT 10").fetchall()
    for row in rows:
        print(dict(row))

    print("\n--- Recent Conversations ---")
    rows = cursor.execute("SELECT * FROM conversations ORDER BY timestamp DESC LIMIT 5").fetchall()
    for row in rows:
        print(dict(row))

    conn.close()

if __name__ == "__main__":
    check_errors()
