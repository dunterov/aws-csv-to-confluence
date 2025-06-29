import io
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from aws_csv_to_confluence.main import (
    _comma_list,
    csv_to_service_dict,
    create_pages,
    clean_up,
)

# --------------------------------------------------------------------------- fixtures


@pytest.fixture()
def tmp_csv(tmp_path: Path) -> Path:
    """Temporary CSV with two EC2 rows and one S3 row."""
    content = io.StringIO(
        "Identifier,Tag: Name,Service,Type,Region,ARN\n"
        "id-111,DB1,ec2,instance,us-east-2,arn:aws:ec2:...:instance/id-111\n"
        "id-222,DB2,ec2,snapshot,us-east-2,arn:aws:ec2:...:snapshot/id-222\n"
        "id-333,Bucket1,s3,bucket,us-east-1,arn:aws:s3:::bucket1\n"
    )
    path = tmp_path / "resources.csv"
    path.write_text(content.getvalue())
    return path


class DummyConfluence:
    """Minimal stub that records what the code calls."""

    def __init__(self):
        self.pages_created = []
        self.pages_removed = []
        # Child pages we'll expose via get_child_id_list
        self._children = {
            "1": {
                "title": "[AWS] ec2",
                "version": {"when": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat().replace("+00:00", "Z")},
            },
            "2": {
                "title": "[AWS] s3",
                "version": {"when": (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat().replace("+00:00", "Z")},
            },
        }

    # ----- called by the app -----
    def update_or_create(self, *, title, body, representation, parent_id):
        self.pages_created.append((title, body, parent_id))

    def get_child_id_list(self, *, page_id):
        return list(self._children)

    def get_page_by_id(self, *, page_id):
        return self._children[str(page_id)]

    def remove_page(self, *, page_id):
        self.pages_removed.append(page_id)


# --------------------------------------------------------------------------- unit tests


def test_comma_list_helper():
    assert _comma_list("a,b ,c") == {"a", "b", "c"}
    assert _comma_list(None) == set()


def test_csv_to_service_dict(tmp_csv: Path):
    result = csv_to_service_dict(tmp_csv)
    assert set(result) == {"ec2", "s3"}                   # two top-level keys
    assert len(result["ec2"]) == 2                        # two rows kept together
    first = result["ec2"][0]
    assert first[:3] == ["id-111", "DB1", "instance"]     # basic mapping intact


def test_create_pages_filtering(monkeypatch):
    resources = {
        "ec2": [
            ["id-1", "R1", "instance", "us-east-1", "arn1"],
            ["id-2", "R2", "snapshot", "us-east-1", "arn2"],
        ],
        "s3": [
            ["id-3", "R3", "bucket", "us-east-1", "arn3"],
        ],
    }
    stub = DummyConfluence()

    # Ignore the whole group "s3" and the resource-type "snapshot"
    created = create_pages(
        resources,
        parent_id=42,
        subtitle="prod",
        ignore_groups={"s3"},
        ignore_resource_types={"snapshot"},
        confluence=stub,
    )

    # Only one page (ec2) should be created …
    assert created == {"[AWS] [prod] ec2"}
    # … and it should contain only the *instance* row.
    assert len(stub.pages_created) == 1
    _, body, _ = stub.pages_created[0]
    assert "|id-1|" in body and "|id-2|" not in body


def test_clean_up(tmp_path: Path):
    stub = DummyConfluence()
    keep_titles = {"[AWS] ec2"}          # pretend we just recreated the ec2 page
    run_start = datetime.now(timezone.utc)

    clean_up(
        parent_id=999,
        keep_titles=keep_titles,
        run_time=run_start,
        confluence=stub,
    )

    # Page 1 (ec2) is kept, page 2 (s3) has a *future* edit so is also kept
    assert stub.pages_removed == []

def test_dry_run_creates_nothing_and_removes_nothing():
    """`--dry-run` should leave Confluence untouched."""
    resources = {
        "ec2": [["id-1", "R1", "instance", "us-east-1", "arn1"]],
        "s3":  [["id-2", "R2", "bucket",   "us-east-1", "arn2"]],
    }
    stub = DummyConfluence()

    # ----- create phase (dry‑run) -----
    created = create_pages(
        resources,
        parent_id=42,
        subtitle=None,
        ignore_groups=set(),
        ignore_resource_types=set(),
        confluence=stub,
        dry_run=True,
    )

    assert created == {"[AWS] ec2", "[AWS] s3"}   # titles are still reported
    assert stub.pages_created == []               # but nothing was pushed

    # ----- cleanup phase (dry‑run) -----
    run_start = datetime.now(timezone.utc)
    clean_up(
        parent_id=999,
        keep_titles=created,
        run_time=run_start,
        confluence=stub,
        dry_run=True,
    )
