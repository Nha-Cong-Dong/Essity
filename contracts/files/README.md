# contracts/files: deploy order for CARDS-V3 (05/11)

`session-result.v2` and `submission-context.v1` are closed (`additionalProperties: false`) on both
sides, and this branch is ONE build of core-api that reads and writes the new fields (core writes
`documents` into the context; ai-service writes `title`, `notice` and the set `draft_key`). An old
service refuses what the new one writes, and that submission fails for good. So there is one way
to deploy, with the ai worker stopped while the two services differ:

1. Back up the database (ADR-0012).
2. Stop the ai-service worker.
3. Deploy core-api and run its migration 0038.
4. Deploy ai-service and run its migration 0012.
5. Start the ai-service worker.
6. Move the cards that waited for review: `python -m core_api.cli promote-drafts --dry-run`, then
   without `--dry-run`.

Messages already queued when the worker stops are read by the new ai-service. A context written
before the new core has no `documents`, which the new ai-service reads as none.

`draft_key` is the SHA-256 of `<session>:<quote_hash>` for one quote, or of
`<session>:<distinct quote hashes of all anchors, sorted, joined by ":">`; the first form is the
second for a single quote, so old and new results validate on both.
