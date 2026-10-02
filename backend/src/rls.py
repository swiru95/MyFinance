"""PostgreSQL row-level security: the database's own copy of "a user sees only
their rows", underneath the filtering the ORM already does (scoping.py).

How it fits together
--------------------
* Every user-owned table has `ENABLE` and `FORCE ROW LEVEL SECURITY` and one
  policy, `myfinance_user_isolation`, for every command:

      USING / WITH CHECK  (user_id = NULLIF(current_setting('myfinance.user_id', true), '')::uuid)

  The variable is set by scoping.py at the start of every transaction
  (`set_config(..., true)`, i.e. `SET LOCAL`), from the session's own
  `info["user_id"]`. `current_setting(..., true)` returns NULL when it was never
  set and '' once a transaction that set it has ended; `NULLIF` turns both into
  NULL, and `user_id = NULL` is never true. So a connection with no variable
  sees nothing and cannot write anything - it does not error, and it never falls
  back to "everything".

* The application connects as a *runtime* role that is not the table owner, has
  no BYPASSRLS and is not a superuser. Nothing it can do touches another user's
  row, whatever SQL it sends.

* Work that really is cross-user has the narrowest door that does the job, as a
  SECURITY DEFINER function owned by the owning role, executable by the runtime
  role and nobody else (`PUBLIC` is revoked):

    myfinance_get_or_create_user(hash, id, key material)   find a person, or add them
    myfinance_sweep_interrupted_jobs()                      the startup sweep (status only)
    myfinance_recovery_lookup(recovery_id)                  the wrapped key a recovery code opens
    myfinance_recover_account(recovery_id, proof, ...)      re-attach old data to a new identity
    myfinance_contact_unsubscribe(token_hash)               the unauthenticated unsubscribe link

  Everything else the runtime role does, it does as one user.

The owner
---------
FORCE makes the *owner* subject to the policies too; without it the owner would
see everything implicitly. The owner does still have to work across users - the
schema job's backfills, and the two functions above, which run as it - so it is
admitted by a second, explicitly named policy, `myfinance_owner_access`
(`TO <owner role>`, `USING (true)`). The difference from leaving FORCE off is
that nothing is admitted by accident: the one door is visible in `pg_policies`,
is bound to a named role, and disappears if the policy is dropped. It is also
why this works for an owner that is not a superuser and cannot be granted
BYPASSRLS (only a superuser can). It does mean the application must never
connect as the owner, or as a member of it; `check_runtime_role` refuses to start
if it does.

The users table
---------------
`users` has RLS too. It holds no personal data, but it is the list of every
account, and without a policy the runtime role could read all of it and could
create, rename or delete accounts. With it, the runtime role sees and updates
only the caller's own row, only the two terms-acceptance columns are updatable
(column privilege, see schema.grant_runtime_role) and it cannot insert or delete
at all - accounts are created through the function above.

What RLS does not cover
-----------------------
Foreign keys and unique constraints are checked with RLS bypassed, so a row
could still *reference* another user's parent. That is what the composite
foreign keys (user_id, parent_id) are for - see schema.migrate_integrity.
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

log = logging.getLogger(__name__)

# The custom setting that carries the current user's id. Any `prefix.name` is a
# legal user-defined setting without server configuration.
GUC = "myfinance.user_id"

ISOLATION_POLICY = "myfinance_user_isolation"
OWNER_POLICY = "myfinance_owner_access"
USERS_SELECT_POLICY = "myfinance_own_row_select"
USERS_UPDATE_POLICY = "myfinance_own_row_update"

GET_OR_CREATE_USER = "myfinance_get_or_create_user"
SWEEP_JOBS = "myfinance_sweep_interrupted_jobs"
RECOVERY_LOOKUP = "myfinance_recovery_lookup"
RECOVER_ACCOUNT = "myfinance_recover_account"
CONTACT_UNSUBSCRIBE = "myfinance_contact_unsubscribe"
# (name, argument types) of every function the runtime role may execute.
FUNCTIONS = [
    (GET_OR_CREATE_USER, "text, uuid, bytea, bytea, integer"),
    (SWEEP_JOBS, ""),
    (RECOVERY_LOOKUP, "text"),
    (RECOVER_ACCOUNT, "text, bytea, bytea, bytea, integer"),
    (CONTACT_UNSUBSCRIBE, "bytea"),
]
# Earlier signatures of the functions above, dropped when the new ones go in so
# an old overload does not linger with the runtime role's EXECUTE on it.
SUPERSEDED = [
    (GET_OR_CREATE_USER, "text, uuid"),
]

# Tables whose rows a first sign-in creates by itself (the default asset types,
# the settings a visit may write): they do not make an account "not empty" when
# a recovery code is used on it, and are deleted with it.
DISPOSABLE_TABLES = ("assets", "settings", "user_contacts")

_CURRENT_USER = f"NULLIF(current_setting('{GUC}', true), '')::uuid"


class RowSecurityError(RuntimeError):
    """Row-level security cannot be applied, or is not effective, as configured."""


def _quote(conn: Connection, name: str) -> str:
    return conn.dialect.identifier_preparer.quote(name)


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


# --- functions ------------------------------------------------------------


def _function_sql(owned_tables: list[str]) -> list[str]:
    # Imported here: jobnotes' codes are the one source of truth for what the
    # sweep writes, and this module must not import models at load time.
    from .models.jobnotes import INTERRUPTED, TRANSLATION_INTERRUPTED

    def sweep(table: str) -> str:
        # Status and a note *code* only. The text a user reads (jobnotes.NOTE_TEXT)
        # is looked up from the code on the way out, because `error` itself is
        # encrypted and this function, which holds no key, cannot write it. A
        # job in 'translating' always has its English text stored already (the
        # job commits it before it sets that status), so it cannot be told from
        # a finished one by looking at the content - nor does it need to be.
        return f"""
    UPDATE public.{table}
       SET status = CASE WHEN status = 'translating' THEN 'done' ELSE 'failed' END,
           status_note = CASE WHEN status = 'translating'
                              THEN {_literal(TRANSLATION_INTERRUPTED)}
                              ELSE {_literal(INTERRUPTED)} END
     WHERE status IN ('pending', 'running', 'translating');"""

    not_empty = " OR ".join(
        f"EXISTS (SELECT 1 FROM public.{t} WHERE user_id = v_new)"
        for t in owned_tables
        if t not in DISPOSABLE_TABLES
    ) or "false"
    disposable = "\n    ".join(
        f"DELETE FROM public.{t} WHERE user_id = v_new;" for t in DISPOSABLE_TABLES if t in owned_tables
    )

    reports_sql, insights_sql = sweep("reports"), sweep("insights")
    return [
        # Find or add a person by the keyed hash of their identity. The one
        # place the application has to look across users, because it does not
        # yet know which user it is dealing with. It reveals an id only to a
        # caller who already holds the hash (which needs the server-side
        # pepper), and it can only ever add a row, never change or read others.
        f"""
