import jwt, datetime, os
import psycopg2
from psycopg2 import sql
from flask import Flask, request
from dotenv import load_dotenv
from werkzeug.security import check_password_hash

load_dotenv('.env')

server = Flask(__name__)

def get_db_connection():
    # use full DSN if provided
    dsn = os.getenv('DATABASE_URL')
    if dsn:
        return psycopg2.connect(dsn)
    return psycopg2.connect(host=os.getenv('DATABASE_HOST'),
                            database=os.getenv('DATABASE_NAME'),
                            user=os.getenv('DATABASE_USER'),
                            password=os.getenv('DATABASE_PASSWORD'),
                            port=os.getenv('PORT', '5432'))


@server.route('/login', methods=['POST'])
def login():
    auth_table_name = os.getenv('AUTH_TABLE', 'users')
    auth = request.authorization
    if not auth or not auth.username or not auth.password:
        return 'Could not verify', 401, {'WWW-Authenticate': 'Basic realm="Login required!"'}

    conn = get_db_connection()
    cur = conn.cursor()
    query = sql.SQL("SELECT email, password FROM {table} WHERE email = %s").format(
        table=sql.Identifier(auth_table_name)
    )
    cur.execute(query, (auth.username,))
    user_row = cur.fetchone()
    cur.close()
    conn.close()

    if not user_row:
        return 'Could not verify', 401, {'WWW-Authenticate': 'Basic realm="Login required!"'}

    email, stored_password = user_row
    # if passwords are stored hashed use check_password_hash, otherwise compare directly
    if stored_password.startswith('pbkdf2:') or stored_password.startswith('bcrypt$') or stored_password.startswith('sha'):
        valid = check_password_hash(stored_password, auth.password)
    else:
        valid = (auth.password == stored_password)

    if not valid or auth.username != email:
        return 'Could not verify', 401, {'WWW-Authenticate': 'Basic realm="Login required!"'}

    return CreateJWT(auth.username, os.environ['JWT_SECRET'], True)

def CreateJWT(username, secret, authz):
    return jwt.encode(
        {
            "username": username,
            "exp": datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(days=1),
            "iat": datetime.datetime.now(tz=datetime.timezone.utc),
            "admin": authz,
        },
        secret,
        algorithm="HS256",
    )

@server.route('/validate', methods=['POST'])
def validate():
    encoded_jwt = request.headers.get('Authorization')
    if not encoded_jwt:
        return 'Unauthorized', 401, {'WWW-Authenticate': 'Basic realm="Login required!"'}

    token = encoded_jwt.split(' ')[1] if ' ' in encoded_jwt else encoded_jwt
    try:
        decoded_jwt = jwt.decode(token, os.environ['JWT_SECRET'], algorithms=["HS256"])
    except:
        return 'Unauthorized', 401, {'WWW-Authenticate': 'Basic realm="Login required!"'}
    return decoded_jwt, 200

if __name__ == '__main__':
    server.run(host='0.0.0.0', port=5000)