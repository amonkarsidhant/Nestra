# Nestra Spinout Plan (Separate Repository)

## Why spin out
Nestra now has its own product identity, architecture direction, and delivery workflow. Keeping it in a dedicated repository improves focus, release velocity, and partner-facing clarity.

## Suggested new repository metadata
- **Repository name:** `nestra`
- **Short description:** `Policy-first smart home operating layer with voice, guardrails, and auditable automation outcomes.`
- **Website:** `https://nestra.homelabdev.space`

## Recommended migration steps
1. Create new repo `nestra` on GitHub.
2. Preserve history for `nestra/` using subtree split:

```bash
git subtree split --prefix=nestra -b nestra-history
git clone <new-nestra-repo-url> nestra-repo
cd nestra-repo
git pull /path/to/homelab nestra-history
```

3. Add top-level docs in new repo from this folder:
   - `DESCRIPTION.md`
   - `PRODUCT_BRIEF.md`
   - `MVP_SPEC.md`
   - `UX_FLOWS.md`
   - `CLAUDE_CODE_TASKLIST.md`
4. Configure CI and deployment in new repo.
5. Keep a lightweight pointer in homelab to new Nestra repo.

## Post-spinout rule
All product and code evolution for Nestra should happen in the dedicated repository first, then referenced back into homelab only when infra integration changes are needed.
