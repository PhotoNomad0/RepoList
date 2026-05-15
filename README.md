# GitHub Repository Spreadsheet Tools

Utilities for generating an OpenDocument spreadsheet of GitHub repository data and exporting spreadsheet sheets to CSV files.

## Prerequisites

- Python 3.11+
- A GitHub personal access token
- A Python virtual environment

## Setup

Create and activate a virtual environment if you have not already done so:
```
bash
python -m virtualenv .venv
source .venv/bin/activate
```

On Windows:
```
bash
.venv\Scripts\activate
```

Install the required Python packages:
```
bash
pip install pandas odfpy
```


## Configuration

Copy the sample environment file:

```
bash
cp env.sample .env
```
Then edit `.env` and add your GitHub token.

## Generate the Repository Spreadsheet

Run:
```
bash
python github_repos_csv.py
```
This generates an OpenDocument spreadsheet named:
```
text
unfoldingword_repos.ods
```

## Export Spreadsheet Sheets to CSV

To split the data in `unfoldingword_repos.ods` into separate CSV files, run:
```
bash
python SheetToCSVConverter.py
```


## Output

- `unfoldingword_repos.ods` — generated spreadsheet containing repository data
- CSV files — generated from the individual sheets in the spreadsheet
```
