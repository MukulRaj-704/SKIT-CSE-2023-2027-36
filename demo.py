
from career_assistant.services.ingestion import ingest_jobrix_jobs
from career_assistant.services.chunking import chunk_documents
from career_assistant.services.vector_pipeline import VectorPipeline
from career_assistant.services.query_expander import QueryExpander
from career_assistant.services.job_matching import JobMatchingService
from career_assistant.services.skill_gap_analyzer import SkillGapAnalyzer


def main():
    print("\n" + "=" * 65)
    print("             JOBRIX KAI - WORKING DEMONSTRATION")
    print("=" * 65)

    profile = {
        "name": "Demo User",
        "skills": ["Python", "Django", "SQL"],
        "target_role": "Backend Developer",
        "experience": "1 year",
        "location": "Remote"
    }

    jobs = [
        {
            "id": "JOB101",
            "title": "Python Backend Developer",
            "company": "TechNova",
            "category": "Software Development",
            "job_type": "Full-time",
            "location": "Remote",
            "skills": ["Python", "Django", "SQL", "Docker"],
            "tags": ["Python", "Django", "SQL", "Docker"],
            "required_skills": ["Python", "Django", "SQL", "Docker"],
            "description": "Develop backend APIs using Python and Django. Work with SQL databases and Docker."
        },
        {
            "id": "JOB102",
            "title": "Full Stack Developer",
            "company": "CodeWorks",
            "category": "Software Development",
            "job_type": "Full-time",
            "location": "Remote",
            "skills": ["Python", "React", "JavaScript", "SQL"],
            "tags": ["Python", "React", "JavaScript", "SQL"],
            "required_skills": ["Python", "React", "JavaScript", "SQL"],
            "description": "Build full stack applications using Python, React, JavaScript and SQL."
        },
        {
            "id": "JOB103",
            "title": "Cloud Engineer",
            "company": "CloudTech",
            "category": "Software Development",
            "job_type": "Full-time",
            "location": "Remote",
            "skills": ["AWS", "Docker", "Kubernetes", "Linux"],
            "tags": ["AWS", "Docker", "Kubernetes", "Linux"],
            "required_skills": ["AWS", "Docker", "Kubernetes", "Linux"],
            "description": "Manage cloud infrastructure, containerization and deployment."
        }
    ]

    print("\n[1] JOB DATA INGESTION")

    documents = ingest_jobrix_jobs(jobs)

    print("Jobs received:", len(jobs))
    print("Documents created:", len(documents))

    print("\n[2] TEXT CHUNKING")

    chunks = chunk_documents(
        documents,
        chunk_size=40,
        overlap=8
    )

    print("Documents:", len(documents))
    print("Generated chunks:", len(chunks))

    print("\n[3] EMBEDDING AND VECTOR STORAGE")

    pipeline = VectorPipeline()

    stored = pipeline.add_documents(chunks)

    print("Documents indexed:", stored)
    print("Vector statistics:", pipeline.statistics())

    print("\n[4] QUERY EXPANSION")

    query = "Python backend developer jobs"

    expander = QueryExpander()

    expanded_queries = expander.expand_for_jobs(
        query,
        profile
    )

    print("Original query:", query)
    print("Expanded queries:")

    for item in expanded_queries:
        print(" -", item)

    print("\n[5] SEMANTIC JOB RETRIEVAL")

    retrieved = pipeline.retrieve_context(
        query=query,
        top_k=5
    )

    print("Retrieved documents:", len(retrieved))

    for item in retrieved:
        print(
            " -",
            item.get("metadata", {}).get("company", "Unknown"),
            "|",
            item.get("text", "")[:100]
        )

    print("\n[6] JOB RANKING AND MATCHING")

    matcher = JobMatchingService()

    matches = matcher.match(
        profile=profile,
        jobs=jobs,
        limit=3
    )

    for index, match in enumerate(matches, 1):
        ranking = match.get("ranking", {})
        result = match.get("match", {})

        print(f"\nRank #{index}")
        print("Job:", match.get("title"))
        print("Company:", match.get("company"))
        print("Score:", ranking.get("score"))
        print("Matched skills:", result.get("matched_skills"))
        print("Missing skills:", result.get("missing_skills"))
        print("Explanation:", result.get("explanation"))

    print("\n[7] SKILL GAP ANALYSIS")

    analyzer = SkillGapAnalyzer()

    analysis = analyzer.analyze(
        profile=profile,
        jobs=jobs
    )

    print(
        "Average skill coverage:",
        analysis["average_skill_coverage"],
        "%"
    )

    print("Priority skills:")

    for item in analysis["priority_skills"]:
        print(
            " -",
            item["skill"],
            "| Priority:",
            item["priority_score"],
            "| Job demand:",
            item["job_demand_percentage"],
            "%"
        )

    print("\nRecommendations:")

    for item in analysis["recommendations"]:
        print(" -", item["action"])

    print("\n" + "=" * 65)
    print("             KAI DEMONSTRATION COMPLETED")
    print("=" * 65)


if __name__ == "__main__":
    main()
