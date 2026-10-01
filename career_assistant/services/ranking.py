import math
import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Sequence


class JobRankingService:
    def __init__(
        self,
        semantic_weight: float = 0.45,
        skill_weight: float = 0.25,
        title_weight: float = 0.15,
        experience_weight: float = 0.10,
        location_weight: float = 0.05,
    ):
        weights = {
            "semantic": semantic_weight,
            "skill": skill_weight,
            "title": title_weight,
            "experience": experience_weight,
            "location": location_weight,
        }
        total = sum(weights.values())
        if total <= 0:
            raise ValueError("Ranking weights must have a positive total")
        self.weights = {key: value / total for key, value in weights.items()}
        self.stop_words = {
            "a", "an", "and", "are", "as", "at", "be", "by", "for",
            "from", "has", "have", "in", "is", "it", "of", "on", "or",
            "that", "the", "to", "with", "this", "will", "you", "your"
        }

    def rank(
        self,
        jobs: Iterable[Dict[str, Any]],
        profile: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        profile = profile or {}
        ranked = []

        for job in jobs:
            signals = self._calculate_signals(job, profile)
            score = self._calculate_score(signals)
            result = dict(job)
            result["ranking"] = {
                "score": round(score, 4),
                "signals": {
                    key: round(value, 4)
                    for key, value in signals.items()
                },
            }
            ranked.append(result)

        ranked.sort(
            key=lambda item: (
                item["ranking"]["score"],
                self._safe_text(item.get("title")).lower(),
            ),
            reverse=True,
        )

        if limit is not None:
            return ranked[:max(0, limit)]

        return ranked

    def rank_single(
        self,
        job: Dict[str, Any],
        profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.rank([job], profile=profile, limit=1)[0]

    def _calculate_signals(
        self,
        job: Dict[str, Any],
        profile: Dict[str, Any],
    ) -> Dict[str, float]:
        return {
            "semantic": self._semantic_score(job, profile),
            "skill": self._skill_score(job, profile),
            "title": self._title_score(job, profile),
            "experience": self._experience_score(job, profile),
            "location": self._location_score(job, profile),
        }

    def _calculate_score(self, signals: Dict[str, float]) -> float:
        score = 0.0

        for key, weight in self.weights.items():
            score += signals.get(key, 0.0) * weight

        return min(1.0, max(0.0, score))

    def _semantic_score(
        self,
        job: Dict[str, Any],
        profile: Dict[str, Any],
    ) -> float:
        profile_text = self._profile_text(profile)
        job_text = self._job_text(job)

        if not profile_text or not job_text:
            return 0.0

        profile_tokens = self._tokenize(profile_text)
        job_tokens = self._tokenize(job_text)

        if not profile_tokens or not job_tokens:
            return 0.0

        profile_counter = Counter(profile_tokens)
        job_counter = Counter(job_tokens)

        intersection = set(profile_counter) & set(job_counter)

        if not intersection:
            return 0.0

        numerator = sum(
            profile_counter[token] * job_counter[token]
            for token in intersection
        )

        profile_norm = math.sqrt(
            sum(value * value for value in profile_counter.values())
        )
        job_norm = math.sqrt(
            sum(value * value for value in job_counter.values())
        )

        if profile_norm == 0 or job_norm == 0:
            return 0.0

        return numerator / (profile_norm * job_norm)

    def _skill_score(
        self,
        job: Dict[str, Any],
        profile: Dict[str, Any],
    ) -> float:
        profile_skills = self._extract_skills(profile)
        job_skills = self._extract_skills(job)

        if not profile_skills or not job_skills:
            return 0.0

        matched = profile_skills & job_skills
        return len(matched) / len(job_skills)

    def _title_score(
        self,
        job: Dict[str, Any],
        profile: Dict[str, Any],
    ) -> float:
        title = self._safe_text(job.get("title")).lower()

        if not title:
            return 0.0

        target_titles = self._as_list(
            profile.get("target_roles")
            or profile.get("preferred_roles")
            or profile.get("roles")
        )

        if target_titles:
            title_tokens = set(self._tokenize(title))
            scores = []

            for target in target_titles:
                target_tokens = set(self._tokenize(target))

                if not target_tokens:
                    continue

                overlap = len(title_tokens & target_tokens)
                scores.append(overlap / len(target_tokens))

            if scores:
                return min(1.0, max(scores))

        profile_text = self._profile_text(profile)
        profile_tokens = set(self._tokenize(profile_text))
        title_tokens = set(self._tokenize(title))

        if not profile_tokens or not title_tokens:
            return 0.0

        return len(profile_tokens & title_tokens) / len(title_tokens)

    def _experience_score(
        self,
        job: Dict[str, Any],
        profile: Dict[str, Any],
    ) -> float:
        required = self._extract_years(
            job.get("experience")
            or job.get("experience_required")
            or job.get("experience_level")
        )

        candidate = self._extract_years(
            profile.get("experience")
            or profile.get("years_of_experience")
            or profile.get("experience_years")
        )

        if required is None:
            return 1.0

        if candidate is None:
            return 0.5

        if candidate >= required:
            return 1.0

        if required == 0:
            return 1.0

        return max(0.0, candidate / required)

    def _location_score(
        self,
        job: Dict[str, Any],
        profile: Dict[str, Any],
    ) -> float:
        job_location = self._safe_text(
            job.get("location")
            or job.get("job_location")
        ).lower()

        if not job_location:
            return 0.5

        preferred_locations = self._as_list(
            profile.get("preferred_locations")
            or profile.get("locations")
            or profile.get("preferred_location")
        )

        if not preferred_locations:
            remote_preference = profile.get("remote")
            if remote_preference is True:
                preferred_locations = ["remote"]
            else:
                return 0.5

        job_tokens = set(self._tokenize(job_location))

        for location in preferred_locations:
            location_text = self._safe_text(location).lower()

            if location_text == "remote" and "remote" in job_location:
                return 1.0

            location_tokens = set(self._tokenize(location_text))

            if location_tokens and location_tokens & job_tokens:
                return 1.0

        if "remote" in job_location:
            return 0.8

        return 0.0

    def _extract_skills(self, data: Dict[str, Any]) -> set:
        raw_values = []

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
                raw_values.extend(value)
            elif value:
                raw_values.append(value)

        text_fields = [
            data.get("description"),
            data.get("title"),
            data.get("text"),
        ]

        raw_values.extend(
            value for value in text_fields if value
        )

        skills = set()

        for value in raw_values:
            if isinstance(value, str):
                tokens = self._tokenize(value)
                skills.update(tokens)

        return skills

    def _profile_text(self, profile: Dict[str, Any]) -> str:
        fields = [
            profile.get("summary"),
            profile.get("bio"),
            profile.get("skills"),
            profile.get("experience"),
            profile.get("projects"),
            profile.get("education"),
            profile.get("target_roles"),
            profile.get("preferred_roles"),
        ]

        return self._combine_values(fields)

    def _job_text(self, job: Dict[str, Any]) -> str:
        fields = [
            job.get("title"),
            job.get("description"),
            job.get("category"),
            job.get("skills"),
            job.get("technologies"),
            job.get("tags"),
        ]

        return self._combine_values(fields)

    def _combine_values(self, values: Sequence[Any]) -> str:
        parts = []

        for value in values:
            if isinstance(value, (list, tuple, set)):
                parts.extend(str(item) for item in value)
            elif isinstance(value, dict):
                parts.extend(str(item) for item in value.values())
            elif value is not None:
                parts.append(str(value))

        return " ".join(parts)

    def _tokenize(self, text: str) -> List[str]:
        tokens = re.findall(r"[a-zA-Z0-9+#.]+", text.lower())

        return [
            token
            for token in tokens
            if token not in self.stop_words and len(token) > 1
        ]

    def _extract_years(self, value: Any) -> Optional[float]:
        if value is None:
            return None

        if isinstance(value, (int, float)):
            return float(value)

        text = str(value).lower()

        if any(
            phrase in text
            for phrase in ("fresher", "entry level", "no experience")
        ):
            return 0.0

        matches = re.findall(r"\d+(?:\.\d+)?", text)

        if not matches:
            return None

        numbers = [float(number) for number in matches]

        if "month" in text and "year" not in text:
            return max(numbers) / 12

        return max(numbers)

    def _as_list(self, value: Any) -> List[str]:
        if value is None:
            return []

        if isinstance(value, str):
            return [value]

        if isinstance(value, (list, tuple, set)):
            return [
                str(item)
                for item in value
                if item is not None
            ]

        return [str(value)]

    def _safe_text(self, value: Any) -> str:
        if value is None:
            return ""

        if isinstance(value, (list, tuple, set)):
            return " ".join(str(item) for item in value)

        return str(value)