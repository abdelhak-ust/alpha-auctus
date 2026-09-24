"""Agent execution runner + sandbox — Claude Code, MVP single-agent-per-task.

Runs an agent against a repo in an isolated sandbox (git worktree/container
per run), streams activity (read/edit/run/note/block) over ws/, and handles
the ask_clarification blocking round-trip. Phase P3 in the plan, alongside mcp/.
"""