CREATE OR REPLACE FUNCTION public.{GET_OR_CREATE_USER}(
    p_subject_hash text, p_id uuid, p_salt bytea, p_wrapped bytea, p_kek_version integer)
RETURNS TABLE (out_user_id uuid, out_created boolean, out_salt bytea, out_wrapped bytea, out_kek_version integer)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
    v_id uuid;
BEGIN
    IF p_subject_hash IS NULL OR p_subject_hash !~ '^[0-9a-f]{{64}}$' THEN
        RAISE EXCEPTION 'subject hash must be 64 lower-case hex characters' USING ERRCODE = '22023';
    END IF;
    SELECT u.id INTO v_id FROM public.users u WHERE u.subject_hash = p_subject_hash;
    IF v_id IS NOT NULL THEN
        RETURN QUERY SELECT u.id, false, u.key_salt, u.wrapped_dek, u.kek_version
                       FROM public.users u WHERE u.id = v_id;
        RETURN;
    END IF;
    -- Two first requests from one person can arrive together. The loser waits
    -- for the winner's transaction (which also provisions their assets), does
    -- nothing, and then finds the row - and the winner's wrapped key, which is
    -- the one that matters: the loser's own candidate key is discarded.
    INSERT INTO public.users (id, subject_hash, created_at, key_salt, wrapped_dek, kek_version)
    VALUES (p_id, p_subject_hash, now() AT TIME ZONE 'utc', p_salt, p_wrapped, p_kek_version)
    ON CONFLICT (subject_hash) DO NOTHING
    RETURNING id INTO v_id;
    IF v_id IS NOT NULL THEN
        RETURN QUERY SELECT v_id, true, p_salt, p_wrapped, p_kek_version;
        RETURN;
    END IF;
    RETURN QUERY SELECT u.id, false, u.key_salt, u.wrapped_dek, u.kek_version
                   FROM public.users u WHERE u.subject_hash = p_subject_hash;
END
$fn$""",
        # Startup: a crash or restart left jobs in a state that will never
        # finish. Changes status and error only; reads no report content and
        # returns counts.
        f"""
