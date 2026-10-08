"""Creates the first superadmin (or resets the password of an existing account).

Run from the project root:   python dashboard/create_superadmin.py
"""
import getpass
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server"))

from dotenv import load_dotenv  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

load_dotenv()

from auth import USERNAME_RE, password_error  # noqa: E402
from database import connect, init_db  # noqa: E402


def main():
    init_db()
    username = input("Superadmin username: ").strip()
    if not USERNAME_RE.match(username):
        raise SystemExit("Username: 3 to 32 characters (letters, digits, . _ -).")

    password = getpass.getpass("Password (not shown): ")
    if password != getpass.getpass("Repeat password: "):
        raise SystemExit("The two passwords are different.")
    problem = password_error(password, username)
    if problem:
        raise SystemExit(problem)

    hashed = generate_password_hash(password)
    conn = connect()
    with conn:
        existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE users SET password_hash = ?, role = 'superadmin', active = 1 WHERE id = ?",
                (hashed, existing["id"]),
            )
            print(f"Account '{username}' already existed: password reset, role set to superadmin.")
        else:
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'superadmin')",
                (username, hashed),
            )
            print(f"Superadmin '{username}' created.")
    conn.close()


if __name__ == "__main__":
    main()
