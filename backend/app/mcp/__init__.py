"""MCP server — the agent's two-way interface into Nexus (Alpha Auctus).

Exposes list_tasks/get_task, claim_task, ask_clarification, log_decision,
update_progress, submit_for_verification. claim_task enforces the autonomy
level and permission rules (allowed repos/files) from the unified registry.
Phase P3 in the plan.
"""