CREATE OR REPLACE FUNCTION public.{SWEEP_JOBS}()
RETURNS TABLE (out_reports integer, out_insights integer)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
    v_reports integer;
    v_insights integer;
BEGIN
    {reports_sql}
    GET DIAGNOSTICS v_reports = ROW_COUNT;
    {insights_sql}
    GET DIAGNOSTICS v_insights = ROW_COUNT;
    RETURN QUERY SELECT v_reports, v_insights;
END
$fn$""",
        # A recovery code's lookup half names an account; this hands back the
        # wrapped key that the code's secret half can open, and the scrypt
        # parameters. Useless without the code, and the id is 80 random bits.
        f"""
CREATE OR REPLACE FUNCTION public.{RECOVERY_LOOKUP}(p_recovery_id text)
RETURNS TABLE (out_user_id uuid, out_salt bytea, out_kdf text, out_wrapped bytea)
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
    SELECT u.id, u.recovery_salt, u.recovery_kdf, u.recovery_wrapped_dek
      FROM public.users u
     WHERE u.recovery_id = p_recovery_id AND u.recovery_wrapped_dek IS NOT NULL
$fn$""",
        # Re-attach an old account's data to the caller's identity. The caller is
        # whoever the session says it is (the same variable the policies use), so
        # this can only ever delete *the caller's own* empty account, never a
        # named one. The proof is checked against the stored verifier here, in the
        # database, so a runtime role that was talked into calling this without a
        # valid recovery code moves nothing.
        f"""
CREATE OR REPLACE FUNCTION public.{RECOVER_ACCOUNT}(
    p_recovery_id text, p_proof bytea, p_new_salt bytea, p_new_wrapped bytea, p_new_kek_version integer)
RETURNS TABLE (out_status text, out_user_id uuid)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
    v_new uuid := NULLIF(current_setting('{GUC}', true), '')::uuid;
    v_old uuid;
    v_verifier bytea;
    v_new_hash text;
BEGIN
    IF v_new IS NULL THEN
        RETURN QUERY SELECT 'denied'::text, NULL::uuid;
        RETURN;
    END IF;
    SELECT u.id, u.recovery_verifier INTO v_old, v_verifier
      FROM public.users u WHERE u.recovery_id = p_recovery_id;
    IF v_old IS NULL OR v_verifier IS NULL OR p_proof IS NULL OR v_verifier <> sha256(p_proof) THEN
        RETURN QUERY SELECT 'denied'::text, NULL::uuid;
        RETURN;
    END IF;
    IF v_old = v_new THEN
        UPDATE public.users
           SET key_salt = p_new_salt, wrapped_dek = p_new_wrapped, kek_version = p_new_kek_version,
               recovery_failures = 0, recovery_locked_until = NULL
         WHERE id = v_old;
        RETURN QUERY SELECT 'rewrapped'::text, v_old;
        RETURN;
    END IF;
    IF {not_empty} THEN
        RETURN QUERY SELECT 'not_empty'::text, v_old;
        RETURN;
    END IF;
    SELECT u.subject_hash INTO v_new_hash FROM public.users u WHERE u.id = v_new;
    {disposable}
    DELETE FROM public.users WHERE id = v_new;
    UPDATE public.users
       SET subject_hash = v_new_hash, key_salt = p_new_salt, wrapped_dek = p_new_wrapped,
           kek_version = p_new_kek_version, recovery_failures = 0, recovery_locked_until = NULL
     WHERE id = v_old;
    RETURN QUERY SELECT 'recovered'::text, v_old;
END
$fn$""",
        # The unsubscribe link carries a token; whoever clicks it is not signed
        # in, so this is the one write the runtime role makes with no user. It
        # sets one flag and erases the address, for the row the token's hash names.
        f"""
CREATE OR REPLACE FUNCTION public.{CONTACT_UNSUBSCRIBE}(p_token_hash bytea)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
    v_rows integer;
