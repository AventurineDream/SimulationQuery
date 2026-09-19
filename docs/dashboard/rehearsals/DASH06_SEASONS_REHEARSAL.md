# DASH-06 — Seasons / Private Close / Publication rehearsal

**Status:** implemented and locally verified on 2026-08-27; creator walkthrough pending.

**Scope:** disposable S02 only. This is not an authorization to close S01,
deploy, restart a worker, run a model, or release public work.

## What the operator can verify

1. Open **Seasons** with synthetic S02 selected. Opening or refreshing it must
   only read the versioned close snapshot.
2. Confirm the snapshot shows lifecycle, version, accepted records, archive
   reachability, integrity, outbox status, and unresolved runs/diaries without
   private filesystem paths.
3. Open **Review private close**. It states what will happen and what will not.
   Nothing happens until the exact phrase `end S02 privately` is entered.
4. After the close receipt, confirm `PRIVATE_COMPLETE`, a verified handoff, and
   the still-visible unresolved work. The action must not publish, delete,
   rewrite, or clear private evidence.
5. Review the now-separate publication screen. It starts only from
   `PRIVATE_COMPLETE`, shows the closure receipt and pending-call eligibility,
   and defaults every diary to private.
6. Clear only a written or late diary, update the exact preview, then open the
   publication impact review. The command requires `publish S02` plus the three
   wellness/privacy/consent confirmations.
7. Confirm the receipt identifies the immutable projection and reports the same
   private archive hash as before publication.

## Expected safe failures

- a stale snapshot or season version;
- a wrong typed phrase or reused request ID with changed intent;
- private close with an active lease;
- publication before `PRIVATE_COMPLETE`;
- publication while model calls remain pending;
- clearing a held/missing diary or a diary outside the private archive;
- missing wellness, privacy, or consent confirmation.

## Local evidence

- `154 passed` via `./.venv/bin/python -m pytest -q`;
- JavaScript syntax, Python compilation, and whitespace checks pass;
- unit and route coverage exercise replay, stale review, S01/production
  rejection, exact allowlisting, and the private-archive hash guard.

The creator’s walkthrough is the remaining acceptance gate. It should use a
fresh temporary S02 root and must not be treated as evidence about S01 or a
real public release.
