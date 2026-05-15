## To setup:

```
pip install pandas odfpy
```

## To run:

copy `env.sample` to `.env` and add your github token

run:
```
python github_repos_csv.py
```
- this generates a spreadsheet named `unfoldingword_repos.ods`

## To split out data in `unfoldingword_repos.ods` to separate CSV files, run:


```
python SheetToCSVConverter.py
```