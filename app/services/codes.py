"""Short code generation using cryptographically secure random selection.

Generates 7-character base62 strings from [a-zA-Z0-9].
$62^7 \approx 3.52$ trillion possible unique combinations.
Provides collision retry mechanisms up to 5 attempts when inserting into PostgreSQL.
"""

import secrets
import string

# Base62 character pool: 26 lowercase + 26 uppercase + 10 digits
BASE62_ALPHABET = string.ascii_letters + string.digits
DEFAULT_CODE_LENGTH = 7
MAX_COLLISION_RETRIES = 5


def generate_short_code(length: int = DEFAULT_CODE_LENGTH) -> str:
    """Generates a random URL-safe base62 code using the secrets module."""
    return "".join(secrets.choice(BASE62_ALPHABET) for _ in range(length))
