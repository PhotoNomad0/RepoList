import base64
import csv
import datetime
import json
import os
import pandas as pd
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import xml.etree.ElementTree as ET

NS = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
}

def read_ods_sheets(input_file):
    """
    Read all sheets from an ODS file.

    Returns:
        dict[str, pandas.DataFrame]: Mapping of sheet names to DataFrames.
    """
    return pd.read_excel(
        input_file,
        sheet_name=None,
        engine="odf"
    )


def write_ods_sheets(output_file, sheets):
    """
    Write one or more sheets to an ODS file.

    Args:
        output_file (str): Path to the ODS file to write.
        sheets (dict[str, pandas.DataFrame] | pandas.DataFrame): Sheet data to write.
            If a single DataFrame is provided, it is written to a sheet named "Sheet1".
    """
    if isinstance(sheets, pd.DataFrame):
        sheets = {"Sheet1": sheets}

    with pd.ExcelWriter(output_file, engine="odf") as writer:
        for sheet_name, dataframe in sheets.items():
            dataframe.to_excel(
                writer,
                sheet_name=str(sheet_name)[:31],
                index=False,
            )


def write_rows_to_ods(output_file, sheet_name, rows):
    """
    Write a list of dictionaries to a single-sheet ODS file.

    Args:
        output_file (str): Path to the ODS file to write.
        sheet_name (str): Name of the sheet.
        rows (list[dict]): Rows to write.
    """
    dataframe = pd.DataFrame(rows)
    write_ods_sheets(output_file, {sheet_name: dataframe})


def safe_filename(name):
    """
    Convert a sheet name into a safe filename.
    """
    name = re.sub(r'[\\/*?:"<>|]', "_", name)
    name = name.strip()
    return name or "sheet"


def urlopen_with_retry(request, retries=1, retry_delay_seconds=5):
    for attempt in range(retries + 1):
        try:
            return urllib.request.urlopen(request)
        except urllib.error.HTTPError as error:
            if error.code == 429 and attempt < retries:
                print(
                    f"Received 429 Too Many Requests. Retrying in {retry_delay_seconds} second...",
                    file=sys.stderr,
                )
                time.sleep(retry_delay_seconds)
                continue

            raise


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

def github_request(url, allow_not_found=False, allow_conflict=False):
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
        with urlopen_with_retry(request) as response:
            data = response.read()
            link_header = response.headers.get("Link")
            return data, link_header

    except urllib.error.HTTPError as error:
        if error.code == 404 and allow_not_found:
            return None, None

        if error.code == 409 and allow_conflict:
            return None, None

        if error.code == 403:
            reset_time = error.headers.get("X-RateLimit-Reset")
            if reset_time:
                reset_seconds = int(reset_time) - int(time.time())
                print(
                    f"GitHub rate limit exceeded. Try again in {max(reset_seconds, 0)} seconds.",
                    file=sys.stderr,
                )
            else:
                print(f"GitHub API returned 403 Forbidden. (URL: {url})", file=sys.stderr)

        elif error.code == 404:
            print(f"Organization not found. (URL: {url})", file=sys.stderr)

        else:
            print(f"GitHub API error: {error.code} {error.reason} (URL: {url})", file=sys.stderr)

        raise


