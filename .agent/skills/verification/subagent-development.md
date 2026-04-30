---
name: subagent-driven-development
description: Use when executing implementation plans with independent tasks in the current session.
---

# Subagent-Driven Development

Execute plans by dispatching specialized subagents per task. This ensures isolated context, focused execution, and high-quality results.

## Core Principle
**Fresh Subagent per Task + Two-Stage Review (Spec Compliance → Code Quality).**

## The Workflow

### 1. Preparation
*   Read the implementation plan and extract all tasks with full text and context.
*   Note dependencies and cross-task context.

### 2. Per-Task Execution Cycle
1.  **Dispatch Implementer**: Give the subagent the specific task text and relevant context.
2.  **Answer Questions**: Resolve any blockers or clarifications before implementation begins.
3.  **Implementation**: Subagent implements, tests, commits, and performs a self-review.
4.  **Spec Compliance Review**: Verify the code matches the specification exactly (no missing features, no "extra" features).
5.  **Code Quality Review**: Verify the implementation is clean, follows patterns, and is technically sound.

### 3. Review Gates
*   **DONE**: Proceed to review.
*   **DONE_WITH_CONCERNS**: Review the implementer's notes before proceeding.
*   **NEEDS_CONTEXT**: Provide missing info and re-dispatch.
*   **BLOCKED**: Assess the blocker and adjust (break task down, use more capable model, or update plan).

## Guardrails
*   **Isolation**: Never let subagents inherit the main session's history; provide only what they need.
*   **Sequential Review**: Always finish the spec compliance review before starting the code quality review.
*   **No Skipping**: Never skip reviews or proceed with unfixed issues.
*   **TDD**: Subagents should follow Test-Driven Development for each task.
