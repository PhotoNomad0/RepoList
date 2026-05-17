import csv
from datetime import datetime
import zipfile
import xml.etree.ElementTree as ET

from lib.utilities import write_rows_to_ods

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


def load_repository_data():
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
            return datetime.strptime(value[:19], date_format)
        except ValueError:
            continue

    return None


def months_old(value):
    """Return approximate age in months for a date value."""
    date_value = parse_date(value)

    if date_value is None:
        return None

    today = datetime.today()
    return (today.year - date_value.year) * 12 + today.month - date_value.month


def contains_any(value, terms):
    """Return True when value contains any term."""
    return any(term in str(value).lower() for term in terms)


def determine_classification(row):
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
        return "Active"

    if has_local_use:
        return "Keep - locally used"

    if has_github_dependents or npm_downloads_last_year >= 1000:
        return "Keep - externally used"

    if contains_any(repo_name, core_terms):
        return "Manual review"

    if archived:
        return "Dead - archived"

    if npm_deprecated and last_commit_months is not None and last_commit_months > 24:
        return "Dead - deprecated"

    if open_issues_count >= 50:
        return "Manual review"

    if github_release_count >= 10 or github_downloads >= 100:
        return "Manual review"

    if github_contributors >= 5:
        return "Manual review"

    if (
        last_edit_months is not None
        and last_edit_months <= 12
        and last_commit_months is not None
        and last_commit_months > 36
    ):
        return "Manual review"

    if (
        last_commit_months is not None
        and last_commit_months > 60
        and not archived
        and npm_used_by_empty
        and github_dependents_empty
        and github_downloads == 0
        and github_release_count == 0
    ):
        return "Dead candidate"

    if (
        is_fork
        and last_commit_months is not None
        and last_commit_months > 36
        and npm_used_by_empty
        and github_dependents_empty
        and github_downloads == 0
    ):
        return "Dead candidate"

    if (
        contains_any(repo_name, cleanup_terms)
        and last_commit_months is not None
        and last_commit_months > 24
        and npm_used_by_empty
        and github_dependents_empty
    ):
        return "Dead candidate"

    if (
        language_empty
        and github_release_count == 0
        and github_downloads == 0
        and npm_package_empty
        and last_commit_months is not None
        and last_commit_months > 36
    ):
        return "Dead candidate"

    if (
        last_commit_months is not None
        and last_commit_months > 18
        and (
            not npm_used_by_empty
            or not github_dependents_empty
            or npm_downloads_last_year > 0
        )
    ):
        return "Stale but used"

    if (
        not npm_package_empty
        and npm_last_published_months is not None
        and npm_last_published_months > 18
        and not npm_deprecated
    ):
        return "Stale package"

    if (
        last_commit_months is not None
        and last_commit_months > 12
        and (open_prs_count >= 5 or open_issues_count >= 20)
    ):
        return "Stale / neglected"

    if (
        last_commit_months is not None
        and last_commit_months <= 24
        and last_release_months is not None
        and last_release_months > 24
        and github_release_count > 0
    ):
        return "Stale release process"

    if (
        last_commit_months is not None
        and last_commit_months > 18
        and not archived
    ):
        return "Stale"

    if contains_any(repo_name, replacement_terms):
        return "No longer used candidate"

    if (
        contains_any(repo_name, cleanup_terms)
        and last_commit_months is not None
        and last_commit_months > 12
    ):
        return "No longer used candidate"

    if is_fork and npm_used_by_empty and github_dependents_empty:
        return "No longer used candidate"

    if (
        not npm_package_empty
        and npm_used_by_empty
        and github_dependents_empty
        and npm_downloads_last_year == 0
    ):
        return "No longer used candidate"

    return "Needs review"


def main():
    headers, data_rows = load_repository_data()

    if "classification" not in headers:
        headers.append("classification")

    for row in data_rows:
        print(row)
        row["classification"] = determine_classification(row)

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

    # write_list_to_csv(CATEGORIZED_OUTPUT_CSV, headers, data_rows)
    write_rows_to_ods("categorized_repos.ods", "Repositories", data_rows)


if __name__ == "__main__":
    main()
