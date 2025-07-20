#!/usr/bin/env python3
"""
aws-csv-to-confluence

Usage:
  aws-csv-to-confluence --user USER --token TOKEN --url URL --file FILE
                        (--parent PARENT | --parent-space SPACE --parent-title TITLE)
                        [--subtitle SUBTITLE]
                        [--ignore-group GROUPS]
                        [--ignore-resource-type TYPES]
                        [--clean]
                        [--dry-run]

Options:
  --user USER                  Confluence user (required)
  --token TOKEN                Atlassian token / password (required)
  --url URL                    Base URL, e.g. https://mycorp.atlassian.net/wiki (required)
  --parent PARENT              Confluence parent page ID (mutually exclusive with --parent-space and --parent-title)
  --parent-space SPACE         Confluence space key (must be used with --parent-title)
  --parent-title TITLE         Confluence parent page title (must be used with --parent-space)
  --file FILE                  Path to the CSV file to process (required)
  --subtitle SUBTITLE          Text inserted in square brackets after "[AWS]" in the page title
  --ignore-group GROUPS        Comma-separated resource groups to skip (e.g. ec2,s3)
  --ignore-resource-type TYPES Comma-separated resource types to skip (e.g. snapshot,instance)
  --clean                      Delete stale child pages after publishing
  --dry-run                    Do everything except call the Confluence REST API
"""
from __future__ import annotations

import csv
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Collection, Dict, List, Set

from atlassian import Confluence
from docopt import docopt


def _comma_list(val: str | None) -> set[str]:
    return {x.strip() for x in val.split(",")} if val else set()


def csv_to_service_dict(path: str | Path) -> Dict[str, List[List[str]]]:
    """Return {Service: [[Identifier, Tag: Name, Type, Region, ARN], …]}."""
    required = {"Identifier", "Tag: Name", "Type", "Region", "ARN", "Service"}
    out: Dict[str, List[List[str]]] = defaultdict(list)

    with open(path, newline="") as fp:
        rdr = csv.DictReader(fp)
        if rdr.fieldnames is None:
            raise ValueError("CSV has no header row")

        missing = required - set(rdr.fieldnames)
        if missing:
            raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")

        for row in rdr:
            out[row["Service"]].append(
                [
                    row["Identifier"],
                    row["Tag: Name"] or "(not tagged)",
                    row["Type"],
                    row["Region"],
                    row["ARN"],
                ]
            )
    return out


def create_pages(
    resources: Dict[str, List[List[str]]],
    parent_id: str | int,
    subtitle: str | None,
    *,
    ignore_groups: Collection[str],
    ignore_resource_types: Collection[str],
    confluence: Confluence,
    dry_run: bool = False,
) -> Set[str]:
    """
    Publish one Confluence page per Service; return the set of titles created.
    """
    ig_groups = set(ignore_groups)
    ig_types = set(ignore_resource_types)
    header = "||ID||Tag: Name||Type||Region||ARN||"
    log = logging.getLogger(__name__)
    created_titles: set[str] = set()

    for group, rows in resources.items():
        if group in ig_groups:
            log.info("Skipping group %s (ignore list)", group)
            continue

        body_rows = [
            f"|{rid}|{tag}|{rtype}|{region}|{arn}|"
            for rid, tag, rtype, region, arn in rows
            if rtype not in ig_types or log.info("Skipping %s (%s ignored)", rid, rtype)
        ]

        if not body_rows:
            log.info("Group %s: all rows filtered out — page not created", group)
            continue

        title = "[AWS] "
        if subtitle:
            title += f"[{subtitle}] "
        title += group

        if dry_run:
            log.info("[DRY-RUN] Would publish page %s (%d rows)", title, len(body_rows))
        else:
            confluence.update_or_create(
                title=title,
                body=header + "\n" + "\n".join(body_rows),
                representation="wiki",
                parent_id=parent_id,
            )
            log.info("Published page %s (%d rows)", title, len(body_rows))

        created_titles.add(title)

    return created_titles


def clean_up(
    parent_id: str | int,
    keep_titles: Set[str],
    run_time: datetime,
    confluence: Confluence,
    *,
    dry_run: bool = False,
) -> None:
    """
    Delete child pages whose title is *not* in keep_titles and whose last edit
    precedes run_time.
    """
    log = logging.getLogger(__name__)
    for page_id in confluence.get_child_id_list(page_id=parent_id):
        meta = confluence.get_page_by_id(page_id=page_id)
        title = meta.get("title", "")
        if title in keep_titles:
            continue

        edited_str = meta.get("version", {}).get("when")
        if not edited_str:
            continue
        try:
            edited_ts = datetime.fromisoformat(edited_str.replace("Z", "+00:00"))
        except ValueError:
            log.warning("Could not parse timestamp %s on page %s", edited_str, title)
            continue

        if edited_ts < run_time:
            if dry_run:
                log.info("[DRY-RUN] Would remove stale page %s (id %s)", title, page_id)
            else:
                log.info("Removing stale page %s (id %s)", title, page_id)
                confluence.remove_page(page_id=page_id)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args: Dict[str, Any] = docopt(__doc__)

    dry_run: bool = bool(args["--dry-run"])
    if dry_run:
        logging.info(
            "Running in DRY-RUN mode — no changes will be pushed to Confluence"
        )

    confluence = Confluence(
        url=args["--url"],
        username=args["--user"],
        password=args["--token"],
    )

    has_parent_id = bool(args["--parent"])
    has_space_and_title = bool(args["--parent-space"] and args["--parent-title"])

    if has_parent_id and has_space_and_title:
        raise ValueError("Cannot use --parent with --parent-space and --parent-title")

    if not has_parent_id and not has_space_and_title:
        raise ValueError(
            "Must provide either --parent or both --parent-space and --parent-title"
        )

    if has_space_and_title:
        parent_page = confluence.get_page_by_title(
            space=args["--parent-space"], title=args["--parent-title"]
        )
        if not parent_page:
            raise ValueError(
                f"Parent page not found in space '{args['--parent-space']}' with title '{args['--parent-title']}'"
            )
        parent_id = parent_page["id"]
    else:
        parent_id = args["--parent"]

    run_start = datetime.now(timezone.utc)

    services = csv_to_service_dict(Path(args["--file"]))
    created_titles = create_pages(
        services,
        parent_id=parent_id,
        subtitle=args.get("--subtitle"),
        ignore_groups=_comma_list(args.get("--ignore-group")),
        ignore_resource_types=_comma_list(args.get("--ignore-resource-type")),
        confluence=confluence,
        dry_run=dry_run,
    )

    if args["--clean"]:
        clean_up(
            parent_id=parent_id,
            keep_titles=created_titles,
            run_time=run_start,
            confluence=confluence,
            dry_run=dry_run,
        )

    logging.info("Finished at %s", datetime.now(timezone.utc).isoformat())


if __name__ == "__main__":
    main()
