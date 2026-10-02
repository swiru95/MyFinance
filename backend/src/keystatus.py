"""`python -m src.keystatus`: how far a KEK rotation has got.

Rotation is lazy: adding a KEK version changes nothing for existing users until
each of them next signs in, at which point their data key is wrapped again under
the new current version (services/users._rewrap). This reports, per KEK version,
how many users are still on it, so the old one is only dropped from the Secret
once the count behind is zero. Users who have never signed in since the
encryption migration (no key yet) are listed apart.

Run it with the *owner's* database credentials (the same as the schema job): as
the runtime role, row-level security hides every other user, and the counts
would be wrong. It refuses to report in that case rather than print them.

Exit status: 0 normally; 1 with --fail-on-behind when any user is behind the
current version (for a pipeline that gates removing the old KEK on it); 2 when it
cannot give a meaningful answer.
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import text

from . import rls
from .crypto.core import KekError, active_keks
from .database import engine
from .services import keys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report how many users are on each KEK version.")
    parser.add_argument("--fail-on-behind", action="store_true", help="exit 1 if any user is behind")
    args = parser.parse_args(argv)
    try:
        active_keks()
    except KekError as exc:
        print(f"keystatus: {exc}", file=sys.stderr)
        return 2
    with engine.connect() as conn:
        if engine.dialect.name == "postgresql" and not rls.runtime_role_problems(conn) and conn.execute(
            text("SELECT relrowsecurity FROM pg_class WHERE oid = to_regclass('public.users')")
        ).scalar():
            print(
                "keystatus: this database role is subject to row-level security and would see only "
                "its own row; run it with the owner's credentials",
                file=sys.stderr,
            )
            return 2
        report = keys.version_report(conn)
    print(f"current KEK version: {report['current']}   configured: {report['configured']}")
    print(f"users: {report['total']}")
    for version, count in report["by_version"].items():
        marker = "current" if version == report["current"] else "BEHIND"
        print(f"  KEK v{version}: {count} user(s)  [{marker}]")
    if report["keyless"]:
        print(f"  no key yet: {report['keyless']} user(s) (never signed in since the encryption migration)")
    print(f"behind the current version: {report['behind']}")
    if report["behind"] == 0 and report["by_version"]:
        print("every user with a key is on the current version; older KEKs can be retired")
    return 1 if (args.fail_on_behind and report["behind"]) else 0


if __name__ == "__main__":
    sys.exit(main())
