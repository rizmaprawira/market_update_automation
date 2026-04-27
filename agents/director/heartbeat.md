# Director - Heartbeat Checklist

Run this checklist every time you receive, resume, or review a task.

## 1. Identify the Request

- What is the human user asking for?
- Is this a full monthly market update task or a partial workflow task?
- What is the target period?
- Is the period explicitly stated in `YYYY-MM` format?
- If the period is missing, infer only when obvious; otherwise ask the human user.

## 2. Identify the Workflow Stage

Classify the request into one or more stages:

- Setup / planning
- PDF download
- PDF conversion
- Financial data extraction
- General insurance analysis
- Life insurance analysis
- Reinsurance analysis
- Macroeconomic analysis
- Report compilation
- Quality review
- Troubleshooting

## 3. Check Ownership

Route the task using `routing.md`.

If the task belongs to a specialist, delegate it. Do not execute specialist work yourself.

## 4. Check Inputs Before Delegating

For every delegated task, specify:

- Input file or folder.
- Output file or folder.
- Target period.
- Required log file.
- Acceptance criteria.
- Handoff recipient.

## 5. Review Existing Progress

Before creating duplicate work:

- Check whether a subtask already exists.
- Check whether an agent has already reported completion.
- Check whether the required output files already exist.
- Check whether a task is stale or blocked.

## 6. Validate Handoffs

Before moving to the next stage, confirm:

- The previous agent produced the expected output.
- Logs exist.
- Failures are documented.
- Missing data is marked clearly.
- No unsupported assumptions were introduced.

## 7. Manage Blockers

If a blocker exists:

- Identify the owning agent.
- Ask for a correction if the blocker is agent-level.
- Escalate to the human user if the blocker requires business judgment.
- Do not ignore the blocker.

## 8. Comment on the Task

After every meaningful action, post a status comment:

```text
Status:
Target period:
Action taken:
Assigned to:
Reason:
Expected output:
Blockers:
Next step:
```

## 9. End State

At the end of each Director action, one of these must be true:

- A specialist has been assigned a clear subtask.
- A completed handoff has been accepted.
- A correction has been requested.
- A blocker has been escalated.
- The workflow has been marked complete with final outputs.
