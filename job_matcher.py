import re
from typing import List, Dict
import aiohttp


class JobMatcher:
    """Resume-aware matcher that can work with or without an AI client."""

    def __init__(self, ai_client=None):
        self.ai_client = ai_client
        self.hh_api_url = "https://api.hh.ru/vacancies"
        self.cache = {}

    def score_lead(self, lead: Dict, resume_text: str) -> Dict:
        """Score any normalized job/freelance lead against resume text."""
        if not resume_text.strip():
            return {**lead, "match_score": None, "match_reason": "resume_not_configured"}

        vacancy = {
            "name": lead.get("name") or lead.get("title") or "",
            "description": lead.get("description") or lead.get("requirements") or "",
            "key_skills": lead.get("key_skills") or lead.get("matched_skills") or [],
            "experience": lead.get("experience") or "",
        }
        score = self._simple_match(vacancy, resume_text)
        skills = self._get_skills_match_sync(vacancy, resume_text)
        reason = (
            f"Совпадение по навыкам: {', '.join(skills)}"
            if skills
            else "Совпадение рассчитано по названию, стеку и уровню вакансии"
        )
        return {
            **lead,
            "match_score": score,
            "match_reason": reason,
            "resume_skills_match": skills,
        }

    async def search_matching_jobs(self, query: str, resume_text: str, filters: Dict) -> List[Dict]:
        vacancies = await self._fetch_vacancies(query, filters)
        if not vacancies:
            return []

        matched_jobs = []
        for vac in vacancies:
            match_score = await self._calculate_match(vac, resume_text)
            if match_score >= 60:
                match_reason = await self._get_match_reason(vac, resume_text)
                matched_jobs.append({
                    **vac,
                    "match_score": match_score,
                    "match_reason": match_reason,
                    "skills_match": await self._get_skills_match(vac, resume_text),
                })

        matched_jobs.sort(key=lambda x: x["match_score"], reverse=True)
        return matched_jobs

    async def _fetch_vacancies(self, query: str, filters: Dict) -> List[Dict]:
        params = {
            "text": query,
            "per_page": 30,
            "search_field": "name",
            "area": 1,
            "only_with_salary": False,
        }

        if filters.get("remote_only"):
            params["schedule"] = "remote"

        if filters.get("experience_level"):
            experience_map = {"junior": "1", "middle": "2", "senior": "3"}
            params["experience"] = experience_map.get(filters["experience_level"], "")

        headers = {"User-Agent": "JobApplyBot/1.0"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.hh_api_url, params=params, headers=headers) as response:
                    if response.status != 200:
                        return []
                    data = await response.json()
                    vacancies = []
                    for item in data.get("items", []):
                        title = item.get("name", "").lower()
                        if any(excl.lower() in title for excl in filters.get("exclude_keywords", [])):
                            continue

                        salary = item.get("salary")
                        if salary and str(salary.get("currency") or "").upper() in ("RUR", "RUB"):
                            salary_values = [
                                value for value in (salary.get("from"), salary.get("to"))
                                if isinstance(value, (int, float))
                            ]
                            maximum = filters.get("max_salary")
                            if maximum and salary_values and max(salary_values) > maximum:
                                continue

                        description = await self._get_vacancy_description(item.get("id"))
                        vacancies.append({
                            "id": item.get("id"),
                            "name": item.get("name"),
                            "employer": item.get("employer", {}).get("name"),
                            "area": item.get("area", {}).get("name"),
                            "url": item.get("alternate_url"),
                            "salary": self._format_salary(salary) if salary else "Зарплата не указана",
                            "description": description,
                            "key_skills": [skill.get("name") for skill in item.get("key_skills", [])],
                            "created_at": item.get("created_at"),
                            "schedule": item.get("schedule", {}).get("name", ""),
                            "experience": item.get("experience", {}).get("name", ""),
                            "site": "hh.ru",
                        })
                    return vacancies
        except Exception:
            return []

    async def _get_vacancy_description(self, vacancy_id: str) -> str:
        cache_key = f"desc_{vacancy_id}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.hh_api_url}/{vacancy_id}"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        description = data.get("description", "")[:3000]
                        self.cache[cache_key] = description
                        return description
        except Exception:
            pass
        return ""

    async def _calculate_match(self, vacancy: Dict, resume_text: str) -> int:
        if not self.ai_client:
            return self._simple_match(vacancy, resume_text)

        prompt = f"""Оцени соответствие между резюме и вакансией в процентах (0-100).

Резюме:
{resume_text[:1000]}

Вакансия:
Название: {vacancy.get('name', '')}
Описание: {vacancy.get('description', '')[:1000]}
Навыки: {', '.join(vacancy.get('key_skills', []))}
Опыт: {vacancy.get('experience', '')}

Ответь только числом от 0 до 100.
"""
        try:
            response = await self.ai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=10,
                temperature=0.3,
            )
            numbers = re.findall(r"\d+", response.choices[0].message.content.strip())
            return min(100, int(numbers[0])) if numbers else 50
        except Exception:
            return self._simple_match(vacancy, resume_text)

    def _simple_match(self, vacancy: Dict, resume_text: str) -> int:
        resume_lower = resume_text.lower()
        name = (vacancy.get("name") or "").lower()
        description = (vacancy.get("description") or "").lower()
        experience = (vacancy.get("experience") or "").lower()
        haystack = f"{name} {description} {experience}"

        tech_stack = [
            "react", "typescript", "javascript", "html", "css", "scss",
            "redux", "rest", "git", "figma", "python", "qa", "testing",
        ]
        resume_skills = [s for s in tech_stack if s in resume_lower]
        vacancy_skills = [s for s in tech_stack if s in haystack]
        shared = set(resume_skills) & set(vacancy_skills)

        skill_score = min(60, len(shared) * 12)
        title_score = 0
        for token in ("frontend", "react", "typescript", "верст", "qa", "tester"):
            if token in resume_lower and token in name:
                title_score += 10
        title_score = min(25, title_score)

        exp_score = 0
        if any(x in haystack for x in ("junior", "без опыта", "1-3 года", "1–3 года")):
            exp_score = 15
        elif "senior" not in haystack and "lead" not in haystack:
            exp_score = 8

        return min(100, skill_score + title_score + exp_score)

    async def _get_match_reason(self, vacancy: Dict, resume_text: str) -> str:
        if not self.ai_client:
            skills = self._get_skills_match_sync(vacancy, resume_text)
            return (
                f"Совпадают навыки: {', '.join(skills)}"
                if skills
                else "Соответствие рассчитано по стеку и уровню вакансии"
            )

        prompt = f"""Кратко объясни, почему кандидат подходит.
Резюме: {resume_text[:500]}
Вакансия: {vacancy.get('name', '')}
Навыки: {', '.join(vacancy.get('key_skills', []))}
"""
        try:
            response = await self.ai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0.5,
            )
            return response.choices[0].message.content.strip()
        except Exception:
            return "Соответствует по ключевым навыкам"

    async def _get_skills_match(self, vacancy: Dict, resume_text: str) -> List[str]:
        return self._get_skills_match_sync(vacancy, resume_text)

    def _get_skills_match_sync(self, vacancy: Dict, resume_text: str) -> List[str]:
        resume_lower = resume_text.lower()
        required = vacancy.get("key_skills", []) or []
        matched = [skill for skill in required if str(skill).lower() in resume_lower]

        if not matched:
            text = f"{vacancy.get('name', '')} {vacancy.get('description', '')}".lower()
            for skill in self._extract_skills(resume_text):
                if skill in text:
                    matched.append(skill)
        return matched[:8]

    def _extract_skills(self, text: str) -> List[str]:
        tech_stack = [
            "react", "vue", "angular", "javascript", "typescript", "python",
            "java", "php", "node", "express", "django", "flask", "spring",
            "aws", "docker", "kubernetes", "git", "linux", "sql", "mongodb",
            "postgresql", "redis", "graphql", "rest", "html", "css", "scss",
            "figma", "redux", "qa", "testing",
        ]
        lower = text.lower()
        return [skill for skill in tech_stack if skill in lower]

    def _format_salary(self, salary: Dict) -> str:
        parts = []
        if salary.get("from"):
            parts.append(f"от {salary['from']:,}".replace(",", " "))
        if salary.get("to"):
            parts.append(f"до {salary['to']:,}".replace(",", " "))
        if parts:
            result = " ".join(parts)
            if salary.get("currency"):
                result += f" {salary['currency']}"
            return result
        return "Зарплата не указана"
