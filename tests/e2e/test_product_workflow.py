"""Real loopback HTTP acceptance using synthetic miu2d assets and isolated state."""

from __future__ import annotations

import io
import json
import shutil
import socket
import subprocess
import sys
import time
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
ASSET = REPO / "tests/fixtures/miu2d/product"


class RealServer:
    """Own one real CLI process; restart preserves its temporary SQLite state."""

    def __init__(self, root: Path) -> None:
        self.root = root
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            self.port = sock.getsockname()[1]
        self.client = httpx.Client(base_url=f"http://127.0.0.1:{self.port}", timeout=10)
        self.process: subprocess.Popen[bytes] | None = None
        self.log = (root / "server.log").open("ab")

    def start(self) -> None:
        """Start the product CLI, failing with captured logs if startup fails."""
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "udify.cli",
                "serve",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
                "--state-dir",
                str(self.root / "state"),
            ],
            cwd=REPO,
            stdout=self.log,
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                response = self.client.get("/api/v0/healthz")
                if response.status_code == 200:
                    assert response.json()["data"]["state_dir"] == str(self.root / "state")
                    return
            except httpx.TransportError:
                pass
            if self.process.poll() is not None:
                break
            time.sleep(0.05)
        raise AssertionError((self.root / "server.log").read_text())

    def stop(self) -> None:
        """Stop only the owned process and await its shutdown protocol."""
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
                raise

    def restart(self) -> None:
        """Restart against the same state directory and address."""
        self.stop()
        self.start()


@pytest.fixture
def server(tmp_path: Path) -> Iterator[RealServer]:
    """Run the real service with no mocked execution, API, or persistence."""
    service = RealServer(tmp_path)
    try:
        service.start()
        yield service
    finally:
        service.stop()
        service.client.close()
        service.log.close()


@pytest.fixture
def product_game(tmp_path: Path) -> Path:
    """Copy tracked synthetic assets; exercise CRLF preservation on the copy."""
    root = tmp_path / "game"
    shutil.copytree(ASSET, root)
    for path in root.glob("*.ini"):
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    return root


def snapshot(root: Path) -> dict[str, bytes]:
    """Return exact original bytes, including files that are not package targets."""
    return {
        str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }


def wait_status(client: httpx.Client, job_id: str, target: str) -> dict[str, Any]:
    """Wait for a durable status or show the actual failed job."""
    deadline = time.monotonic() + 20
    job: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/v0/jobs/{job_id}")
        response.raise_for_status()
        job = response.json()["data"]["job"]
        if job["status"] == target:
            return job
        assert job["status"] != "failed", job
        time.sleep(0.05)
    raise AssertionError(f"Wanted {target}: {job}")


def create_job(client: httpx.Client, root: Path, intent: str) -> str:
    """Create via actual HTTP and return the assigned job ID."""
    response = client.post("/api/v0/jobs", json={"game_root": str(root), "intent": intent})
    assert response.status_code == 202, response.text
    return str(response.json()["data"]["job_id"])


