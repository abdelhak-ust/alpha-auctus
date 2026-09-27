"""WebSocket manager — live verdicts + live agent-run activity.

Pushes verdict results (task conflict/dedup) and Run activity/AC-tracker
events to connected clients, per architecture.md ("REST/GraphQL + websocket
(live verdicts)") and ui_ux_design.md §14. Built out in P3 alongside Runs.
"""
