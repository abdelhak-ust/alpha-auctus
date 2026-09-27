"""GitHub App — PR create/read, CI/build/deploy webhooks.

Links PRs to tasks (branch naming / task id), and re-runs requirement
validation on every push so coverage travels with the PR (delta shown, e.g.
5/7 -> 7/7) with regression detection. Human-only merge/deploy (L0-L1 per
the session's decision). Phase P4 in the plan.
"""
