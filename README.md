# aws-csv-to-confluence

Upload an AWS resource inventory (exported as CSV) to Confluence, one page per **Service**.  
Written in Python, packaged with **Poetry**, and shipped with an optional Docker image.

---

## Table of contents

1. [Features](#features)
2. [CSV format expectations](#csv-format-expectations)
3. [Quick start](#quick-start)
4. [Command-line reference](#command-line-reference)
5. [Examples](#examples)
6. [Docker](#docker)
7. [Development & tests](#development--tests)
8. [License](#license)

---

## Features

* **One Confluence page per AWS Service** - EC2, S3, Lambda, ...  
* Keeps multiple rows per service (e.g. snapshots, instances, volumes).  
* **ignore lists**  
  * `--ignore-group` - filters out given resource group(s)
  * `--ignore-resource-type` - filters out given resource type(s)
* **`--clean`** flag, when added, removes obsolete pages created by earlier runs.  
* Simple output format - Confluence **storage (wiki) tables**, no fancy macros.  
* Two external dependencies - [Atlassian Python REST API wrapper](https://github.com/atlassian-api/atlassian-python-api) and `docopt`.

---

## CSV format expectations

The script needs **six columns** to be presented in a file:

| Column            | Notes                                |
|-------------------|--------------------------------------|
| `Identifier`      | e.g. `vol-0abc…` / `i-0123…`         |
| `Tag: Name`       | Empty values become "`(not tagged)`" |
| `Type`            | `instance`, `snapshot`, `bucket`, …  |
| `Region`          | `us-east-1` / `eu-central-1` …       |
| `ARN`             | Full resource ARN                    |
| `Service`         | Logical grouping key (`ec2`, `s3`)   |

All other columns are ignored

---

## How to export resources in CSV from AWS

TBD

## How to create Atlassian token

TBD

## Quick start

```bash
# 1. Clone & install
git clone https://github.com/dunterov/aws-csv-to-confluence.git
cd aws-csv-to-confluence
poetry install

# 2. Run
poetry run aws-csv-to-confluence --user alice@example.com \
    --token <ATLASSIAN_TOKEN> \
    --url https://mycorp.atlassian.net/wiki   \
    --parent 123456789 \
    --file ./resources.csv \
    --subtitle prod \
    --ignore-group DBGroup,CacheGroup \ 
    --ignore-resource-type snapshot \
    --clean
```

**Result:**  
* `[AWS] [prod] ec2`, `[AWS] [prod] s3`, … pages created (or updated) under page `123456789` in a Confluence.  
* Old child pages last edited _before_ the run and _not_ recreated are deleted.

---

## Command-line reference

```text
aws-csv-to-confluence --user USER --token TOKEN --url URL --parent PARENT --file FILE
                        [--subtitle SUBTITLE]
                        [--ignore-group GROUPS]
                        [--ignore-resource-type TYPES]
                        [--clean]

Options:
  --user USER                  Confluence user (required)
  --token TOKEN                Atlassian token / password (required)
  --url URL                    Base URL, e.g. https://mycorp.atlassian.net/wiki (required)
  --parent PARENT              Confluence parent page ID (required)
  --file FILE                  Path to the CSV file to process (required)
  --subtitle SUBTITLE          Text inserted in square brackets after '[AWS]' in the page title.
  --ignore-group GROUPS        Comma-separated resource groups to skip (e.g ec2, s3).
  --ignore-resource-type TYPES Comma-separated resource types to skip (e.g. snapshot, instance).
  --clean                      After publishing, delete child pages that
                               (a) were last edited *before* this run and
                               (b) no longer match any current page title.
```

---

## Examples

### Ignore whole resource group *and* specific resource types

```bash
--ignore-group iam --ignore-resource-type snapshot,volume
```

### Dry-run (no page deletion)

Simply omit **`--clean`** - pages are added/updated, nothing is deleted.

---

## Docker

A minimal image is provided:

```bash
# build
docker build -t aws-csv-to-confluence .

# run
docker run --rm -v $PWD/resources.csv:/resources.csv \
    -e ATLASSIAN_USER=alice@example.com \
    -e ATLASSIAN_TOKEN=$TOKEN \
    aws-csv-to-confluence:latest \
    --user $ATLASSIAN_USER \
    --token $ATLASSIAN_TOKEN \
    --url https://mycorp.atlassian.net/wiki \
    --parent 123456789 \
    --file /resources.csv \
    --clean
```

---

## Development & tests

```bash
# set up
poetry install

# run unit tests
poetry run pytest

```

The **test suite** uses small in-memory CSV snippets and a `DummyConfluence`
stub, so it never touches a real wiki.

---

## License
MIT - see [`LICENSE`](LICENSE) for full text.
