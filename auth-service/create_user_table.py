import os
from dotenv import load_dotenv
import psycopg2

load_dotenv('.env')

dsn = os.getenv('DATABASE_URL') or (
    f"postgresql://{os.getenv('DATABASE_USER')}:{os.getenv('DATABASE_PASSWORD')}"
    f"@{os.getenv('DATABASE_HOST')}:{os.getenv('PORT', '5432')}/{os.getenv('DATABASE_NAME')}"
)

sql_create = """
CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  password TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

try:
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute(sql_create)
    conn.commit()
    cur.close()
    print('users table created or already exists.')
except Exception as e:
    print('Error creating table:', e)
finally:
    if 'conn' in locals() and conn:
        conn.close()