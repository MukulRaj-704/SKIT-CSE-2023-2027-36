import sys
from pprint import pprint

from career_assistant.data.jobrix_data import get_software_jobs
from career_assistant.services.ingestion import ingest_jobrix_jobs
from career_assistant.services.chunking import chunk_documents
from career_assistant.services.vector_pipeline import VectorPipeline
from career_assistant.services.query_expander import QueryExpander
from career_assistant.services.job_matching import JobMatchingService
from career_assistant.services.skill_gap_analyzer import SkillGapAnalyzer
from career_assistant.services.assistant import CareerAssistant


def main():
    print("\n====================================")
    print("       JOBRIX - KAI ASSISTANT")
    print("====================================")

    print("\n[1/5] Loading your career profile...")

    name = input("Your name: ").strip() or "JobRix User"
    skills = input("Your skills (comma separated): ").split(",")
    role = input("Target job role: ").strip() or "Software Developer"
    experience = input("Experience: ").strip() or "Fresher"
    location = input("Preferred location: ").strip() or "Remote"

    profile = {
        "name": name,
        "skills": [s.strip() for s in skills if s.strip()],
        "target_role": role,
        "experience": experience,
        "location": location
    }

    print("\n[2/5] Fetching live jobs from Remotive...")

    jobs = get_software_jobs(limit=100)

    if not jobs:
        print("No jobs received from the API.")
        return

    print("Jobs fetched:", len(jobs))

    print("\n[3/5] Running job matching and skill gap analysis...")

    matcher = JobMatchingService()
    match_results = matcher.match(profile, jobs, limit=5)

    analyzer = SkillGapAnalyzer()
    skill_report = analyzer.analyze(profile, jobs=jobs)

    print("\nTOP JOB MATCH RESULTS")
    pprint(match_results, sort_dicts=False)

    print("\nSKILL GAP REPORT")
    pprint(skill_report, sort_dicts=False)

    print("\n[4/5] Building KAI knowledge retrieval...")

    documents = ingest_jobrix_jobs(jobs)
    chunks = chunk_documents(documents)

    pipeline = VectorPipeline()
    pipeline.add_documents(chunks)

    expander = QueryExpander()

    print("Indexed chunks:", pipeline.count())

    print("\n[5/5] Connecting Gemini-powered KAI...")

    assistant = CareerAssistant()

    user_context = {
        "profile": profile,
        "job_matching_results": match_results,
        "skill_gap_report": skill_report,
        "available_job_count": len(jobs)
    }

    history = []

    print("\n====================================")
    print(" KAI IS READY!")
    print(" Type 'exit' to close the assistant.")
    print("====================================")

    while True:
        query = input("\nYou: ").strip()

        if query.lower() in ("exit", "quit", "bye"):
            print("\nKAI: Goodbye! Keep growing with JobRix.")
            break

        if not query:
            continue

        try:
            expanded_queries = expander.expand_for_jobs(
                query,
                profile
            )

            search_query = " ".join(expanded_queries[:4])

            retrieved_documents = pipeline.retrieve_context(
                search_query,
                top_k=5
            )

            response = assistant.generate_response(
                query=query,
                retrieved_documents=retrieved_documents,
                conversation_history=history,
                user_context=user_context
            )

            print("\nKAI:", response)

            history.append({
                "role": "user",
                "content": query
            })

            history.append({
                "role": "assistant",
                "content": response
            })

        except Exception as error:
            print("\nKAI Error:", error)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nKAI stopped.")
    except Exception as error:
        print("\nApplication error:", error)
        sys.exit(1)
