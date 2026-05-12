#!/usr/bin/env python3

import csv
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


ORG_NAME = [
    "unfoldingWord",
    "unfoldingWord-dev",
    "unfoldingWord-box3",
]
OUTPUT_FILE = "unfoldingword_repos.csv"
GITHUB_API_URL = f"https://api.github.com/orgs/{ORG_NAME}/repos"
ENV_FILE = ".env"


def load_env_file(env_file):
    if not os.path.exists(env_file):
        return

    with open(env_file, mode="r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()

            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if key and key not in os.environ:
                os.environ[key] = value


def github_request(url):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "unfoldingword-repo-list-script",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    github_token = os.getenv("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    request = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(request) as response:
            data = response.read()
            link_header = response.headers.get("Link")
            return data, link_header

    except urllib.error.HTTPError as error:
        if error.code == 403:
            reset_time = error.headers.get("X-RateLimit-Reset")
            if reset_time:
                reset_seconds = int(reset_time) - int(time.time())
                print(
                    f"GitHub rate limit exceeded. Try again in {max(reset_seconds, 0)} seconds.",
                    file=sys.stderr,
                )
            else:
                print("GitHub API returned 403 Forbidden.", file=sys.stderr)

        elif error.code == 404:
            print("Organization not found.", file=sys.stderr)

        else:
            print(f"GitHub API error: {error.code} {error.reason}", file=sys.stderr)

        raise


def get_next_page_url(link_header):
    if not link_header:
        return None

    links = link_header.split(",")

    for link in links:
        parts = link.strip().split(";")
        if len(parts) != 2:
            continue

        url_part = parts[0].strip()
        rel_part = parts[1].strip()

        if rel_part == 'rel="next"':
            return url_part.strip("<>")

    return None


def fetch_repositories_for_org(org_name):
    repos = []

    query_params = urllib.parse.urlencode({
        "per_page": 100,
        "type": "all",
        "sort": "updated",
        "direction": "desc",
    })

    github_api_url = f"https://api.github.com/orgs/{org_name}/repos"
    url = f"{github_api_url}?{query_params}"

    while url:
        print(f"Fetching: {url}")

        data, link_header = github_request(url)

        import json
        page_repos = json.loads(data.decode("utf-8"))

        repos.extend(page_repos)

        url = get_next_page_url(link_header)

    return repos


def fetch_repositories():
    repos = []

    for org_name in ORG_NAME:
        repos.extend(fetch_repositories_for_org(org_name))

    return repos


def write_csv(repos, output_file):
    with open(output_file, mode="w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)

        writer.writerow([
            "repo name",
            "language",
            "organization name",
            "repo url",
            "last edit date",
        ])

        for repo in repos:
            writer.writerow([
                repo.get("name", ""),
                repo.get("language") or "",
                repo.get("owner", {}).get("login", ""),
                repo.get("html_url", ""),
                repo.get("updated_at", ""),
            ])


def main():
    load_env_file(ENV_FILE)

    repos = fetch_repositories()
    write_csv(repos, OUTPUT_FILE)

    print()
    print(f"Created CSV: {OUTPUT_FILE}")
    print(f"Repositories written: {len(repos)}")


if __name__ == "__main__":
    main()
