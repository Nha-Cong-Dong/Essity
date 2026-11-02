# T7.12d plan (self, yellow)
1. Repo: KnowledgeUnitRepository.by_section(subject_id) -> (section rows, unit rows, links), user-scoped.
2. API: GET /v1/subjects/{id}/units/by-section in api/units.py (router already verified_user -> 403). 404 for other user's subject.
   Shape: groups[{section_id|null, title|null, units[{id,title,content,kind,status}]}]; sections by ord,id; ungrouped last; draft+canonical only; card in several sections appears in each.
3. Tests (AC14): grouping, ungrouped group, status filter, two-user isolation, unverified 403, unknown subject 404.
4. Regen api-client; web: UnitsBySection component in components/session-study, shown on the session screen; vitest + 320px class check.
5. Gates: core batches, lint/typecheck/vitest, touched e2e.
