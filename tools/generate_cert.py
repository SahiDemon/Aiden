import os
import datetime
import ipaddress
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

def generate_self_signed_cert(cert_path="cert.pem", key_path="key.pem"):
    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # Generate certificate subject/issuer
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"Aiden AI"),
        x509.NameAttribute(NameOID.COMMON_NAME, u"192.168.1.9"),
    ])

    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        private_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.datetime.now(datetime.UTC)
    ).not_valid_after(
        # Valid for 10 years
        datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=3650)
    ).add_extension(
        x509.SubjectAlternativeName([x509.IPAddress(ipaddress.IPv4Address(u"192.168.1.9"))]),
        critical=False,
    ).sign(private_key, hashes.SHA256())

    # Write private key
    with open(key_path, "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))

    # Write certificate
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    print(f"Generated {cert_path} and {key_path}")

if __name__ == "__main__":
    generate_self_signed_cert()