BEGIN
    IF p_token_hash IS NULL THEN
        RETURN 0;
    END IF;
    UPDATE public.user_contacts
       SET notify_opt_in = false, email = NULL, updated_at = now() AT TIME ZONE 'utc'
     WHERE unsubscribe_token_hash = p_token_hash;
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RETURN v_rows;
END
$fn$""",
    ]


def function_signatures() -> list[str]:
    return [f"public.{name}({args})" for name, args in FUNCTIONS]


# --- applying -------------------------------------------------------------


def _owner_of(conn: Connection, table: str) -> str:
    return conn.execute(
        text("SELECT pg_get_userbyid(c.relowner) FROM pg_class c WHERE c.oid = to_regclass(:t)"),
        {"t": f"public.{_quote(conn, table)}"},
    ).scalar_one()


def apply(conn: Connection, owned_tables: list[str]) -> None:
    """Enable and force RLS on every owned table and on `users`, install the
    policies and the functions. Idempotent; run as the role that owns the
    tables, in the caller's transaction.
    """
    me = conn.execute(text("SELECT current_user")).scalar_one()
    for table in [*owned_tables, "users"]:
        owner = _owner_of(conn, table)
        if owner != me:
            raise RowSecurityError(
                f"table {table} is owned by {owner}, but this job runs as {me}: "
                "row-level security has to be applied by the owning role"
            )
    owner_q = _quote(conn, me)

    def policy(table: str, name: str, command: str, using: str, check: str | None, to: str = "PUBLIC") -> None:
        t = _quote(conn, table)
        conn.execute(text(f"DROP POLICY IF EXISTS {name} ON {t}"))
        sql = f"CREATE POLICY {name} ON {t} AS PERMISSIVE FOR {command} TO {to} USING ({using})"
        if check is not None:
            sql += f" WITH CHECK ({check})"
        conn.execute(text(sql))

    for table in owned_tables:
        t = _quote(conn, table)
        conn.execute(text(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY"))
        conn.execute(text(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY"))
        same = f"user_id = {_CURRENT_USER}"
        policy(table, ISOLATION_POLICY, "ALL", same, same)
        policy(table, OWNER_POLICY, "ALL", "true", "true", to=owner_q)

    conn.execute(text("ALTER TABLE users ENABLE ROW LEVEL SECURITY"))
    conn.execute(text("ALTER TABLE users FORCE ROW LEVEL SECURITY"))
    own = f"id = {_CURRENT_USER}"
    policy("users", USERS_SELECT_POLICY, "SELECT", own, None)
    policy("users", USERS_UPDATE_POLICY, "UPDATE", own, own)
    policy("users", OWNER_POLICY, "ALL", "true", "true", to=owner_q)

    for name, args in SUPERSEDED:
        conn.execute(text(f"DROP FUNCTION IF EXISTS public.{name}({args})"))
    for sql in _function_sql(owned_tables):
        conn.execute(text(sql))
    for sig in function_signatures():
        # Functions are executable by PUBLIC unless told otherwise.
        conn.execute(text(f"REVOKE ALL ON FUNCTION {sig} FROM PUBLIC"))


def grant_functions(conn: Connection, role: str) -> None:
    for sig in function_signatures():
        conn.execute(text(f"GRANT EXECUTE ON FUNCTION {sig} TO {_quote(conn, role)}"))


# --- checking the runtime role ---------------------------------------------


def runtime_role_problems(conn: Connection) -> list[str]:
    """Why the role this connection is logged in as would ignore the policies.

    Empty when row-level security is not installed (nothing to ignore) or when
    the role is subject to it.
    """
    state = conn.execute(
        text(
            "SELECT c.relrowsecurity, c.relforcerowsecurity, r.rolsuper, r.rolbypassrls, "
            "       pg_has_role(current_user, c.relowner, 'USAGE') "
            "FROM pg_class c, pg_roles r "
            "WHERE c.oid = to_regclass('public.users') AND r.rolname = current_user"
        )
    ).first()
    if state is None or not state[0]:
        return []
    _, forced, superuser, bypass, owner_or_member = state
    problems = []
    if superuser:
        problems.append("it is a superuser")
    if bypass:
        problems.append("it has BYPASSRLS")
    if owner_or_member:
        problems.append("it is the table owner (or a member of that role)")
    if not forced:
        problems.append("FORCE ROW LEVEL SECURITY is off on users")
    return problems


def check_runtime_role(eng: Engine) -> None:
    """Refuse to serve when the connection role would walk straight past the
    policies. A silent no-op is the failure to avoid: everything would work and
    nothing would be protected."""
    if eng.dialect.name != "postgresql":
        return
    with eng.connect() as conn:
        problems = runtime_role_problems(conn)
        role = conn.execute(text("SELECT current_user")).scalar_one()
    if problems:
        raise RowSecurityError(
            f"database role {role!r} is not subject to row-level security: "
            + "; ".join(problems)
            + ". Connect the application as the runtime role (no DDL, no BYPASSRLS), "
            "not as the owner; or set MYFINANCE_RLS_ROLE_CHECK=false to run anyway."
        )
