# Nestra Skill Stack (from alirezarezvani/claude-skills)

This is the recommended subset of skills to use for Nestra.

## Core build loop (always-on)

1. `engineering/spec-driven-workflow`
   - Use for spec-first slices (requirements, acceptance criteria, edge cases).
2. `engineering-team/senior-architect`
   - Use for tenancy boundaries, domain decomposition, and ADR-level choices.
3. `engineering-team/senior-backend`
   - Use for API contracts, guardrails, auth boundaries, and persistence behavior.
4. `engineering-team/senior-frontend`
   - Use for implementation and performance of web app surfaces.
5. `engineering/api-design-reviewer`
   - Use before merge for REST consistency and breaking-change checks.

## Product and UX stack

6. `product-team/product-strategist`
   - Use for quarterly narrative, ICP alignment, and outcome-oriented roadmap slices.
7. `product-team/ui-design-system`
   - Use for tokenized visual system, consistency, and handoff quality.
8. `product-team/ux-researcher-designer`
   - Use for scenario clarity, friction removal, and trust-focused flows.
9. `product-team/landing-page-generator`
   - Use for sales-facing messaging experiments and rapid page variants.

## Reliability and operations stack

10. `engineering/observability-designer`
    - Use to define SLI/SLOs, alerts, dashboards, and incident visibility.
11. `engineering/ci-cd-pipeline-builder`
    - Use for repeatable checks and quality gates.
12. `engineering/runbook-generator`
    - Use to produce operational runbooks for deploy/recover/debug paths.

## Security and hygiene stack

13. `engineering/skill-security-auditor`
    - Use before importing third-party skills or scripts.
14. `engineering/dependency-auditor`
    - Use for dependency risk/license and upgrade planning.
15. `engineering/env-secrets-manager`
    - Use for secret handling and leak prevention patterns.

## How to use for Nestra slices

- Design phase: `spec-driven-workflow` + `senior-architect` + `product-strategist`
- Build phase: `senior-backend` + `senior-frontend` + `ui-design-system`
- Review phase: `api-design-reviewer` + `observability-designer`
- Release phase: `ci-cd-pipeline-builder` + `runbook-generator`

## Practical activation prompts

- "Use spec-driven-workflow to write a shippable spec for <feature>."
- "Use senior-architect to propose domain boundaries and risks for <feature>."
- "Use senior-backend to define API contracts and guardrail logic for <feature>."
- "Use senior-frontend + ui-design-system to implement the premium UI slice for <feature>."
- "Use api-design-reviewer to review breaking changes and consistency before merge."
- "Use observability-designer to define SLI/SLO and alerts for <feature>."
