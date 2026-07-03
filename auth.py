import hashlib
import secrets


def hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def make_salt() -> str:
    return secrets.token_hex(8)


def encode_password(password: str) -> str:
    """Zwraca string 'salt$hash' do zapisu w bazie."""
    salt = make_salt()
    return f"{salt}${hash_password(password, salt)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, hashed = stored.split("$", 1)
    except ValueError:
        return False
    return hash_password(password, salt) == hashed