def github_html_request(url, allow_not_found=False):
    headers = {
        "Accept": "text/html",
        "User-Agent": "unfoldingword-repo-list-script",
    }

    github_token = os.getenv("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    request = urllib.request.Request(url, headers=headers)

    try:
        with urlopen_with_retry(request) as response:
            return response.read().decode("utf-8")

    except urllib.error.HTTPError as error:
        if error.code == 404 and allow_not_found:
            return None

        print(
            f"GitHub HTML request error: {error.code} {error.reason}",
            file=sys.stderr,
        )
        return None

    except urllib.error.URLError as error:
        print(
            f"GitHub HTML request failed: {error.reason} (URL: {url})",
            file=sys.stderr,
        )
        return None
    

def fetch_repository_dependents(repo):
    owner = repo.get("owner", {}).get("login")
    repo_name = repo.get("name")

    if not owner or not repo_name:
        return []

    dependents = []
    seen_dependents = set()
    next_url = (
        f"https://github.com/{urllib.parse.quote(owner, safe='')}/"
        f"{urllib.parse.quote(repo_name, safe='')}/network/dependents?"
        f"{urllib.parse.urlencode({'dependent_type': 'REPOSITORY'})}"
    )

    while next_url:
        print(f"Fetching dependents: {owner}/{repo_name}")

        html = github_html_request(next_url, allow_not_found=True)
        if not html:
            break

        repo_links = re.findall(r'href="/([^"/]+/[^"/]+)"', html)

        for dependent in repo_links:
            if dependent == f"{owner}/{repo_name}":
                continue

            if dependent in seen_dependents:
                continue

            seen_dependents.add(dependent)
            dependents.append(dependent)

        next_match = re.search(r'href="([^"]+)"[^>]*>\s*Next\s*</a>', html)
        if not next_match:
            break

        next_url = urllib.parse.urljoin("https://github.com", next_match.group(1))

    return dependents


def fetch_repository_contributors(repo):
    owner = repo.get("owner", {}).get("login")
    repo_name = repo.get("name")

    if not owner or not repo_name:
        return []

    contributors = []
    seen_contributors = set()
    next_url = (
        f"https://api.github.com/repos/"
        f"{urllib.parse.quote(owner, safe='')}/"
        f"{urllib.parse.quote(repo_name, safe='')}/contributors?"
        f"{urllib.parse.urlencode({'per_page': 100, 'anon': 'true'})}"
    )

    while next_url:
        print(f"Fetching contributors: {owner}/{repo_name}")

        data, link_header = github_request(next_url, allow_not_found=True)
        if not data:
            break

        decoded_data = data.decode("utf-8").strip()
        if not decoded_data:
            break

        try:
            page_contributors = json.loads(decoded_data)
        except json.JSONDecodeError as error:
            print(
                f"Could not parse contributors response for {owner}/{repo_name}: {error}",
                file=sys.stderr,
            )
            break

        if not isinstance(page_contributors, list):
            message = page_contributors.get("message", "Unexpected contributors response")
            print(
                f"Could not fetch contributors for {owner}/{repo_name}: {message}",
                file=sys.stderr,
            )
            break

        for contributor in page_contributors:
            contributor_name = (
                contributor.get("login")
                or contributor.get("name")
                or contributor.get("email")
            )

            if not contributor_name:
                continue

            if contributor_name in seen_contributors:
                continue

            seen_contributors.add(contributor_name)
            contributors.append(contributor_name)

        next_url = get_next_page_url(link_header)

    return contributors


def fetch_repository_last_commit_date(repo):
    owner = repo.get("owner", {}).get("login")
    repo_name = repo.get("name")
    default_branch = repo.get("default_branch")

    if not owner or not repo_name:
        return ""

    query_params = {
        "per_page": 1,
    }

    if default_branch:
        query_params["sha"] = default_branch

    commits_url = (
        f"https://api.github.com/repos/"
        f"{urllib.parse.quote(owner, safe='')}/"
        f"{urllib.parse.quote(repo_name, safe='')}/commits?"
        f"{urllib.parse.urlencode(query_params)}"
    )

    print(f"Fetching latest commit: {owner}/{repo_name}")

    data, _ = github_request(commits_url, allow_not_found=True, allow_conflict=True)
    if not data:
        return ""

    commits = json.loads(data.decode("utf-8"))
    if not commits:
        return ""

    return (
        commits[0]
        .get("commit", {})
        .get("committer", {})
        .get("date", "")
    )


def fetch_repository_last_release_date(repo):
    owner = repo.get("owner", {}).get("login")
    repo_name = repo.get("name")

    if not owner or not repo_name:
        return ""

    releases_url = (
        f"https://api.github.com/repos/"
        f"{urllib.parse.quote(owner, safe='')}/"
        f"{urllib.parse.quote(repo_name, safe='')}/releases/latest"
    )

    print(f"Fetching latest release: {owner}/{repo_name}")

    data, _ = github_request(releases_url, allow_not_found=True)
    if not data:
        return ""

    release = json.loads(data.decode("utf-8"))
    return release.get("published_at") or release.get("created_at", "")


def fetch_repository_open_prs_count(repo):
    owner = repo.get("owner", {}).get("login")
    repo_name = repo.get("name")

    if not owner or not repo_name:
        return ""

    pulls_url = (
        f"https://api.github.com/repos/"
        f"{urllib.parse.quote(owner, safe='')}/"
        f"{urllib.parse.quote(repo_name, safe='')}/pulls?"
        f"{urllib.parse.urlencode({'state': 'open', 'per_page': 1})}"
    )

    print(f"Fetching open PR count: {owner}/{repo_name}")

    data, link_header = github_request(pulls_url, allow_not_found=True)
    if not data:
        return ""

    last_page_match = re.search(r'[?&]page=(\d+)>; rel="last"', link_header or "")
    if last_page_match:
        return int(last_page_match.group(1))

    pulls = json.loads(data.decode("utf-8"))
    return len(pulls)


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


def fetch_repository_file(repo, file_path):
    owner = repo.get("owner", {}).get("login")
    repo_name = repo.get("name")

    if not owner or not repo_name:
        return None

    for branch_name in ("main", "master"):
        file_url = (
            f"https://api.github.com/repos/"
            f"{urllib.parse.quote(owner, safe='')}/"
            f"{urllib.parse.quote(repo_name, safe='')}/"
            f"contents/{urllib.parse.quote(file_path, safe='/')}?"
            f"{urllib.parse.urlencode({'ref': branch_name})}"
        )

        print(f"Fetching {file_path}: {owner}/{repo_name}@{branch_name}")

        data, _ = github_request(file_url, allow_not_found=True)
        if data is None:
            continue

        repository_file = json.loads(data.decode("utf-8"))
        content = repository_file.get("content", "")

        if content:
            return content

    return None


def fetch_repository_json_file(repo, file_path):
    encoded_content = fetch_repository_file(repo, file_path)

    if encoded_content:
        decoded_content = base64.b64decode(encoded_content).decode("utf-8")
        return json.loads(decoded_content)

    return None


def fetch_package_json(repo):
    package_json = fetch_repository_json_file(repo, "package.json")
    return package_json


def fetch_package_json_files(repo):
    owner = repo.get("owner", {}).get("login")
    repo_name = repo.get("name")
    default_branch = repo.get("default_branch")

    if not owner or not repo_name or not default_branch:
        return []

    tree_url = (
        f"https://api.github.com/repos/"
        f"{urllib.parse.quote(owner, safe='')}/"
        f"{urllib.parse.quote(repo_name, safe='')}/"
        f"git/trees/"
        f"{urllib.parse.quote(default_branch, safe='')}?"
        f"{urllib.parse.urlencode({'recursive': '1'})}"
    )

    print(f"Fetching recursive file tree: {owner}/{repo_name}@{default_branch}")

    data, _ = github_request(tree_url, allow_not_found=True)
    if data is None:
        return []

    tree_data = json.loads(data.decode("utf-8"))
    package_files = []

    for item in tree_data.get("tree", []):
        if item.get("type") != "blob":
            continue

        path = item.get("path", "")

        if path.endswith("package.json"):
            package_files.append({
                "path": path,
                "url": (
                    f"https://github.com/{owner}/{repo_name}/blob/"
                    f"{urllib.parse.quote(default_branch, safe='')}/{path}"
                ),
            })

    return package_files

def fetch_nx_json(repo):
    return fetch_repository_json_file(repo, "nx.json")


def fetch_npmjs_package_metadata(package_name):
    package_url = (
        "https://registry.npmjs.org/"
        f"{urllib.parse.quote(package_name, safe='@')}"
    )

    print(f"Fetching npm package metadata: {package_name}")

    request = urllib.request.Request(
        package_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "unfoldingword-repo-list-script",
        },
    )

    try:
        with urlopen_with_retry(request) as response:
            return json.loads(response.read().decode("utf-8"))

    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None

        print(
            f"npm registry error for {package_name}: {error.code} {error.reason}",
            file=sys.stderr,
        )
        return None


