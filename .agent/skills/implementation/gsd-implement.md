---
tool: gsd-implement
description: Use this skill for autonomous execution of tasks, multi-file code generation, and complex implementation work.
---

# GSD Implementation Loop

GSD's autonomous execution engine follows a strict state machine to build software with high fidelity and clean history.

## The Execution Cycle

The core loop follows this progression:
**Plan (with integrated research) → Execute (per task) → Complete → Reassess Roadmap → Next Slice**

### 1. Plan
*   Scout the codebase and research relevant documentation.
*   Decompose the slice into discrete tasks with explicit "must-haves".
*   Identify boundaries and dependencies.

### 2. Execute
*   Run each task in a fresh, isolated context window.
*   Focus on the specific task plan without accumulated "context garbage".
*   Perform multi-file edits, shell commands, and subagent dispatches as needed.

### 3. Complete
*   Write a concise summary of changes.
*   Generate a User Acceptance Test (UAT) script.
*   Commit changes with meaningful, task-derived messages.

### 4. Reassess
*   Check if the roadmap still makes sense after the implementation.
*   Adjust subsequent slices based on new information or technical discoveries.

### 5. Validate Milestone
*   Reconciliation gate after all slices complete.
*   Compare roadmap success criteria against actual results.
*   Catch gaps before final completion.

## Guiding Principles

### Context Isolation
Every unit of work (task, research, planning) starts with a clean context window. Only relevant artifacts (task plans, summaries, decisions register) are inlined to prevent context rot.

### Incremental Memory
Maintain a `KNOWLEDGE.md` register of project-specific rules, patterns, and lessons learned. Read it at the start of every unit and update it when discovering recurring issues.

### Verification Gates
Run automated verification commands (lint, test) after every task execution. Failures trigger auto-fix retries where the agent attempts to resolve issues before advancing.
