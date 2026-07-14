# init_db.py
import sqlite3

DB = 'psp_app.db'
conn = sqlite3.connect(DB)
c = conn.cursor()

c.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL
)
''')

conn.commit()
conn.close()
print("Initialized database:", DB)
