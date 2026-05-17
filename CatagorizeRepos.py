import csv
import zipfile
import xml.etree.ElementTree as ET


ODS_FILE = "unfoldingword_repos.ods"
SHEET_NAME = "Repositories"
OUTPUT_CSV = "categorized_repos.csv"

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
    """Read rows from a named sheet in an ODS file."""
    with zipfile.ZipFile(filename, "r") as ods:
        with ods.open("content.xml") as content:
            tree = ET.parse(content)

    root = tree.getroot()

    sheets = root.findall(".//table:table", NS)

    for sheet in sheets:
        name = sheet.attrib.get(f"{{{NS['table']}}}name")

        if name != sheet_name:
            continue

        rows = []

        for row in sheet.findall("table:table-row", NS):
            repeated_rows = int(
                row.attrib.get(f"{{{NS['table']}}}number-rows-repeated", "1")
            )

            row_data = []

            for cell in row.findall("table:table-cell", NS):
                repeated_cols = int(
                    cell.attrib.get(f"{{{NS['table']}}}number-columns-repeated", "1")
                )

                value = get_cell_text(cell)

                for _ in range(repeated_cols):
                    row_data.append(value)

            for _ in range(repeated_rows):
                rows.append(row_data)

        return rows

    raise ValueError(f"Sheet not found: {sheet_name}")


def write_csv(output_csv, headers, data):
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


def main():
    headers, data = load_repository_data()

    # TODO categories repos

    write_csv(OUTPUT_CSV, headers, data)


if __name__ == "__main__":
    main()
