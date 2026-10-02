"""What a restart tells a job it interrupted.

The startup sweep (services/llm_queue.py, and its SQL twin in rls.py) changes a
job's status without being able to decrypt anything, so it cannot write the
`error` text, which is encrypted. It sets a code in the plaintext `status_note`
column instead, and `error` reads it back as this text when the job has no error
of its own.
"""
from __future__ import annotations

INTERRUPTED = "interrupted"
KEY_EXPIRED = "key_expired"
TRANSLATION_INTERRUPTED = "translation_interrupted"

INTERRUPTED_NOTE = "Interrupted by a server restart - generate again."
TRANSLATION_INTERRUPTED_NOTE = "Translation was interrupted by a server restart; showing English."

KEY_EXPIRED_NOTE = (
    "The job waited so long that its encryption key expired before it could run - generate again."
)

NOTE_TEXT = {
    KEY_EXPIRED: KEY_EXPIRED_NOTE,
    INTERRUPTED: INTERRUPTED_NOTE,
    TRANSLATION_INTERRUPTED: TRANSLATION_INTERRUPTED_NOTE,
}
