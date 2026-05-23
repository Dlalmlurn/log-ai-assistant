from __future__ import annotations

import os
import random
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from gen_vpn_logs import USERS, gen_anomaly_large_download, gen_failed_login, gen_normal_login


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _to_syslog_line(entry: object) -> str:
    d = asdict(entry)
    line = (
        f"{d['timestamp']} {d['vpn_gateway']} vpnd: "
        f"event={d['event_type']} user={d['username']} dept={d['dept']} "
        f"src_ip={d['src_ip']} src_geo={d['src_country']}/{d['src_city']} "
        f"proto={d['protocol']} auth={d['auth_method']} "
        f"client=\"{d['client_software']}\" session={d['session_id']} "
        f"result={d['result']}"
    )
    if d["fail_reason"]:
        line += f" reason={d['fail_reason']}"
    if d["session_duration_sec"]:
        line += f" duration={d['session_duration_sec']}s"
    if d["bytes_recv"]:
        line += f" bytes_recv={d['bytes_recv']} bytes_sent={d['bytes_sent']}"
    line += f" risk_score={d['risk_score']} risk_tags=\"{d['risk_tags']}\""
    return line


def _next_entry(now: datetime) -> object:
    user = random.choice(USERS)
    roll = random.random()
    if roll < 0.04:
        return gen_failed_login(user, now, anomaly_ip=random.random() < 0.5)
    if roll < 0.05:
        return gen_anomaly_large_download(user, now)
    return gen_normal_login(user, now)


def main() -> None:
    output = Path(os.getenv("LOG_GENERATOR_OUTPUT", "/var/log/app/vpn_logs.log"))
    interval_seconds = max(1, _get_int("LOG_GENERATOR_INTERVAL_SECONDS", 5))
    batch_size = max(1, _get_int("LOG_GENERATOR_BATCH_SIZE", 3))
    seed = _get_int("LOG_GENERATOR_SEED", 42)

    random.seed(seed)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.touch(exist_ok=True)

    print(
        "continuous log-generator started: "
        f"output={output} interval={interval_seconds}s batch_size={batch_size}"
    )

    while True:
        now = datetime.now()
        lines = [_to_syslog_line(_next_entry(now)) for _ in range(batch_size)]
        with output.open("a", encoding="utf-8") as f:
            for line in lines:
                f.write(line + "\n")
            f.flush()
        print(f"appended {len(lines)} log lines to {output}")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    main()
