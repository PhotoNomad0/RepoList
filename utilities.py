import os
import pandas as pd
import re
import sys
import time
import urllib.error
import urllib.request

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