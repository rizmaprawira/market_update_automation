# RIU Market Update Agent Instructions

This package contains operational instruction files for the RIU Market Update automation company in Paperclip.

## Folder structure

Each agent has:

- `agent.md` - role, responsibilities, scope, input/output contract, handoff rules.
- `soul.md` - personality, working style, behavioral defaults.
- `heartbeat.md` - checklist the agent should run every time it receives or resumes a task.
- `tools.md` - allowed files, folders, scripts, and forbidden actions.

The Director also has:

- `routing.md` - routing rules, workflow stages, delegation rules, and escalation logic.

## Recommended hierarchy

Human user -> Director -> Specialist agents

The Director is the operational manager. Specialist agents should execute within their role and escalate blockers back to the Director.

## Agents included

- Director
- Data Engineer
- Financial Data Extraction
- General Insurance Analyst
- Life Insurance Analyst
- Reinsurance Analyst
- Macroeconomic Analyst
- Report Compiler
