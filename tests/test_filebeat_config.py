from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FILEBEAT_YML = PROJECT_ROOT / "filebeat" / "filebeat.yml"


def test_filebeat_reads_each_generated_source_file() -> None:
    config = FILEBEAT_YML.read_text(encoding="utf-8")

    for source in ("vpn", "oa", "api", "system", "file", "database", "security_device"):
        assert f"/var/log/app/{source}.log" in config
        assert f"source_type: {source}" in config

    assert 'topic: "raw_logs"' in config
