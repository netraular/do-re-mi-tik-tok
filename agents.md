## User Verification Workflow

**IMPORTANT**: Upon finishing your tasks you **MUST use the `ask_questions` tool** to present a summary of completed work and ask the user for feedback. Never forget this.
Subagents MUST NOT ask the user for feedback: Only the main/primary agent should interact with the user via the `ask_questions` tool.


### Verification Process:

1. Complete all assigned tasks.
2. Use the `ask_questions` tool with `allowFreeformInput: true` to present a summary of what was done and ask the user if everything looks good or if they have feedback.

**Remember**: Always ask the user for feedback before finalizing the chat, even for simple questions/answers or explanations.

---

## General Guidelines

- Always write everything in **English**.
- Work in small, testable increments.
- Sometimes an agent will be asked to generate a summary of the current status/information gathered and pending tasks. Whenever that happens, it should also add to the summary the importance of following the agents.md file.
- Always display the form information BEFORE executing `ask_questions`. When executing it, always ensure it includes multiple-choice options alongside one open-ended option.