def npm_repo_is_from_uw(package_metadata, ORG_NAMES):
    if package_metadata is None:
        return False

    homepage = package_metadata.get("homepage") or ""
    repository = package_metadata.get("repository") or {}

    if isinstance(repository, dict):
        repository_url = repository.get("url") or ""
    else:
        repository_url = str(repository) if repository else ""

    homepage = homepage.lower()
    repository_url = repository_url.lower()

    in_uw_org = any(org_name.lower() in homepage or org_name.lower() in repository_url for org_name in ORG_NAMES)
    return in_uw_org


def fetch_npmjs_last_published(package_metadata):
    if package_metadata is None:
        return ""

    time_metadata = package_metadata.get("time") or {}
    latest_version = package_metadata.get("dist-tags", {}).get("latest")

    if latest_version:
        return time_metadata.get(latest_version, "")

    published_dates = [
        published_at
        for version, published_at in time_metadata.items()
        if version not in ("created", "modified")
    ]

    time.sleep(0.25)

    return max(published_dates, default="")


def fetch_npmjs_is_deprecated(package_metadata):
    if package_metadata is None:
        return ""

    latest_version = package_metadata.get("dist-tags", {}).get("latest")
    versions = package_metadata.get("versions") or {}

    if latest_version and latest_version in versions:
        return bool(versions[latest_version].get("deprecated"))

    return bool(package_metadata.get("deprecated"))


