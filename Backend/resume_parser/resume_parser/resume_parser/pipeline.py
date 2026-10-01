"""
pipeline.py
===========
ResumePipeline: the single public entry point that mirrors the required flow

    Resume PDF
        -> CommonParser (parse ONCE)
        -> ParsedResume
        -> either:
             ATSOutputBuilder -> (+ Job Description) -> ATSScorer -> score/suggestions
             InterviewOutputBuilder -> InterviewQuestionGenerator -> questions/follow-ups

Callers should generally only import from here — the submodules
(parser/, outputs/, ats/, interview/) stay independently testable/importable
but this is the "front door" that guarantees parsing never happens twice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .ats.ats_scorer import ATSScorer, ATSScoreResult
from .interview.question_generator import InterviewQuestionGenerator, InterviewQuestionSet
from .models import ParsedResume
from .outputs.ats_output import ATSOutputBuilder, ATSResumeData
from .outputs.interview_output import InterviewOutputBuilder, InterviewResumeData
from .parser.common_parser import CommonResumeParser


@dataclass
class ATSResult:
    ats_data: ATSResumeData
    score_result: ATSScoreResult


@dataclass
class InterviewResult:
    interview_data: InterviewResumeData
    question_set: InterviewQuestionSet


class ResumePipeline:
    """
    Usage:
        pipeline = ResumePipeline()
        pipeline.load(pdf_path="Mukul_resume_drivewise.pdf")     # parses ONCE, cached

        ats_result = pipeline.run_ats(job_description=jd_text)
        interview_result = pipeline.run_interview()
    """

    def __init__(
        self,
        parser: Optional[CommonResumeParser] = None,
        ats_output_builder: Optional[ATSOutputBuilder] = None,
        interview_output_builder: Optional[InterviewOutputBuilder] = None,
        ats_scorer: Optional[ATSScorer] = None,
        interview_generator: Optional[InterviewQuestionGenerator] = None,
    ):
        self._parser = parser or CommonResumeParser()
        self._ats_output_builder = ats_output_builder or ATSOutputBuilder()
        self._interview_output_builder = interview_output_builder or InterviewOutputBuilder()
        self._ats_scorer = ats_scorer or ATSScorer()
        self._interview_generator = interview_generator or InterviewQuestionGenerator()

        self._parsed_resume: Optional[ParsedResume] = None

    # ------------------------------------------------------------------
    # Step 1: parse ONCE
    # ------------------------------------------------------------------

    def load(
        self,
        pdf_path: Optional[str] = None,
        pdf_bytes: Optional[bytes] = None,
        text: Optional[str] = None,
    ) -> ParsedResume:
        self._parsed_resume = self._parser.parse(pdf_path=pdf_path, pdf_bytes=pdf_bytes, text=text)
        return self._parsed_resume

    def load_parsed(self, parsed_resume: ParsedResume) -> ParsedResume:
        """
        Cache an already parsed resume instead of reading a document again.

        Services that persist a ``ParsedResume`` (for example the JobRix Django
        backend stores it as JSON next to the uploaded file) can feed it back
        here and still run the ATS / Interview flows through this facade, so the
        same PDF is never parsed twice.
        """
        self._parsed_resume = parsed_resume
        return self._parsed_resume

    @property
    def parsed_resume(self) -> ParsedResume:
        if self._parsed_resume is None:
            raise RuntimeError("Call pipeline.load(...) before running ATS or Interview flows.")
        return self._parsed_resume

    # ------------------------------------------------------------------
    # Step 2a: ATS flow (user selects ATS)
    # ------------------------------------------------------------------

    def run_ats(self, job_description: str) -> ATSResult:
        ats_data = self._ats_output_builder.build(self.parsed_resume)
        score_result = self._ats_scorer.score(ats_data, job_description)
        return ATSResult(ats_data=ats_data, score_result=score_result)

    # ------------------------------------------------------------------
    # Step 2b: Interview flow (user selects Interview)
    # ------------------------------------------------------------------

    def run_interview(self) -> InterviewResult:
        interview_data = self._interview_output_builder.build(self.parsed_resume)
        question_set = self._interview_generator.generate(interview_data)
        return InterviewResult(interview_data=interview_data, question_set=question_set)
