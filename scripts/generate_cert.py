#!/usr/bin/env python3
# scripts/generate_cert.py

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import datetime


# Sertifika bilgileri
def generate_self_signed_cert(cert_file="./cert/cert.pem", key_file="./cert/key.pem"):
    # Özel anahtar oluştur
    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )

    # Konu bilgileri
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "TR"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Istanbul"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "Istanbul"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Localhost Dev"),
            x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
        ]
    )

    # Sertifika oluştur
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.DNSName("127.0.0.1"),
                ]
            ),
            critical=False,
        )
        .sign(private_key, hashes.SHA256(), default_backend())
    )

    # Dosyalara yaz
    with open(cert_file, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    with open(key_file, "wb") as f:
        f.write(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    print(f"Sertifika oluşturuldu: {cert_file}")
    print(f"Anahtar oluşturuldu: {key_file}")


if __name__ == "__main__":
    generate_self_signed_cert()
