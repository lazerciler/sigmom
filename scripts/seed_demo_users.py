# scripts/seed_demo_users.py
# Python 3.9+
import os
import bcrypt
import random
import string
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text

DB_URL = os.getenv("DATABASE_URL", "mysql+pymysql://root:@localhost/sigmom_pro_v1")

engine = create_engine(DB_URL)


def generate_random_code(length=12):
    chars = string.ascii_uppercase + string.digits
    code = "".join(random.choice(chars) for _ in range(length))
    return f"{code[:4]}-{code[4:8]}-{code[8:]}"


def hash_code_bcrypt(code):
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(code.encode("utf-8"), salt).decode("utf-8")


def main():
    output_lines = []

    with engine.begin() as conn:
        for i in range(1, 11):
            email = f"demo{i}@asiluye.com"
            name = f"Demo Kullanıcı {i}"

            result = conn.execute(
                text(
                    """
                    INSERT INTO users (email, name, created_at)
                    VALUES (:email, :name, NOW())
                """
                ),
                {"email": email, "name": name},
            )
            user_id = result.lastrowid

            plain_code = generate_random_code()
            hashed_code = hash_code_bcrypt(plain_code)

            conn.execute(
                text(
                    """
                    INSERT INTO referral_codes
                    (code_hash, status, tier, invited_by_admin_id, used_by_user_id, used_at, expires_at)
                    VALUES (:code_hash, 'RESERVED', 'default', :admin_id, NULL, NULL, :expires_at)
                """
                ),
                {
                    "code_hash": hashed_code,
                    "admin_id": user_id,
                    "expires_at": datetime.utcnow() + timedelta(days=30),
                },
            )

            line = f"{email} → {plain_code}"
            print("[OK]", line)
            output_lines.append(line)

    with open("demo_codes.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))

    print("\n[✓] demo_codes.txt dosyasına 10 kod yazıldı.")


if __name__ == "__main__":
    main()
