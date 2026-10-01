import re
from typing import Any, Dict, Iterable, List, Optional

from .ranking import JobRankingService


class JobMatchingService:
    def __init__(
        self,
        ranking_service: Optional[JobRankingService] = None,
        minimum_score: float = 0.0,
    ):
        self.ranking_service = ranking_service or JobRankingService()
        self.minimum_score = max(0.0, min(1.0, minimum_score))

    def match(
        self,
        profile: Optional[Dict[str, Any]],
        jobs: Iterable[Dict[str, Any]],
        limit: Optional[int] = None,
        minimum_score: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        profile = profile or {}
        jobs = list(jobs)

        ranked_jobs = self.ranking_service.rank(
            jobs,
            profile=profile,
            limit=None,
        )

        threshold = (
            self.minimum_score
            if minimum_score is None
            else max(0.0, min(1.0, minimum_score))
        )

        matches = []

        for job in ranked_jobs:
            score = job.get("ranking", {}).get("score", 0.0)

            if score < threshold:
                continue

            matches.append(
                self._build_match_result(
                    job=job,
                    profile=profile,
                )
            )

        if limit is not None:
            return matches[:max(0, limit)]

        return matches

    def match_one(
        self,
        profile: Optional[Dict[str, Any]],
        job: Dict[str, Any],
    ) -> Dict[str, Any]:
        results = self.match(
            profile=profile,
            jobs=[job],
            limit=1,
        )

        if results:
            return results[0]

        return self._build_match_result(
            job=job,
            profile=profile or {},
        )

    def explain_match(
        self,
        profile: Optional[Dict[str, Any]],
        job: Dict[str, Any],
    ) -> Dict[str, Any]:
        profile = profile or {}

        ranked = self.ranking_service.rank(
            [job],
            profile=profile,
            limit=1,
        )

        if not ranked:
            return {
                "job": job,
                "score": 0.0,
                "signals": {},
                "matched_skills": [],
                "missing_skills": [],
                "explanation": "Unable to calculate a match.",
            }

        ranked_job = ranked[0]
        signals = ranked_job.get("ranking", {}).get("signals", {})

        matched_skills, missing_skills = self._skill_analysis(
            profile,
            job,
        )

        return {
            "job": ranked_job,
            "score": ranked_job.get("ranking", {}).get("score", 0.0),
            "signals": signals,
            "matched_skills": matched_skills,
            "missing_skills": missing_skills,
            "explanation": self._build_explanation(
                signals=signals,
                matched_skills=matched_skills,
                missing_skills=missing_skills,
            ),
        }

    def filter_by_category(
        self,
        jobs: Iterable[Dict[str, Any]],
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not category:
            return list(jobs)

        target = self._normalize(category)
        filtered = []

        for job in jobs:
            job_category = self._normalize(
                job.get("category")
                or job.get("job_category")
                or ""
            )

            if target in job_category or job_category in target:
                filtered.append(job)

        return filtered

    def filter_by_job_type(
        self,
        jobs: Iterable[Dict[str, Any]],
        job_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not job_type:
            return list(jobs)

        target = self._normalize(job_type)
        filtered = []

        for job in jobs:
            current_type = self._normalize(
                job.get("job_type")
                or job.get("type")
                or ""
            )

            if target in current_type or current_type in target:
                filtered.append(job)

        return filtered

    def filter_by_location(
        self,
        jobs: Iterable[Dict[str, Any]],
        location: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not location:
            return list(jobs)

        target = self._normalize(location)
        filtered = []

        for job in jobs:
            job_location = self._normalize(
                job.get("location")
                or job.get("job_location")
                or ""
            )

            if target in job_location or job_location in target:
                filtered.append(job)

        return filtered

    def find(
        self,
        profile: Optional[Dict[str, Any]],
        jobs: Iterable[Dict[str, Any]],
        category: Optional[str] = None,
        job_type: Optional[str] = None,
        location: Optional[str] = None,
        limit: Optional[int] = None,
        minimum_score: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        filtered_jobs = list(jobs)

        filtered_jobs = self.filter_by_category(
            filtered_jobs,
            category,
        )

        filtered_jobs = self.filter_by_job_type(
            filtered_jobs,
            job_type,
        )

        filtered_jobs = self.filter_by_location(
            filtered_jobs,
            location,
        )

        return self.match(
            profile=profile,
            jobs=filtered_jobs,
            limit=limit,
            minimum_score=minimum_score,
        )

    def _build_match_result(
        self,
        job: Dict[str, Any],
        profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        ranking = job.get("ranking", {})
        signals = ranking.get("signals", {})

        matched_skills, missing_skills = self._skill_analysis(
            profile,
            job,
        )

        result = dict(job)
        result["match"] = {
            "score": ranking.get("score", 0.0),
            "matched_skills": matched_skills,
            "missing_skills": missing_skills,
            "signals": signals,
            "explanation": self._build_explanation(
                signals=signals,
                matched_skills=matched_skills,
                missing_skills=missing_skills,
            ),
        }

        return result

    def _skill_analysis(
        self,
        profile: Dict[str, Any],
        job: Dict[str, Any],
    ) -> tuple:
        profile_skills = self._extract_explicit_skills(profile)
        job_skills = self._extract_explicit_skills(job)

        if not job_skills:
            return sorted(profile_skills), []

        matched = profile_skills & job_skills
        missing = job_skills - profile_skills

        return sorted(matched), sorted(missing)

    def _extract_explicit_skills(
        self,
        data: Dict[str, Any],
    ) -> set:
        values = []

        for key in (
            "skills",
            "skill",
            "technologies",
            "technology",
            "tech_stack",
            "tags",
        ):
            value = data.get(key)

            if isinstance(value, (list, tuple, set)):
                values.extend(value)
            elif value:
                values.append(value)

        skills = set()

        for value in values:
            if isinstance(value, str):
                for item in re.split(r"[,;|/]+", value):
                    normalized = self._normalize_skill(item)

                    if normalized:
                        skills.add(normalized)

        return skills

    def _normalize_skill(self, value: Any) -> str:
        if value is None:
            return ""

        value = str(value).strip().lower()
        value = re.sub(r"\s+", " ", value)
        value = re.sub(r"[^a-z0-9+#.\- ]", "", value)

        return value.strip()

    def _normalize(self, value: Any) -> str:
        if value is None:
            return ""

        value = str(value).lower().strip()
        value = re.sub(r"[^a-z0-9+#.\- ]", " ", value)
        value = re.sub(r"\s+", " ", value)

        return value

    def _build_explanation(
        self,
        signals: Dict[str, float],
        matched_skills: List[str],
        missing_skills: List[str],
    ) -> str:
        parts = []

        score = sum(signals.values()) / len(signals) if signals else 0.0

        if score >= 0.75:
            parts.append("Strong overall profile alignment.")
        elif score >= 0.5:
            parts.append("Moderate profile alignment.")
        elif score >= 0.25:
            parts.append("Partial profile alignment.")
        else:
            parts.append("Limited profile alignment.")

        if matched_skills:
            parts.append(
                f"{len(matched_skills)} relevant skills matched."
            )

        if missing_skills:
            parts.append(
                f"{len(missing_skills)} job skills may need development."
            )

        if signals.get("location", 0.0) >= 0.8:
            parts.append("Location preference is well aligned.")

        if signals.get("experience", 0.0) >= 0.8:
            parts.append("Experience requirement is well aligned.")

        return " ".join(parts)