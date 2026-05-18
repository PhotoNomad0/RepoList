from lib.utilities import write_rows_to_ods, is_true, months_old, is_empty, as_int, contains_any, load_repository_data, \
    write_list_to_csv

ODS_FILE = "unfoldingword_repos.ods"
SHEET_NAME = "Repositories"
CATEGORIZED_OUTPUT_CSV = "categorized_repos.ods"

SORT_ORDER = [
    "No longer used candidate",
    "Keep - externally used",
    "Keep - locally used",
    "Manual review",
    "Needs review",
    "Dead - archived",
]

NS = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
}


def determine_github_classification(row):
    """Classify a repository using repository cleanup rules."""
    repo_name = row.get("repo name", "")
    archived = is_true(row.get("archived"))
    npm_deprecated = is_true(row.get("npm is deprecated"))
    is_fork = is_true(row.get("is fork"))

    last_commit_months = months_old(row.get("last commit date"))
    last_release_months = months_old(row.get("last release date"))
    last_edit_months = months_old(row.get("last edit date"))
    npm_last_published_months = months_old(row.get("npmjs last published"))

    npm_used_by_empty = is_empty(row.get("npmjs used by"))
    github_dependents_empty = is_empty(row.get("github dependents"))
    npm_package_empty = is_empty(row.get("npmjs package name"))
    language_empty = is_empty(row.get("language"))

    github_downloads = as_int(row.get("github downloads"))
    github_release_count = as_int(row.get("github release count"))
    npm_downloads_last_year = as_int(row.get("npmjs downloads last year"))
    open_issues_count = as_int(row.get("open issues count"))
    open_prs_count = as_int(row.get("open prs count"))
    github_contributors = as_int(row.get("github contributors"))

    cleanup_terms = [
        "poc",
        "proof",
        "demo",
        "test",
        "sample",
        "example",
        "template",
        "old",
        "hackathon",
        "playground",
    ]
    replacement_terms = ["old", "legacy", "deprecated", "obsolete", "archive", "backup"]
    core_terms = [
        "gateway",
        "door43",
        "dcs",
        "translationcore",
        "tc-create",
        "obs-app",
        "bt-servant",
        "tx-job",
        "catalog",
        "content-validation",
        "scripture",
        "resource",
    ]

    has_local_use = not npm_used_by_empty
    has_github_dependents = not github_dependents_empty
    recently_active = last_commit_months is not None and last_commit_months <= 12

    if recently_active:
        return "Active", f"Last commit was within the last 12 months ({last_commit_months} months ago)."

    if has_local_use:
        return "Keep - locally used", "Repository is listed as used by an npm package."

    if has_github_dependents or npm_downloads_last_year >= 1000:
        return "Keep - externally used", f"Repository has GitHub dependents or at least 1,000 npm downloads in the last year ({npm_downloads_last_year} downloads)."

    if contains_any(repo_name, core_terms):
        return "Manual review", "Repository name contains a core project term."

    if archived:
        return "Dead - archived", "Repository is archived."

    if npm_deprecated and last_commit_months is not None and last_commit_months > 24:
        return "Dead - deprecated", f"Npm package is deprecated and the last commit is older than 24 months ({last_commit_months} months ago)."

    if open_issues_count >= 50:
        return "Manual review", f"Repository has at least 50 open issues ({open_issues_count} open issues)."

    if github_release_count >= 10 or github_downloads >= 100:
        return "Manual review", f"Repository has significant release history or GitHub downloads ({github_release_count} releases, {github_downloads} downloads)."

    if github_contributors >= 5:
        return "Manual review", f"Repository has at least 5 GitHub contributors ({github_contributors} contributors)."

    if (
        last_edit_months is not None
        and last_edit_months <= 12
        and last_commit_months is not None
        and last_commit_months > 36
    ):
        return "Manual review", f"Repository was edited recently ({last_edit_months} months ago) but has not had a commit in over 36 months ({last_commit_months} months ago)."

    if (
        last_commit_months is not None
        and last_commit_months > 60
        and not archived
        and npm_used_by_empty
        and github_dependents_empty
        and github_downloads == 0
        and github_release_count == 0
    ):
        return "Dead candidate", f"Repository has had no commits in over 60 months ({last_commit_months} months ago) and has no usage, downloads ({github_downloads}), or releases ({github_release_count})."

    if (
        is_fork
        and last_commit_months is not None
        and last_commit_months > 36
        and npm_used_by_empty
        and github_dependents_empty
        and github_downloads == 0
    ):
        return "Dead candidate", f"Repository is an old fork with no detected usage or downloads ({github_downloads} downloads), and the last commit was over 36 months ago ({last_commit_months} months ago)."

    if (
        contains_any(repo_name, cleanup_terms)
        and last_commit_months is not None
        and last_commit_months > 24
        and npm_used_by_empty
        and github_dependents_empty
    ):
        return "Dead candidate", f"Repository name suggests cleanup/test/demo content, it has no detected usage, and the last commit was over 24 months ago ({last_commit_months} months ago)."

    if (
        language_empty
        and github_release_count == 0
        and github_downloads == 0
        and npm_package_empty
        and last_commit_months is not None
        and last_commit_months > 36
    ):
        return "Dead candidate", f"Repository has no language, releases ({github_release_count}), downloads ({github_downloads}), or npm package, and is older than 36 months ({last_commit_months} months since last commit)."

    if (
        last_commit_months is not None
        and last_commit_months > 18
        and (
            not npm_used_by_empty
            or not github_dependents_empty
            or npm_downloads_last_year > 0
        )
    ):
        return "Stale but used", f"Repository has had no commits in over 18 months ({last_commit_months} months ago) but still has detected usage ({npm_downloads_last_year} npm downloads in the last year)."

    if (
        not npm_package_empty
        and npm_last_published_months is not None
        and npm_last_published_months > 18
        and not npm_deprecated
    ):
        return "Stale package", f"Npm package has not been published in over 18 months ({npm_last_published_months} months ago) and is not marked deprecated."

    if (
        last_commit_months is not None
        and last_commit_months > 12
        and (open_prs_count >= 5 or open_issues_count >= 20)
    ):
        return "Stale / neglected", f"Repository has had no commits in over 12 months ({last_commit_months} months ago) and has many open PRs or issues ({open_prs_count} PRs, {open_issues_count} issues)."

    if (
        last_commit_months is not None
        and last_commit_months <= 24
        and last_release_months is not None
        and last_release_months > 24
        and github_release_count > 0
    ):
        return "Stale release process", f"Repository has recent commits ({last_commit_months} months ago) but no release in over 24 months ({last_release_months} months ago), with {github_release_count} releases."

    if (
        last_commit_months is not None
        and last_commit_months > 18
        and not archived
    ):
        return "Stale", f"Repository has had no commits in over 18 months ({last_commit_months} months ago) and is not archived."

    if contains_any(repo_name, replacement_terms):
        return "No longer used candidate", "Repository name suggests it may be old, legacy, deprecated, obsolete, archived, or a backup."

    if (
        contains_any(repo_name, cleanup_terms)
        and last_commit_months is not None
        and last_commit_months > 12
    ):
        return "No longer used candidate", f"Repository name suggests cleanup/test/demo content and it has had no commits in over 12 months ({last_commit_months} months ago)."

    if is_fork and npm_used_by_empty and github_dependents_empty:
        return "No longer used candidate", "Repository is a fork with no detected npm or GitHub dependent usage."

    if (
        not npm_package_empty
        and npm_used_by_empty
        and github_dependents_empty
        and npm_downloads_last_year == 0
    ):
        return "No longer used candidate", f"Repository has an npm package but no detected usage or downloads in the last year ({npm_downloads_last_year} npm downloads)."

    return "Needs review", "Repository did not match any automatic classification rule."


