---
type: reference
title: CLI image ID streaming
---

# CLI image ID streaming

`images search` with `emit_ids=true` keeps the existing ID item/result JSONL contract,
input ordering for exact sets, sort behavior, and 100,000-ID output ceiling. Ordinary
metadata search is unchanged. Bulk ID output continues to ignore query offset/limit.

For ordinary SQL filters, one count query precedes one ID-only SELECT cursor. Python
consumes at most 500 IDs per page; output metadata and annotations are not loaded.
Existing filter setup may look up model rows (for example NSFW/manual filters), but
is performed once per operation rather than once per page. No permanent cache is used.

The count is sampled before opening the cursor. The session does not promise a
database-wide snapshot between those two statements: concurrent writes can make
observed total differ from emitted count. Pages share one cursor, avoiding repeated
OFFSET query drift. `truncated` remains `emitted < total` and reports incomplete
output under that existing contract, including the 100,000 ceiling.

Exact sets retain their 500-unique-ID input ceiling, preserve first-occurrence order,
and bypass other filters except processed resolution, as ordinary exact-set lookup does.

Score ranges retain the existing representative-score calculation (manual priority,
otherwise calibrated AI aggregation). Candidate IDs and matched IDs are retained for
this post-filter; **there is no candidate-count bound** before the 100,000 output cap.
Image/score/model records are loaded in existing 500-ID batches. This work runs once
per output operation, not once for count plus each page. Thus score filtering has
O(candidate IDs) ID memory and extra score/model reads; it does not claim the ordinary
SQL path's ID-only memory or zero annotation reads. Large score-filter redesign is
outside this change.
