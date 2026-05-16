# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Does

Fetches GitHub repository metadata for the unfoldingWord GitHub organizations (`unfoldingWord`, `unfoldingWord-box3`, `unfoldingWord-dev`) and writes the results to an OpenDocument Spreadsheet (`.ods`). A second script splits that spreadsheet into per-sheet CSV files.

## Setup

```bash
python -m virtualenv .venv
source .venv/bin/activate
pip install -r requirements.txt   # pandas odfpy
cp env.sample .env                # then add your GITHUB_TOKEN
```

The token only needs read metadata permission on the target orgs.

## Running

```bash
# Generate the spreadsheet (takes several minutes — many API calls per repo)
python GitHubRepositoryFetcher.py

# Split the spreadsheet into per-sheet CSV files
python SheetToCSVConverter.py
```

## Architecture

Two top-level scripts, one shared library:

- **`GitHubRepositoryFetcher.py`** — orchestrator. Loops over the three orgs, calls `fetch_repositories_for_org()` (pagination via GitHub API Link headers), then enriches each repo dict in-place with dependents, contributors, last commit date, last release date, open PR count, and npm data. After all repos are fetched, calls `update_npmjs_dependencies()` to resolve cross-repo npm dependency relationships (including monorepo subpackages). Finally calls `write_ods()` to produce the `.ods` file directly using the ODF XML format (no odfpy write API — raw XML zipped).

- **`SheetToCSVConverter.py`** — reads `unfoldingword_repos.ods` via pandas/odf and writes one CSV per sheet.

- **`lib/utilities.py`** — all HTTP helpers and data-fetching functions. Key design points:
  - `github_request()` / `github_html_request()` — thin wrappers around `urllib` with auth headers and 429 retry logic (`urlopen_with_retry`).
  - npm data is only fetched for JS/TS repos with a non-private `package.json` whose npm package homepage/repository URL maps back to one of the unfoldingWord orgs (`npm_repo_is_from_uw()`).
  - Monorepo detection: if a repo's `package.json` has `workspaces`, or an `nx.json` is present, all nested `package.json` files are fetched and each subpackage is treated as a synthetic repo entry appended to the main list.
  - `fetch_repository_file()` tries `main` then `master` branch for file lookups.

## Key Conventions

- Repo data flows as plain `dict` objects (GitHub API JSON). Fields added by this script are kebab-case Python keys (`last_commit_date`, `open_prs_count`, etc.).
- The `.ods` file is written as raw ODF XML in a zip, not via odfpy's write API.
- `open_issues_count` comes from GitHub metadata (includes PRs); `open_prs_count` is fetched separately from the pulls API.
- `github_dependents` is scraped from GitHub's HTML dependents page, not the API — fragile if GitHub changes page layout.