def test_real_review_package_restart_and_revocation(server: RealServer, product_game: Path) -> None:
    """A1/A4/A5/A7/A8: exact target, package bytes, durable review and revoke."""
    original = snapshot(product_game)
    client = server.client
    job_id = create_job(client, product_game, "把第一个 Boss 的攻击力翻倍")
    endpoint = f"/api/v0/jobs/{job_id}"
    wait_status(client, job_id, "awaiting_review")
    plan = client.get(f"{endpoint}/plan").json()["data"]
    assert len(plan["operations"]) == 1, plan
    assert "BossA" in json.dumps(plan["operations"])
    assert "Attack" in json.dumps(plan["operations"])
    assert len(plan["diffs"]) == 1
    assert snapshot(product_game) == original

    server.restart()
    assert client.get(endpoint).json()["data"]["job"]["status"] == "awaiting_review"
    assert client.get(f"{endpoint}/plan").json()["data"] == plan
    assert client.post(f"{endpoint}/approve").status_code == 202
    wait_status(client, job_id, "completed")
    report = client.get(f"{endpoint}/report").json()["data"]
    assert report["delivery"]["kind"] == "package"
    assert report["delivery"]["installed"] is False
    assert report["delivery"]["tier"] == "STATIC_ONLY"
    assert report["delivery"]["reason"]
    assert report["engine_coverage"] == "UNVERIFIABLE"
    assert report["artifact_validation"]["passed"] is True
    assert report["artifact_validation"]["checks"]
    package = client.get(f"{endpoint}/package")
    assert package.status_code == 200
    with zipfile.ZipFile(io.BytesIO(package.content)) as archive:
        assert {name for name in archive.namelist() if name.startswith("files/")} == {
            "files/characters.ini"
        }
        expected = original["characters.ini"].replace(b"Attack=50\r\n", b"Attack=100\r\n")
        assert archive.read("files/characters.ini") == expected
        assert len(json.loads(archive.read("patch.json"))["operations"]) == 1
    assert snapshot(product_game) == original
    events = client.get(endpoint).json()["data"]["events"]
    cursor = events[len(events) // 2]["seq"]
    stream = client.get(f"{endpoint}/events", headers={"Last-Event-ID": str(cursor)})
    assert stream.status_code == 200
    frames = [
        dict(line.split(": ", 1) for line in frame.splitlines() if ": " in line)
        for frame in stream.text.split("\n\n")
    ]
    replay = [json.loads(frame["data"]) for frame in frames if frame.get("event") == "job"]
    assert replay == [event for event in events if event["seq"] > cursor]
    for frame in frames:
        if frame.get("event") == "job":
            assert int(frame["id"]) == json.loads(frame["data"])["seq"]
    done = [json.loads(frame["data"]) for frame in frames if frame.get("event") == "done"]
    assert done == [{"job_id": job_id, "status": "completed", "seq": events[-1]["seq"]}]
    assert client.post(f"{endpoint}/approve").status_code == 409
    assert client.post(f"{endpoint}/rollback").status_code == 200
    assert client.get(f"{endpoint}/package").status_code == 404
    server.restart()
    assert client.get(endpoint).json()["data"]["job"]["status"] == "rolled_back"
    assert client.get(f"{endpoint}/package").status_code == 404
    assert snapshot(product_game) == original


def test_real_clarification_survives_restart(server: RealServer, product_game: Path) -> None:
    """A3: ambiguous bosses survive restart and must be explicitly selected."""
    original = snapshot(product_game)
    client = server.client
    job_id = create_job(client, product_game, "把 Boss 的攻击力翻倍")
    endpoint = f"/api/v0/jobs/{job_id}"
    job = wait_status(client, job_id, "awaiting_clarification")
    clarification = job["checkpoint"]["clarification"]
    assert clarification["question"] and clarification["reason"]
    assert clarification["graph_checksum"]
    candidates = clarification["candidates"]
    assert {item["display_name"] for item in candidates} == {"BossA", "BossC"}
    assert client.post(f"{endpoint}/approve").status_code == 409
    server.restart()
    restored = client.get(endpoint).json()["data"]["job"]
    assert restored["status"] == "awaiting_clarification"
    assert restored["checkpoint"]["clarification"] == clarification
    invalid = client.post(f"{endpoint}/clarify", json={"target_ids": ["not-a-candidate"]})
    assert invalid.status_code == 400, invalid.text
    assert client.get(endpoint).json()["data"]["job"]["status"] == "awaiting_clarification"
    chosen = next(item["node_id"] for item in candidates if item["display_name"] == "BossC")
    response = client.post(f"{endpoint}/clarify", json={"target_ids": [chosen]})
    assert response.status_code == 202, response.text
    wait_status(client, job_id, "awaiting_review")
    plan = client.get(f"{endpoint}/plan").json()["data"]
    assert len(plan["operations"]) == 1
    assert "BossC" in json.dumps(plan["operations"])
    assert snapshot(product_game) == original


def test_real_approval_rejects_source_drift(server: RealServer, product_game: Path) -> None:
    """A7: an external edit after review must not be silently packaged."""
    client = server.client
    job_id = create_job(client, product_game, "把第一个 Boss 的攻击力翻倍")
    endpoint = f"/api/v0/jobs/{job_id}"
    wait_status(client, job_id, "awaiting_review")
    source = product_game / "characters.ini"
    source.write_bytes(source.read_bytes().replace(b"Attack=50", b"Attack=51"))
    changed_by_test = snapshot(product_game)
    response = client.post(f"{endpoint}/approve")
    assert response.status_code == 202, response.text
    job = wait_status(client, job_id, "failed")
    assert "VERSION" in job["error"]["code"] or "DRIFT" in job["error"]["code"]
    assert client.get(f"{endpoint}/package").status_code == 404
    assert snapshot(product_game) == changed_by_test
