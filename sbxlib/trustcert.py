"""Trust the mkcert CA of the machine that made the sandboxes.

`sbx new` signs each sandbox's certificate with the mkcert CA of the machine
that made it. A second machine has another CA, so its browser warns. Trusting
the sandbox's leaf alone does not work (Chromium and OpenSSL want the CA), and
the sandbox holds the leaf only. So the CA's PUBLIC certificate comes from a
file or from 1Password, and the leaf serves to check that it is the right CA.
The CA key stays on the machine that made it.
"""
from __future__ import annotations

import re
import shutil
import sys
import tempfile
from pathlib import Path

from .run import CommandError, Runner

REMOTE_CERT = "/etc/sbx/tls/cert.pem"
PEM = re.compile(r"-----BEGIN CERTIFICATE-----[A-Za-z0-9+/=\s]+-----END CERTIFICATE-----")

# (anchor directory, command that rebuilds the store) for each Linux family.
LINUX_STORES = (
    (Path("/etc/ca-certificates/trust-source/anchors"), ["update-ca-trust"]),   # Arch
    (Path("/etc/pki/ca-trust/source/anchors"), ["update-ca-trust"]),         # Fedora
    (Path("/usr/local/share/ca-certificates"), ["update-ca-certificates"]),     # Debian, Ubuntu
)


class TrustError(RuntimeError):
    pass


def parse(text: str) -> str:
    """The first certificate in `text`, as PEM, or a TrustError."""
    found = PEM.search(text)
    if not found:
        raise TrustError("no certificate found: a sandbox without one serves http:// only")
    return found.group(0).strip() + "\n"


def nss_db() -> Path:
    """Chromium and Firefox-less Linux browsers read this database."""
    return Path.home() / ".pki" / "nssdb"


CA_NAME = "sbx-mkcert-ca"


def verify(runner: Runner, ca: str, leaf: str) -> bool:
    """Whether `ca` signed `leaf`."""
    with tempfile.TemporaryDirectory() as d:
        ca_path, leaf_path = Path(d, "ca.pem"), Path(d, "leaf.pem")
        ca_path.write_text(ca)
        leaf_path.write_text(leaf)
        return runner.run(["openssl", "verify", "-CAfile", str(ca_path), str(leaf_path)], check=False).code == 0


def install(runner: Runner, name: str, pem: str, *, platform: str = sys.platform) -> list[str]:
    """Trust `pem` as `name`. Returns a line for each store that was changed."""
    done: list[str] = []
    if platform == "darwin":
        with tempfile.NamedTemporaryFile("w", suffix=".pem") as f:
            f.write(pem)
            f.flush()
            runner.run(["sudo", "security", "add-trusted-cert", "-d", "-r", "trustRoot",
                        "-k", "/Library/Keychains/System.keychain", f.name], capture=False)
        return ["the macOS System keychain"]
    store = next(((d, cmd) for d, cmd in LINUX_STORES if d.is_dir()), None)
    if store is None:
        raise TrustError("no system trust store found (update-ca-trust or update-ca-certificates)")
    anchors, rebuild = store
    target = anchors / f"{name}.crt"
    runner.run(["sudo", "install", "-D", "-m", "0644", "/dev/stdin", str(target)], input=pem.encode(), capture=False)
    runner.run(["sudo", *rebuild], capture=False)
    done.append(f"the system store ({target})")
    # Chromium keeps its own database, so the system store is not enough.
    if shutil.which("certutil"):
        db = nss_db()
        url = f"sql:{db}"
        if not db.exists():
            db.mkdir(parents=True, mode=0o700)
            runner.run(["certutil", "-d", url, "-N", "--empty-password"])
        runner.run(["certutil", "-d", url, "-D", "-n", name], check=False)  # a renewed certificate replaces the old one
        with tempfile.NamedTemporaryFile("w", suffix=".pem") as f:
            f.write(pem)
            f.flush()
            runner.run(["certutil", "-d", url, "-A", "-t", "C,,", "-n", name, "-i", f.name])
        done.append(f"the browser database ({db})")
    return done


def fetch(vm) -> str:
    try:
        return parse(vm.run(f"cat {REMOTE_CERT}").stdout)
    except CommandError:
        raise TrustError("the sandbox has no certificate: it serves http:// only") from None
