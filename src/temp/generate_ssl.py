import ipaddress
import datetime
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

def generate_cert():
    print("Generating RSA key pair...")
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, u"sahidemondesk.local"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"Aiden Assistant"),
    ])

    alt_names = [
        x509.DNSName(u"sahidemondesk.local"),
        x509.DNSName(u"sahidemondesk"),
        x509.DNSName(u"localhost"),
        x509.IPAddress(ipaddress.ip_address("192.168.1.9")),
        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
    ]

    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.datetime.now(datetime.timezone.utc)
    ).not_valid_after(
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=3650)
    ).add_extension(
        x509.SubjectAlternativeName(alt_names),
        critical=False,
    ).sign(key, hashes.SHA256())

    print("Writing key.pem and cert.pem...")
    with open("key.pem", "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))

    with open("cert.pem", "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    print("Successfully generated SSL certificates with SAN entries!")

if __name__ == "__main__":
    generate_cert()
