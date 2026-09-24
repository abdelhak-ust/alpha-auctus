---
name: nexus-log
description: Record what was just implemented and verified into /IMPLEMENTATION_LOG.md, and mark the matching feature plan in /plans/ as done. Use after a feature or phase passes nexus-verify — this is how Nexus tracks what's actually been built, distinct from the forward-looking plans.
---

# nexus-log

## 1. Confirm it's actually done

Don't log something that hasn't been verified. If `nexus-verify` wasn't just run (and passed)
for this change, run it first. A log entry is a claim that this works, not a note-to-self.

## 2. Append an entry to `/IMPLEMENTATION_LOG.md`

Newest entry at the **top**, directly under the file's header (this is a log, read
newest-first). Follow the exact structure of the existing entries:

```markdown
## <YYYY-MM-DD> — <short title>

**What:** one paragraph — what changed and, if it's not obvious, why.

**Files:** the files that actually changed (new files marked "(new)"), not every file touched
in passing.

**Verified:** the concrete checks that passed — command + result (`pytest` N/N, `tsc --noEmit`
clean, a specific manual check), not just "tested."

**Open:** anything left unfinished, deferred, or that needs the user's input — omit this
line entirely if there's genuinely nothing open.

**Commit:** the commit hash(es), once committed.
```

Be honest and specific — an inflated or vague entry defeats the point. If something was
attempted and didn't fully work, say so (see the 2026-09-24 entry's "Open" section for the
pattern: report a real blocker plainly, don't bury it).

## 3. Close the loop with `/plans/`

If this feature has a plan file in `/plans/<slug>.md` (check `status: active` frontmatter),
update it:
- `status: done`
- `completed: <today's date>`
- A one-line completion note at the bottom of the file, linking to the new log entry.

This is what lets `nexus-plan` allow the next feature to start (its one-active-at-a-time check
looks for exactly this).

## 4. If nothing in `/plans/` matches

Not every logged change comes from a planned feature (a bug fix, a small foundational change
like this session's GCP setup). That's fine — just log it; there's no plan file to close.
