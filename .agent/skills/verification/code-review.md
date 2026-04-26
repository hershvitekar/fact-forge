---
name: requesting-code-review
description: Use when completing tasks, implementing major features, or before merging to verify work meets requirements.
---

# Requesting Code Review

Review early, review often. Catch issues before they cascade by treating code review as a mandatory gate for major tasks.

## When to Request Review
*   **Mandatory**: After each major task, after completing a feature, and before merging to the main branch.
*   **Recommended**: When stuck, before refactoring, or after fixing a complex bug.

## Review Process
1.  **Define the Scope**: Clearly state what was implemented and what the original requirements were.
2.  **Provide Context**: Use git diffs or specific file paths to focus the review on the work product, not the thought process.
3.  **Analyze Feedback**:
    *   **Critical**: Fix immediately.
    *   **Important**: Fix before proceeding.
    *   **Minor**: Note for later cleanup.

## Guardrails
*   **Don't skip**: Never skip review because "it's simple."
*   **Don't ignore**: Address all Critical and Important issues.
*   **Constructive Pushback**: If the review is technically incorrect, push back with reasoning and evidence (tests/code).

## Workflow Integration
In subagent-driven development or plan execution, review after each task or batch of 3 tasks to prevent compounding errors.
