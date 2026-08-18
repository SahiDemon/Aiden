"""Generate a local self-signed TLS certificate for Aiden."""

from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
from pathlib import Path
from typing import Sequence

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def generate_self_signed_cert(
    cert_path: Path,
    key_path: Path,
    *,
    common_name: str,
    dns_names: Sequence[str],
    ip_addresses: Sequence[str],
    valid_days: int,
) -> None:
    """Generate a certificate and unencrypted private key for local development."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Aiden Assistant"),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]
    )

    alternative_names: list[x509.GeneralName] = [
        x509.DNSName(name) for name in dict.fromkeys(dns_names)
    ]
    alternative_names.extend(
        x509.IPAddress(ipaddress.ip_address(address))
        for address in dict.fromkeys(ip_addresses)
    )

    now = dt.datetime.now(dt.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + dt.timedelta(days=valid_days))
        .add_extension(x509.SubjectAlternativeName(alternative_names), critical=False)
        .sign(private_key, hashes.SHA256())
    )

    cert_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    key_path.chmod(0o600)
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cert", type=Path, default=Path("cert.pem"), help="Certificate output path")
    parser.add_argument("--key", type=Path, default=Path("key.pem"), help="Private-key output path")
    parser.add_argument("--common-name", default="localhost", help="Certificate common name")
    parser.add_argument(
        "--dns-name",
        action="append",
        dest="dns_names",
        help="DNS subject alternative name; may be repeated",
    )
    parser.add_argument(
        "--ip-address",
        action="append",
        dest="ip_addresses",
        help="IP subject alternative name; may be repeated",
    )
    parser.add_argument("--valid-days", type=int, default=3650, help="Certificate lifetime in days")
    args = parser.parse_args()
    if args.valid_days < 1:
        parser.error("--valid-days must be at least 1")
    return args


def main() -> None:
    args = parse_args()
    dns_names = args.dns_names or [args.common_name, "localhost"]
    ip_addresses = args.ip_addresses or ["127.0.0.1"]
    generate_self_signed_cert(
        args.cert,
        args.key,
        common_name=args.common_name,
        dns_names=dns_names,
        ip_addresses=ip_addresses,
        valid_days=args.valid_days,
    )
    print(f"Generated certificate: {args.cert}")
    print(f"Generated private key: {args.key}")


if __name__ == "__main__":
    main()
