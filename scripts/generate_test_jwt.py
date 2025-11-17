#!/usr/bin/env python3
"""Generate test JWT tokens for Active Graph KG development and testing.

Usage:
    # HS256 (dev/staging)
    python scripts/generate_test_jwt.py --tenant test_tenant --actor test_user --scopes "admin:refresh,search:read"

    # RS256 (production)
    python scripts/generate_test_jwt.py --algorithm RS256 --private-key /path/to/private.pem

Environment variables:
    JWT_SECRET_KEY: Secret key or private key for signing (if not provided via --secret/--private-key)
    JWT_ALGORITHM: Algorithm to use (default: HS256)
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

try:
    import jwt
except ImportError:
    print("Error: PyJWT not installed. Install with: pip install PyJWT[crypto]")
    sys.exit(1)


def load_private_key(path: str) -> str:
    """Load RSA private key from file."""
    with open(path) as f:
        return f.read()


def generate_jwt(
    tenant_id: str,
    actor_id: str,
    scopes: list[str],
    algorithm: str = "HS256",
    secret_key: str = None,
    private_key_path: str = None,
    audience: str = "activekg",
    issuer: str = "https://staging-auth.yourcompany.com",
    expires_hours: int = 24,
    actor_type: str = "user",
) -> str:
    """Generate a JWT token for testing.

    Args:
        tenant_id: Tenant ID (for RLS)
        actor_id: Actor ID (sub claim)
        scopes: List of scopes (e.g., ["admin:refresh", "search:read"])
        algorithm: JWT algorithm (HS256 or RS256)
        secret_key: Secret key for HS256
        private_key_path: Path to private key for RS256
        audience: JWT audience claim
        issuer: JWT issuer claim
        expires_hours: Token expiration in hours
        actor_type: Actor type (user, api_key, service)

    Returns:
        JWT token string
    """
    now = datetime.now(timezone.utc)

    payload = {
        "sub": actor_id,  # Actor ID
        "tenant_id": tenant_id,  # Tenant for RLS
        "actor_type": actor_type,  # Actor type
        "scopes": scopes,  # Permissions
        "aud": audience,  # Audience
        "iss": issuer,  # Issuer
        "iat": now,  # Issued at
        "nbf": now,  # Not before
        "exp": now + timedelta(hours=expires_hours),  # Expires
    }

    # Get signing key
    if algorithm == "HS256":
        if not secret_key:
            raise ValueError("secret_key required for HS256")
        key = secret_key
    elif algorithm == "RS256":
        if not private_key_path:
            raise ValueError("private_key_path required for RS256")
        key = load_private_key(private_key_path)
    else:
        raise ValueError(f"Unsupported algorithm: {algorithm}")

    # Generate token
    token = jwt.encode(payload, key, algorithm=algorithm)

    return token


def verify_jwt(
    token: str, public_key: str = None, secret_key: str = None, algorithm: str = "HS256"
):
    """Verify and decode a JWT token (for testing).

    Args:
        token: JWT token string
        public_key: Public key for RS256 verification
        secret_key: Secret key for HS256 verification
        algorithm: JWT algorithm

    Returns:
        Decoded payload dict
    """
    if algorithm == "HS256":
        key = secret_key
    elif algorithm == "RS256":
        key = public_key
    else:
        raise ValueError(f"Unsupported algorithm: {algorithm}")

    payload = jwt.decode(
        token,
        key,
        algorithms=[algorithm],
        options={
            "verify_signature": True,
            "verify_exp": True,
            "verify_nbf": True,
            "verify_iat": True,
        },
    )

    return payload


def main():
    parser = argparse.ArgumentParser(description="Generate test JWT tokens for Active Graph KG")

    # Basic claims
    parser.add_argument("--tenant", default="test_tenant", help="Tenant ID")
    parser.add_argument("--actor", default="test_user", help="Actor ID (sub claim)")
    parser.add_argument("--actor-type", default="user", help="Actor type")
    parser.add_argument(
        "--scopes", default="search:read,nodes:write", help="Comma-separated scopes"
    )

    # JWT config
    parser.add_argument(
        "--algorithm", default="HS256", choices=["HS256", "RS256"], help="JWT algorithm"
    )
    parser.add_argument("--secret", help="Secret key for HS256 (or set JWT_SECRET_KEY env)")
    parser.add_argument("--private-key", help="Path to private key file for RS256")
    parser.add_argument("--public-key", help="Path to public key file for RS256 verification")

    parser.add_argument(
        "--audience", default=os.getenv("JWT_AUDIENCE", "activekg"), help="JWT audience"
    )
    parser.add_argument(
        "--issuer",
        default=os.getenv("JWT_ISSUER", "https://staging-auth.yourcompany.com"),
        help="JWT issuer",
    )
    parser.add_argument("--expires", type=int, default=24, help="Token expiration in hours")

    # Actions
    parser.add_argument("--verify", help="Verify an existing JWT token")

    args = parser.parse_args()

    # Verify mode
    if args.verify:
        try:
            if args.algorithm == "HS256":
                key = args.secret or input("Enter secret key: ")
                payload = verify_jwt(args.verify, secret_key=key, algorithm="HS256")
            else:
                if not args.public_key:
                    print("Error: --public-key required for RS256 verification")
                    sys.exit(1)
                public_key = load_private_key(args.public_key)
                payload = verify_jwt(args.verify, public_key=public_key, algorithm="RS256")

            print("✅ Token is valid!")
            print("\nDecoded payload:")
            import json

            print(json.dumps(payload, indent=2, default=str))

        except Exception as e:
            print(f"❌ Token verification failed: {e}")
            sys.exit(1)

        return

    # Generate mode
    scopes = args.scopes.split(",") if args.scopes else []

    # Get secret/private key
    if args.algorithm == "HS256":
        secret_key = args.secret
        if not secret_key:
            secret_key = os.getenv("JWT_SECRET_KEY")
        if not secret_key:
            print("Generating random secret key for HS256...")
            import secrets

            secret_key = secrets.token_urlsafe(32)
            print(f"\n⚠️  Using random secret: {secret_key}")
            print("Set this as JWT_SECRET_KEY in your environment\n")

        try:
            token = generate_jwt(
                tenant_id=args.tenant,
                actor_id=args.actor,
                scopes=scopes,
                algorithm=args.algorithm,
                secret_key=secret_key,
                audience=args.audience,
                issuer=args.issuer,
                expires_hours=args.expires,
                actor_type=args.actor_type,
            )

            print("✅ JWT Token Generated!")
            print("\n" + "=" * 80)
            print(token)
            print("=" * 80)
            print("\nClaims:")
            print(f"  Tenant ID: {args.tenant}")
            print(f"  Actor ID: {args.actor}")
            print(f"  Actor Type: {args.actor_type}")
            print(f"  Scopes: {', '.join(scopes)}")
            print(f"  Expires: {args.expires} hours")
            print("\nUsage:")
            print(f'  curl -H "Authorization: Bearer {token}" http://localhost:8000/ask')
            print("\nEnvironment:")
            print("  JWT_ENABLED=true")
            print(f"  JWT_SECRET_KEY={secret_key}")
            print("  JWT_ALGORITHM=HS256")
            print(f"  JWT_AUDIENCE={args.audience}")
            print(f"  JWT_ISSUER={args.issuer}")

        except Exception as e:
            print(f"Error generating token: {e}")
            sys.exit(1)

    elif args.algorithm == "RS256":
        if not args.private_key:
            print("Error: --private-key required for RS256")
            print("\nTo generate RS256 keypair:")
            print("  openssl genrsa -out private.pem 2048")
            print("  openssl rsa -in private.pem -pubout -out public.pem")
            sys.exit(1)

        try:
            token = generate_jwt(
                tenant_id=args.tenant,
                actor_id=args.actor,
                scopes=scopes,
                algorithm=args.algorithm,
                private_key_path=args.private_key,
                audience=args.audience,
                issuer=args.issuer,
                expires_hours=args.expires,
                actor_type=args.actor_type,
            )

            print("✅ JWT Token Generated (RS256)!")
            print("\n" + "=" * 80)
            print(token)
            print("=" * 80)
            print("\nClaims:")
            print(f"  Tenant ID: {args.tenant}")
            print(f"  Actor ID: {args.actor}")
            print(f"  Actor Type: {args.actor_type}")
            print(f"  Scopes: {', '.join(scopes)}")
            print(f"  Expires: {args.expires} hours")
            print("\nUsage:")
            print(f'  curl -H "Authorization: Bearer {token}" http://localhost:8000/ask')
            print("\nEnvironment (use public key):")
            print("  JWT_ENABLED=true")
            print('  JWT_SECRET_KEY="$(cat public.pem)"')
            print("  JWT_ALGORITHM=RS256")
            print(f"  JWT_AUDIENCE={args.audience}")
            print(f"  JWT_ISSUER={args.issuer}")

        except Exception as e:
            print(f"Error generating token: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
