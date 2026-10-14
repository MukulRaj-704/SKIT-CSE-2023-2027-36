import re
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


class SkillGapAnalyzer:
    def __init__(
        self,
        minimum_coverage: float = 0.0,
        max_priorities: int = 10,
        max_recommendations: int = 10,
    ):
        self.minimum_coverage = max(
            0.0,
            min(100.0, float(minimum_coverage))
        )
        self.max_priorities = max(0, int(max_priorities))
        self.max_recommendations = max(0, int(max_recommendations))

        self.skill_fields = (
            "skills",
            "skill",
            "required_skills",
            "preferred_skills",
            "technical_skills",
            "technologies",
            "technology",
            "tech_stack",
            "tools",
            "frameworks",
            "languages",
            "competencies",
            "tags",
        )

        self.requirement_fields = (
            "requirements",
            "qualifications",
            "responsibilities",
            "description",
            "job_description",
        )

    def analyze(
        self,
        profile: Optional[Dict[str, Any]],
        jobs: Optional[Iterable[Dict[str, Any]]] = None,
        target_job: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        profile = profile or {}
        profile_skills = self.extract_skills(profile)

        if target_job is not None:
            return self.analyze_job(profile, target_job)

        job_list = [
            job for job in (jobs or [])
            if isinstance(job, dict)
        ]

        reports = [
            self.analyze_job(profile, job)
            for job in job_list
        ]

        eligible_reports = [
            report for report in reports
            if report["coverage"]["percentage"] >= self.minimum_coverage
        ]

        skill_frequency = Counter()
        missing_frequency = Counter()
        skill_importance = defaultdict(float)
        skill_jobs = defaultdict(list)

        for report in reports:
            for skill in report["required_skills"]:
                skill_frequency[skill] += 1

            for item in report["skill_gaps"]:
                skill = item["skill"]
                missing_frequency[skill] += 1
                skill_importance[skill] += item["importance"]
                skill_jobs[skill].append(report["job"])

        total_jobs = len(reports)

        priorities = []

        for skill, frequency in missing_frequency.items():
            demand = frequency / max(total_jobs, 1)
            average_importance = (
                skill_importance[skill] / frequency
            )

            priority_score = (
                demand * 60.0
                + average_importance * 40.0
            )

            priorities.append({
                "skill": skill,
                "priority_score": round(priority_score, 2),
                "jobs_requiring_skill": frequency,
                "job_demand_percentage": round(
                    demand * 100.0,
                    2
                ),
                "average_importance": round(
                    average_importance,
                    2
                ),
                "related_jobs": self.unique(
                    skill_jobs[skill]
                ),
            })

        priorities.sort(
            key=lambda item: (
                item["priority_score"],
                item["jobs_requiring_skill"],
                item["skill"],
            ),
            reverse=True,
        )

        average_coverage = (
            sum(
                report["coverage"]["percentage"]
                for report in reports
            ) / total_jobs
            if total_jobs else 0.0
        )

        return {
            "profile_skills": sorted(profile_skills),
            "jobs_analyzed": total_jobs,
            "jobs_meeting_coverage_threshold": len(
                eligible_reports
            ),
            "average_skill_coverage": round(
                average_coverage,
                2
            ),
            "skill_demand": [
                {
                    "skill": skill,
                    "job_count": count,
                    "demand_percentage": round(
                        count / max(total_jobs, 1) * 100,
                        2,
                    ),
                }
                for skill, count in skill_frequency.most_common()
            ],
            "priority_skills": priorities[:self.max_priorities],
            "job_reports": reports,
            "recommendations": self.build_recommendations(
                priorities
            ),
        }

    def analyze_job(
        self,
        profile: Optional[Dict[str, Any]],
        job: Dict[str, Any],
    ) -> Dict[str, Any]:
        profile = profile or {}
        job = job or {}

        profile_skills = self.extract_skills(profile)
        required_skills = self.extract_skills(job)

        matched_skills = profile_skills & required_skills
        missing_skills = required_skills - profile_skills

        skill_weights = self.extract_skill_weights(job)

        total_weight = sum(
            skill_weights.get(skill, 1.0)
            for skill in required_skills
        )

        matched_weight = sum(
            skill_weights.get(skill, 1.0)
            for skill in matched_skills
        )

        coverage = (
            matched_weight / total_weight * 100.0
            if total_weight > 0
            else 100.0
        )

        gaps = []

        for skill in missing_skills:
            importance = skill_weights.get(skill, 1.0)

            gaps.append({
                "skill": skill,
                "importance": round(importance, 2),
                "priority": self.priority_label(importance),
            })

        gaps.sort(
            key=lambda item: (
                item["importance"],
                item["skill"],
            ),
            reverse=True,
        )

        matched = sorted(matched_skills)
        missing = sorted(missing_skills)

        return {
            "job": self.job_identity(job),
            "required_skills": sorted(required_skills),
            "profile_skills": sorted(profile_skills),
            "matched_skills": matched,
            "missing_skills": missing,
            "skill_gaps": gaps,
            "coverage": {
                "matched_count": len(matched),
                "missing_count": len(missing),
                "required_count": len(required_skills),
                "percentage": round(coverage, 2),
                "weighted_percentage": round(coverage, 2),
            },
            "assessment": self.assess_coverage(coverage),
            "recommendations": self.build_recommendations(
                gaps
            ),
        }

    def extract_skills(
        self,
        data: Any,
        inherited_key: str = "",
    ) -> Set[str]:
        skills = set()

        if data is None:
            return skills

        if isinstance(data, dict):
            for key, value in data.items():
                normalized_key = self.normalize_key(key)

                if normalized_key in self.skill_fields:
                    skills.update(
                        self.parse_skill_values(value)
                    )
                elif isinstance(value, (dict, list, tuple, set)):
                    if normalized_key in self.requirement_fields:
                        skills.update(
                            self.extract_skills(value)
                        )

            return skills

        if isinstance(data, (list, tuple, set)):
            for item in data:
                if isinstance(item, str):
                    skill = self.normalize_skill(item)

                    if skill:
                        skills.add(skill)
                elif isinstance(item, dict):
                    skills.update(self.extract_skills(item))

            return skills

        if isinstance(data, str) and inherited_key in self.skill_fields:
            skills.update(self.parse_skill_values(data))

        return skills

    def parse_skill_values(self, value: Any) -> Set[str]:
        if value is None:
            return set()

        if isinstance(value, dict):
            result = set()

            for key, item in value.items():
                if isinstance(item, (int, float)):
                    skill = self.normalize_skill(key)

                    if skill:
                        result.add(skill)
                else:
                    result.update(self.parse_skill_values(item))

            return result

        if isinstance(value, (list, tuple, set)):
            result = set()

            for item in value:
                result.update(self.parse_skill_values(item))

            return result

        if not isinstance(value, str):
            return set()

        parts = re.split(r"[,;\n|]+", value)
        result = set()

        for part in parts:
            skill = self.normalize_skill(part)

            if skill:
                result.add(skill)

        return result

    def extract_skill_weights(
        self,
        job: Dict[str, Any],
    ) -> Dict[str, float]:
        weights = {}

        raw_weights = job.get("skill_weights") or {}

        if not isinstance(raw_weights, dict):
            return weights

        for skill, weight in raw_weights.items():
            normalized = self.normalize_skill(skill)

            try:
                numeric_weight = float(weight)
            except (TypeError, ValueError):
                continue

            if normalized and numeric_weight > 0:
                weights[normalized] = numeric_weight

        return weights

    def build_recommendations(
        self,
        priorities: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        recommendations = []

        for item in priorities[:self.max_recommendations]:
            if isinstance(item, str):
                skill = self.normalize_skill(item)
                importance = 1.0
                score = 0.0
                jobs_count = 0
            else:
                skill = self.normalize_skill(item.get("skill"))
                importance = item.get("importance", 1.0)
                score = item.get("priority_score", 0.0)
                jobs_count = item.get("jobs_requiring_skill", 0)

            if not skill:
                continue

            recommendations.append({
                "skill": skill,
                "priority_score": round(float(score), 2),
                "importance": round(float(importance), 2),
                "jobs_requiring_skill": int(jobs_count),
                "action": f"Build practical projects using {skill}",
            })

        return recommendations

    def priority_label(self, importance: float) -> str:
        if importance >= 3.0:
            return "high"

        if importance >= 2.0:
            return "medium"

        return "normal"

    def assess_coverage(self, percentage: float) -> str:
        if percentage >= 90:
            return "excellent"

        if percentage >= 75:
            return "strong"

        if percentage >= 50:
            return "moderate"

        if percentage > 0:
            return "developing"

        return "insufficient"

    def job_identity(self, job: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": job.get("id"),
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "location": job.get("location", ""),
            "category": job.get("category", ""),
        }

    def normalize_skill(self, value: Any) -> str:
        if value is None:
            return ""

        value = str(value).strip().lower()
        value = re.sub(r"\s+", " ", value)
        value = re.sub(r"^[\s,;|]+|[\s,;|]+$", "", value)

        return value

    def normalize_key(self, value: Any) -> str:
        value = str(value).strip().lower()
        return re.sub(r"[\s-]+", "_", value)

    def unique(self, values: Iterable[Any]) -> List[Any]:
        result = []
        seen = set()

        for value in values:
            if isinstance(value, dict):
                key = tuple(sorted(value.items()))
            else:
                key = str(value).lower()

            if key in seen:
                continue

            seen.add(key)
            result.append(value)

        return result