def fetch_npmjs_download_count(package_name, period="last-month"):
    if not package_name:
        return ""

    downloads_url = (
        "https://api.npmjs.org/downloads/point/"
        f"{urllib.parse.quote(period, safe='')}/"
        f"{urllib.parse.quote(package_name, safe='@')}"
    )

    print(f"Fetching npm download count: {package_name}")

    request = urllib.request.Request(
        downloads_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "unfoldingword-repo-list-script",
        },
    )

    try:
        with urlopen_with_retry(request) as response:
            download_data = json.loads(response.read().decode("utf-8"))
            return download_data.get("downloads", "")

    except urllib.error.HTTPError as error:
        if error.code == 404:
            return ""

        print(
            f"npm downloads API error for {package_name}: {error.code} {error.reason}",
            file=sys.stderr,
        )
        return ""


def fetch_npmjs_download_count(package_name, period="last-month"):
    if not package_name:
        return ""

    downloads_url = (
        "https://api.npmjs.org/downloads/point/"
        f"{urllib.parse.quote(period, safe='')}/"
        f"{urllib.parse.quote(package_name, safe='@')}"
    )

    print(f"Fetching npm download count: {package_name}")

    request = urllib.request.Request(
        downloads_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "unfoldingword-repo-list-script",
        },
    )

    try:
        with urlopen_with_retry(request) as response:
            download_data = json.loads(response.read().decode("utf-8"))
            return download_data.get("downloads", "")

    except urllib.error.HTTPError as error:
        if error.code == 404:
            return ""

        print(
            f"npm downloads API error for {package_name}: {error.code} {error.reason}",
            file=sys.stderr,
        )
        return ""


def fetch_npmjs_total_download_count(package_name, package_metadata):
    if not package_name or package_metadata is None:
        return ""

    created_at = (package_metadata.get("time") or {}).get("created")
    if not created_at:
        return ""

    try:
        start_date = datetime.date.fromisoformat(created_at[:10])
    except ValueError:
        return ""

    end_date = datetime.date.today()
    total_downloads = 0
    current_start = start_date

    print(f"Fetching total npm download count: {package_name}")

    while current_start <= end_date:
        current_end = min(
            current_start + datetime.timedelta(days=364),
            end_date,
            )

        period = f"{current_start.isoformat()}:{current_end.isoformat()}"
        downloads_url = (
            "https://api.npmjs.org/downloads/range/"
            f"{urllib.parse.quote(period, safe=':')}/"
            f"{urllib.parse.quote(package_name, safe='@')}"
        )

        request = urllib.request.Request(
            downloads_url,
            headers={
                "Accept": "application/json",
                "User-Agent": "unfoldingword-repo-list-script",
            },
        )

        try:
            with urlopen_with_retry(request) as response:
                download_data = json.loads(response.read().decode("utf-8"))
                daily_downloads = sum(day.get("downloads", 0) for day in download_data.get("downloads", []))
                total_downloads += daily_downloads

        except urllib.error.HTTPError as error:
            if error.code == 404:
                return ""

            print(
                f"npm downloads API error for {package_name}: {error.code} {error.reason}",
                file=sys.stderr,
            )
            return ""

        current_start = current_end + datetime.timedelta(days=1)

    return total_downloads


