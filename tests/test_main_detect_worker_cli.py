from src import main as cli
from src.detection.worker import DetectionRunSummary


def test_detect_worker_once_command_runs_worker(monkeypatch, capsys) -> None:
    created: dict[str, object] = {}

    class FakeWorker:
        def __init__(self, **kwargs) -> None:
            created["kwargs"] = kwargs

        def run_once(self) -> DetectionRunSummary:
            return DetectionRunSummary(
                logs_read=3,
                anomalies_detected=1,
                anomalies_inserted=1,
                last_event_time=None,
                duration_ms=7,
            )

        def run_forever(self, *, interval_seconds: int) -> None:
            raise AssertionError("run_forever should not be called for --once")

    monkeypatch.setattr(cli, "ClickHouseStorage", lambda: "storage")
    monkeypatch.setattr(cli, "AnomalyDetectorWorker", FakeWorker)

    args = cli.build_parser().parse_args(
        [
            "detect-worker",
            "--once",
            "--batch-size",
            "25",
            "--lookback-minutes",
            "15",
            "--interval-seconds",
            "5",
        ]
    )
    args.func(args)

    assert created["kwargs"] == {
        "storage": "storage",
        "lookback_minutes": 15,
        "batch_size": 25,
    }
    assert "logs_read=3" in capsys.readouterr().out
