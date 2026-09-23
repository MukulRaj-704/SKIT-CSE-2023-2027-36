import requests


JOBRIX_API_URL = "https://remotive.com/api/remote-jobs"


def fetch_jobrix_jobs(
    limit=100,
    category=None,
    search=None
):
    """
    Fetch job listings from the Remotive public jobs API.

    Args:
        limit: Maximum number of jobs to fetch.
        category: Optional job category such as 'software-dev'.
        search: Optional keyword to search in jobs.

    Returns:
        A list of normalized JobRix job dictionaries.
    """

    params = {
        "limit": limit
    }

    if category:
        params["category"] = category

    if search:
        params["search"] = search

    try:
        response = requests.get(
            JOBRIX_API_URL,
            params=params,
            timeout=20
        )

        response.raise_for_status()

        data = response.json()

        jobs = data.get("jobs", [])

        return [
            normalize_job(job)
            for job in jobs
        ]

    except requests.RequestException as error:
        raise RuntimeError(
            f"Failed to fetch JobRix jobs: {error}"
        )


def normalize_job(job):
    """
    Convert external job data into a consistent
    JobRix format.
    """

    return {
        "id": str(job.get("id", "")),
        "title": job.get("title", ""),
        "company": job.get("company_name", ""),
        "category": job.get("category", ""),
        "job_type": job.get("job_type", ""),
        "location": job.get(
            "candidate_required_location",
            ""
        ),
        "publication_date": job.get(
            "publication_date",
            ""
        ),
        "salary": job.get(
            "salary",
            ""
        ),
        "url": job.get(
            "url",
            ""
        ),
        "description": job.get(
            "description",
            ""
        ),
        "tags": job.get(
            "tags",
            []
        ),
        "source": "Remotive"
    }


def get_software_jobs(limit=100):
    """
    Fetch software development jobs.
    """

    return fetch_jobrix_jobs(
        limit=limit,
        category="software-dev"
    )


if __name__ == "__main__":
    jobs = get_software_jobs(limit=100)

    print(f"Fetched {len(jobs)} jobs")

    if jobs:
        print("\nFirst job:")
        print(jobs[0])