def fetch_repository_github_downloads(repo):
    """
    Fetches the total GitHub release asset download count and release count for a repository.
    """
    downloads = 0
    release_count = 0
    releases_url = repo.get("releases_url", "").replace("{/id}", "")

    if not releases_url:
        return downloads, release_count

    query_params = urllib.parse.urlencode({
        "per_page": 100,
    })
    url = f"{releases_url}?{query_params}"

    while url:
        print(f"Fetching GitHub release downloads: {url}")

        data, link_header = github_request(url)
        releases = json.loads(data.decode("utf-8"))
        release_count += len(releases)

        for release in releases:
            for asset in release.get("assets", []):
                downloads += asset.get("download_count", 0)

        url = get_next_page_url(link_header)

    return downloads, release_count

def get_cell_text(cell):
    """Extract plain text from an ODS table cell."""
    parts = []

    for paragraph in cell.findall(".//text:p", NS):
        text = "".join(paragraph.itertext())
        parts.append(text)

    return "\n".join(parts)


def read_ods_sheet(filename, sheet_name):
    """Read rows from a named sheet in an ODS file.

    This function extracts tabular data from an OpenDocument Spreadsheet (ODS) file
    by parsing its internal XML structure. It handles ODS-specific features like
    repeated rows/columns and normalizes the output to a consistent rectangular grid.

    Args:
        filename (str): Path to the ODS file to read.
        sheet_name (str): Name of the sheet to extract from the ODS file.

    Returns:
        list[list[str]]: A 2D list representing the sheet data, where each inner list
                         is a row of cells. All rows have the same width (determined
                         by the first non-empty row, typically the header).

    Raises:
        ValueError: If the specified sheet_name is not found in the ODS file.

    Processing Details:
        1. Extracts and parses the content.xml file from the ODS ZIP archive
        2. Locates the sheet matching the provided sheet_name
        3. For each row in the sheet:
           - Handles ODS row repetition (number-rows-repeated attribute)
           - For each cell:
             * Extracts text content using get_cell_text()
             * Handles ODS column repetition (number-columns-repeated attribute)
             * Prevents excessive empty column repetition in the header row
             * Constrains cells to the established header width for data rows
           - First row establishes header_width by trimming trailing empty cells
           - Subsequent rows are padded or truncated to match header_width
        4. Returns all rows with consistent column counts

    Note:
        - Empty cells are represented as empty strings ("")
        - The first row determines the number of columns for all subsequent rows
        - ODS files may contain repeated row/column attributes for compression;
          this function expands them to their full representation
    """

    # ODS files are ZIP archives. The spreadsheet data lives in content.xml,
    # so open the archive, read that XML file, and parse it into an ElementTree.
    with zipfile.ZipFile(filename, "r") as ods:
        with ods.open("content.xml") as content:
            tree = ET.parse(content)

    root = tree.getroot()

    # Find every table element in the document. Each table represents one sheet.
    sheets = root.findall(".//table:table", NS)

    for sheet in sheets:
        # ODS stores the sheet name as a namespaced table:name attribute.
        name = sheet.attrib.get(f"{{{NS['table']}}}name")

        # Skip sheets until we find the one the caller requested.
        if name != sheet_name:
            continue

        rows = []

        # The first row is treated as the header. Its width is used to normalize
        # all following rows so CSV output has a consistent number of columns.
        header_width = None

        for row in sheet.findall("table:table-row", NS):
            # ODS may compress identical consecutive rows using
            # table:number-rows-repeated. Default to 1 when it is not present.
            repeated_rows = int(
                row.attrib.get(f"{{{NS['table']}}}number-rows-repeated", "1")
            )

            row_data = []

            for cell in row.findall("table:table-cell", NS):
                # ODS may also compress identical consecutive cells using
                # table:number-columns-repeated.
                repeated_cols = int(
                    cell.attrib.get(f"{{{NS['table']}}}number-columns-repeated", "1")
                )

                # Extract the displayed text from the cell's XML content.
                value = get_cell_text(cell)

                # In the header row, trailing blank cells can be stored as a huge
                # repeated empty range. Keep each empty header cell to one column
                # so the header width does not become artificially large.
                if header_width is None and value == "":
                    repeated_cols = 1

                # After the header width is known, do not read more columns than
                # the header defines. Extra spreadsheet cells are ignored.
                if header_width is not None:
                    remaining_cols = header_width - len(row_data)
                    if remaining_cols <= 0:
                        break
                    repeated_cols = min(repeated_cols, remaining_cols)

                # Expand repeated columns into regular cell values so callers get
                # a normal list of strings instead of ODS compression metadata.
                for _ in range(repeated_cols):
                    row_data.append(value)

            if header_width is None:
                # The first row establishes the number of columns. Remove trailing
                # blanks so accidental empty spreadsheet columns are not included.
                while row_data and row_data[-1] == "":
                    row_data.pop()

                header_width = len(row_data)

            else:
                # Keep data rows rectangular: trim rows that are too wide and pad
                # rows that are too short with empty strings.
                row_data = row_data[:header_width]

                while len(row_data) < header_width:
                    row_data.append("")

            # Expand repeated rows after the row has been normalized. Use copy()
            # so each output row is an independent list.
            for _ in range(repeated_rows):
                rows.append(row_data.copy())

        return rows

    raise ValueError(f"Sheet not found: {sheet_name}")


