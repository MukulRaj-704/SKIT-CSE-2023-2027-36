from career_assistant.data.jobrix_data import get_software_jobs

jobs = get_software_jobs(limit=20)

print("\nTotal jobs fetched:", len(jobs))
print("\nTOP 10 JOBS\n")

for i, job in enumerate(jobs[:10], 1):
    print(f"{i}. {job['title']} | {job['company']} | {job['location']}")
