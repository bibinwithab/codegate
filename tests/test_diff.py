from codevoight.core.diff import (
    compute_diff_hash,
    generate_diff,
    generate_file_diff,
    normalize_text,
)
from codevoight.core.models import StagedFile


def test_normalize_text():
    crlf = "line 1\r\nline 2\r\n"
    lf = "line 1\nline 2\n"
    assert normalize_text(crlf) == lf


def test_compute_diff_hash_consistency():
    diff_crlf = "--- a/foo.py\r\n+++ b/foo.py\r\n@@ -1 +1 @@\r\n-a\r\n+b\r\n"
    diff_lf = "--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-a\n+b\n"
    # Both CRLF and LF must yield identical diff hash
    assert compute_diff_hash(diff_crlf) == compute_diff_hash(diff_lf)


def test_generate_file_diff():
    diff = generate_file_diff(
        "app.py",
        old_content="def hello():\n    return 1\n",
        new_content="def hello():\n    return 2\n",
    )
    assert "--- a/app.py" in diff
    assert "+++ b/app.py" in diff
    assert "-    return 1" in diff
    assert "+    return 2" in diff


def test_generate_multi_file_diff():
    files = [
        StagedFile(file_path="b.py", old_content="", new_content="print(2)\n"),
        StagedFile(file_path="a.py", old_content="", new_content="print(1)\n"),
    ]
    diff = generate_diff(files)
    # Alphabetical order: a.py must appear before b.py
    pos_a = diff.find("a.py")
    pos_b = diff.find("b.py")
    assert pos_a != -1 and pos_b != -1
    assert pos_a < pos_b
