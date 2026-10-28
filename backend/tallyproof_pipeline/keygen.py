"""Generate checkpoint signing keys.

Keys come in classes with different homes (see docs/threat-model.md):

- ``dev``: local development checkpoints.
- ``rel``: the public demo bundle. Generated and kept offline on the maintainer's
  machine; its public key is what the web build pins.

Private keys are written to ``secrets/`` (ignored by git, and blocked by the
secret scanner if anyone tries to commit one) with owner-only permissions. The
public verifier key is printed so it can be published.

Usage::

    python -m tallyproof_pipeline.keygen dev
"""

import argparse
import os
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tallyproof_core.checkpoint import Signer, decode_private_key, encode_private_key
from tallyproof_pipeline.settings import REPO_ROOT

KEY_CLASSES = ("dev", "rel")
KEY_NAMES = {"dev": "dev.tallyproof.dev/log/v1", "rel": "tallyproof.dev/log/v1"}


def key_path(key_class: str, secrets_dir: Path = REPO_ROOT / "secrets") -> Path:
    """Where the private key of a class is stored."""
    return secrets_dir / f"checkpoint_{key_class}.key"


def generate(key_class: str, secrets_dir: Path = REPO_ROOT / "secrets") -> Signer:
    """Create a key for a class, refusing to overwrite an existing one.

    Raises:
        FileExistsError: If the class already has a key. Rotating a key is a
            deliberate act, so the old file must be moved away by hand.
        ValueError: If the class is unknown.
    """
    if key_class not in KEY_CLASSES:
        raise ValueError(f"unknown key class {key_class!r}; expected one of {KEY_CLASSES}")
    path = key_path(key_class, secrets_dir)
    if path.exists():
        raise FileExistsError(f"{path} already exists; move it away first to rotate the key")
    secrets_dir.mkdir(parents=True, exist_ok=True)
    private_key = Ed25519PrivateKey.generate()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(encode_private_key(private_key) + "\n")
    return Signer(KEY_NAMES[key_class], private_key)


def load(key_class: str, secrets_dir: Path = REPO_ROOT / "secrets") -> Signer:
    """Load the signer for a key class."""
    private_key = decode_private_key(key_path(key_class, secrets_dir).read_text())
    return Signer(KEY_NAMES[key_class], private_key)


def main() -> None:  # pragma: no cover - thin command-line wrapper
    """Generate a key and print its public verifier key."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("key_class", choices=KEY_CLASSES)
    signer = generate(parser.parse_args().key_class)
    print(f"Public verifier key: {signer.verifier_key()}")


if __name__ == "__main__":  # pragma: no cover
    main()