def determine_npmjs_classification(row):
    """Classify a published npm module using npmjs lifecycle rules."""
    repo_name = row.get("repo name", "")
    npm_package_name = row.get("npmjs package name", "")

    npm_package_empty = is_empty(npm_package_name)
    npm_deprecated = is_true(row.get("npm is deprecated"))
    archived = is_true(row.get("archived"))

    npm_used_by_empty = is_empty(row.get("npmjs used by"))
    github_dependents_empty = is_empty(row.get("github dependents"))

    npm_downloads_last_year = as_int(row.get("npmjs downloads last year"))
    npm_last_published_months = months_old(row.get("npmjs last published"))

    replacement_terms = ["old", "legacy", "deprecated", "obsolete", "archive", "backup"]
    sensitive_or_build_terms = [
        "auth",
        "login",
        "token",
        "crypto",
        "security",
        "deploy",
        "build",
        "cli",
        "config",
        "eslint",
        "babel",
        "webpack",
        "rollup",
    ]

    if npm_package_empty:
        return "Needs review", "No npmjs package is published for this repository."

    if npm_deprecated:
        return "Deprecated npm package", "Npm package is already explicitly marked as deprecated."

    if contains_any(repo_name, sensitive_or_build_terms) or contains_any(npm_package_name, sensitive_or_build_terms):
        return (
            "Manual review - npm package",
            "Package or repository name suggests a security-sensitive, CLI, deployment, configuration, or build-tool package.",
        )

    if (
        not npm_used_by_empty
        or not github_dependents_empty
        or npm_downloads_last_year >= 1000
    ):
        return (
            "Keep - npm package in use",
            f"Package has detected local usage, GitHub dependents, or significant npm downloads ({npm_downloads_last_year} downloads in the last year).",
        )

    if archived:
        return (
            "Deprecate npm package candidate",
            "Package is backed by an archived repository and is not marked deprecated on npmjs.",
        )

    if (
        npm_used_by_empty
        and github_dependents_empty
        and npm_downloads_last_year == 0
    ):
        return (
            "Deprecate npm package candidate",
            "Published package has no detected local consumers, no GitHub dependents, and no npm download activity in the last year.",
        )

    if (
        npm_last_published_months is not None
        and npm_last_published_months > 24
        and npm_downloads_last_year < 100
        and npm_used_by_empty
    ):
        return (
            "Deprecate npm package candidate",
            f"Package has not been published in over 24 months ({npm_last_published_months} months ago), has fewer than 100 downloads in the last year ({npm_downloads_last_year}), and has no detected local consumers.",
        )

    if contains_any(repo_name, replacement_terms) or contains_any(npm_package_name, replacement_terms):
        return (
            "Deprecate npm package candidate",
            "Package or repository name suggests it may be old, legacy, deprecated, obsolete, archived, or a backup.",
        )

    if (
        npm_downloads_last_year >= 1
        and npm_downloads_last_year < 1000
        and npm_used_by_empty
    ):
        return (
            "Manual review - npm package",
            f"Package has low but nonzero npm usage ({npm_downloads_last_year} downloads in the last year) and no detected local consumers.",
        )

    return (
        "Manual review - npm package",
        "Published npm package did not match any automatic npm lifecycle classification rule.",
    )