def write_list_to_csv(output_csv, headers, data):
    """Write row dictionaries to a CSV file, flattening list values."""
    with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
        if data:
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            writer.writeheader()

            for row in data:
                flattened_row = {}
                for key, value in row.items():
                    if isinstance(value, list):
                        flattened_row[key] = ', '.join(value)
                    else:
                        flattened_row[key] = value
                writer.writerow(flattened_row)

            print(f"Data saved to {output_csv}")


def load_repository_data(ODS_FILE, SHEET_NAME):
    """Load repository rows from the configured ODS sheet and normalize comma-separated values."""
    rows = read_ods_sheet(ODS_FILE, SHEET_NAME)

    headers = rows[0]
    data = [dict(zip(headers, row)) for row in rows[1:]]

    for row in data:
        for key, value in row.items():
            if isinstance(value, str) and ',' in value:
                row[key] = [item.strip() for item in value.split(',')]

    return headers, data


def is_empty(value):
    """Return True when a spreadsheet value is empty."""
    if value is None:
        return True

    if isinstance(value, list):
        return len([item for item in value if str(item).strip()]) == 0

    return str(value).strip() == ""


def is_true(value):
    """Return True for common spreadsheet boolean values."""
    return str(value).strip().lower() in {"true", "yes", "1", "y"}


def as_int(value):
    """Convert spreadsheet numeric values to int, treating blanks as zero."""
    if is_empty(value):
        return 0

    if isinstance(value, list):
        value = value[0] if value else ""

    try:
        return int(float(str(value).replace(",", "").strip()))
    except ValueError:
        return 0


def parse_date(value):
    """Parse common spreadsheet date formats."""
    if is_empty(value):
        return None

    if isinstance(value, list):
        value = value[0] if value else ""

    value = str(value).strip()

    for date_format in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.datetime.strptime(value[:19], date_format)
        except ValueError:
            continue

    return None


def months_old(value):
    """Return approximate age in months for a date value."""
    date_value = parse_date(value)

    if date_value is None:
        return None

    today = datetime.datetime.today()
    return (today.year - date_value.year) * 12 + today.month - date_value.month


def contains_any(value, terms):
    """Return True when value contains any term."""
    return any(term in str(value).lower() for term in terms)


