# Backend TODOs

## 1. Manual chapter-number override on a reference

The user has no way to correct a wrong/missing `chapter_number` on a reference.
Need a write endpoint + storage setter.

**Contract:** `PATCH /api/references/{refId}` with `{ chapter_number: number | null }` →
updated `ReferenceChapter` (200), 404 if missing. Accept `null` to clear a bad auto-parse.

**Frontend:** add `api.setReferenceChapterNumber(refId, n)` to the client, then inline
edit on the `Ch N` / "No chapter number" marker in `references-tab.tsx`.
