# scripts/idtes.py
import sys
import bcrypt

# Kullanım:
#   py -3.9 scripts\idtes.py 1NS1-000M-XF1P '$2b$12$K9mg2b2qEytW/qUJ5r5FjO6f6YDxhtIHUXpeLi8q4vfsA7EhWTbXG'
#
# Not: PowerShell'de hash'i TEK TIRNAK ile ver ki $ işaretleri genişlemesin.

if len(sys.argv) >= 3:
    plain = sys.argv[1]
    hash_ = sys.argv[2]
else:
    # Argüman vermek istemezsen sabitleri buraya yaz
    plain = "1NS1-000M-XF1P"
    hash_ = "$2b$12$K9mg2b2qEytW/qUJ5r5FjO6f6YDxhtIHUXpeLi8q4vfsA7EhWTbXG"

plain_bytes = plain.strip().upper().encode("utf-8")
ok = bcrypt.checkpw(plain_bytes, hash_.encode("utf-8"))
print("match:", ok)
