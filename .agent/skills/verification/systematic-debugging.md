---
name: systematic-debugging
description: Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes.
---

# Systematic Debugging Discipline

Random fixes waste time and create new bugs. Quick patches mask underlying issues. ALWAYS find the root cause before attempting fixes. Symptom fixes are failure.

## The Iron Law
**NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST.**

## The Four Phases

### Phase 1: Root Cause Investigation
1.  **Read Error Messages Carefully**: Note line numbers, file paths, and error codes.
2.  **Reproduce Consistently**: Trigger the issue reliably before acting.
3.  **Check Recent Changes**: Git diffs, dependencies, and config changes.
4.  **Gather Evidence**: Add diagnostic instrumentation (logging) at component boundaries to reveal WHERE it breaks.
5.  **Trace Data Flow**: Trace backward through the call stack to find where the bad value originated.

### Phase 2: Pattern Analysis
1.  **Find Working Examples**: Locate similar working code in the same codebase.
2.  **Compare Against References**: Read reference implementations completely; don't skim.
3.  **Identify Differences**: List every difference between working and broken code, however small.

### Phase 3: Hypothesis and Testing
1.  **Form Single Hypothesis**: "I think X is the root cause because Y."
2.  **Test Minimally**: Make the smallest possible change to test the hypothesis (one variable at a time).
3.  **Verify Before Continuing**: If it didn't work, form a NEW hypothesis. Don't stack fixes.

### Phase 4: Implementation
1.  **Create Failing Test Case**: Automate the reproduction before fixing.
2.  **Implement Single Fix**: Address the identified root cause only.
3.  **Verify Fix**: Ensure the test passes and no other regressions occur.
4.  **If 3+ Fixes Fail**: Stop and question the architecture. Discuss with your human partner.

## Red Flags (STOP and Return to Phase 1)
*   "Quick fix for now, investigate later."
*   "Just try changing X and see if it works."
*   "It's probably X, let me fix that."
*   Proposing solutions before tracing data flow.
*   **"One more fix attempt" after 2+ failures.**