def main():
    headers, data_rows = load_repository_data()

    if "classification" not in headers:
        headers.append("classification")

    if "classification reason" not in headers:
        headers.append("classification reason")

    if "npmjs classification" not in headers:
        headers.append("npmjs classification")

    if "npmjs classification reason" not in headers:
        headers.append("npmjs classification reason")

    for row in data_rows:
        print(row)
        classification, classification_reason = determine_github_classification(row)
        npmjs_classification, npmjs_classification_reason = determine_npmjs_classification(row)

        row["classification"] = classification
        row["classification reason"] = classification_reason
        row["npmjs classification"] = npmjs_classification
        row["npmjs classification reason"] = npmjs_classification_reason

    # data_rows = [
    #     row for row in data_rows
    #     if row["classification"] != "Dead - archived"
    # ]

    sort_rank = {classification: index for index, classification in enumerate(SORT_ORDER)}
    data_rows.sort(
        key=lambda row: (
            sort_rank.get(row["classification"], len(SORT_ORDER)),
            str(row.get("repo name", "")).lower(),
        )
    )

    classifications = sorted({row["classification"] for row in data_rows})

    print("Classifications found:")
    for classification in classifications:
        print(f"- {classification}")

    write_list_to_csv(CATEGORIZED_OUTPUT_CSV, headers, data_rows)
    write_rows_to_ods("categorized_repos.ods", "Repositories", data_rows)


if __name__ == "__main__":
    main()
