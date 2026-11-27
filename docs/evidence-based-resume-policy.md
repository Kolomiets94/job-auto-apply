# Evidence-based resume and application drafts

## Purpose

Application drafts must read like a concise engineering account of work actually done, not like marketing copy. The system must optimize for credibility and verifiability, not for an inflated ATS score.

## Required rules

1. **No invented metrics.** Never invent percentages, latency improvements, throughput, uptime, revenue impact, defect reductions, user counts, savings, or other numerical outcomes. Include a measurement only when the exact value, measurement method, baseline, and scope are present in verified candidate-provided evidence.
2. **Describe engineering work concretely.** Prefer the actual task, the candidate's action, the technology used, and the implemented behavior. Avoid empty claims such as "optimized", "improved", or "increased efficiency" without an explanation of what changed.
3. **Separate personal contribution from team outcomes.** Do not attribute company revenue, conversion, availability, or product-wide outcomes to the candidate unless their personal contribution and the causal evidence are explicitly documented.
4. **Do not invent experience.** Personal, educational, and pet projects must remain clearly identified as such. Never present them as commercial employment or production experience.
5. **Only claim verified skills and features.** Match a vacancy by selecting relevant facts already present in the candidate's verified profile/project evidence. A vacancy requirement is not evidence that the candidate has that skill.
6. **Keep uncertainty visible.** If a project detail, metric, role, or result is not documented, omit it or ask the candidate to confirm it. Do not fill gaps with plausible-sounding claims.
7. **Links are evidence, not proof of every claim.** A repository link may be included, but do not assume that every feature mentioned in a draft exists in that repository unless it has been checked.

## Preferred sentence structure

- "В личном проекте [название] реализовал [конкретную функцию] на [подтверждённый стек]. Код: [ссылка]."
- "В рамках учебного проекта отвечал за [личная задача]; реализовал [конкретные действия/поведение]."
- "Исправил [конкретную техническую проблему] способом [описанное решение]." Use only when the problem and solution are documented.

Avoid unsupported formulations such as:
- "Ускорил приложение на 40%."
- "Снизил количество ошибок на 60%."
- "Повысил отказоустойчивость до 99,9%."
- "Увеличил выручку продукта на 15%."
- "Оптимизировал архитектуру и значительно улучшил производительность."

These examples are prohibited unless backed by candidate-provided, verifiable measurements and a clear description of the candidate's own contribution.

## Enforcement

- Draft-generation tests must cover Russian and English templates and representative vacancy categories.
- Tests must reject invented quantified impact and commercial-experience claims in generated drafts.
- ATS matching may report skill gaps, but must never add missing skills to the resume or cover letter.
- This policy does not loosen vacancy filters or authorize sending applications. Drafts remain drafts until separately approved.
