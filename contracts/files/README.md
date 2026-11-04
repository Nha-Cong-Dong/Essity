# contracts/files: deploy order for CARDS-V3 (05/11)

`session-result.v2` and `submission-context.v1` are closed (`additionalProperties: false`) on both
sides, so a field one side writes and the other does not know fails the whole submission.

Read side first, write side after:

1. Deploy core-api first (it reads the optional `title` and `notice` and both `draft_key` forms),
   then ai-service (reads the optional `documents`; writes `title`, `notice` and the set `draft_key`).
   Or stop the ai worker, deploy core, start ai.
2. Only after the new ai-service runs, deploy the core-api that WRITES `documents` into the
   context (commit "core writes the outline of mentioned documents").

`draft_key` is the SHA-256 of `<session>:<quote_hash>` for one quote, or of
`<session>:<distinct quote hashes of all anchors, sorted, joined by ":">`; the first form is the
second for a single quote, so old and new results validate on both.
