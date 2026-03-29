# Nestra Superpowers Workflow

This document adapts the `obra/superpowers` workflow to Nestra's product and platform constraints.

Use this when shipping any non-trivial feature.

## Core loop

1. **Clarify the slice**
   - Name actor, household/tenant boundary, and desired outcome.
   - Identify guardrail, audit, and failure-safe behavior.
   - Produce a short design summary before coding.

2. **Write a concrete plan**
   - Break implementation into small tasks with exact file paths.
   - Include verification steps for each task.
   - Keep scope to the smallest shippable slice.

3. **Implement in small steps**
   - Prefer one focused change set at a time.
   - Keep API contracts explicit and typed.
   - Add or update docs for meaningful architecture decisions.

4. **Review and validate**
   - Validate syntax/build/tests with real commands.
   - Verify critical runtime paths (health, route behavior, guardrails).
   - Confirm audit visibility for sensitive actions.

5. **Close with evidence**
   - Summarize what changed and why.
   - Report what was validated and what remains.
   - Leave clear next slices for follow-up.

## Nestra guardrails for execution

- Do not claim enterprise capabilities that are not implemented.
- Do not ship automation behavior without guardrail rules.
- Do not ship critical actions without audit events.
- Do not bypass tenant/household context boundaries.
- Do not skip verification.

## Recommended command sequence

1. Plan only:

```text
/nestra-plan <task>
```

2. Implement feature:

```text
/nestra-feature <task>
```

3. Execute with explicit checklist:

```text
/nestra-execute <task>
```

## Optional plugin setup

If you want full superpowers plugin behavior in OpenCode, add this to project-level `opencode.json`:

```json
{
  "plugin": ["superpowers@git+https://github.com/obra/superpowers.git"]
}
```

Then restart OpenCode.
