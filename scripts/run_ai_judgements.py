#!/usr/bin/env python3
"""批量 AI 研判驱动。

按 docs/07_ai_judgement_feedback_spec.md，AI 只研判高可疑(high/critical)异常。本脚本
挑选这些待研判事件，复用后端 `POST /api/v1/ai/judge/{event_id}` 端点完成研判与落库，
从而：
  - 走与前端一致的证据包链路（baseline + related_logs + window_stats）；
  - 把 AIJudgement 写入 `ai_judgements`，并把结构化建议写入 `ai_feedback`(pending)；
  - DashScope 不可用时端点自动回退 mock，研判结果带 `is_mock=true` 明确标记。

脚本只依赖标准库，可在宿主机(默认 http://localhost:8000)或后端容器内运行。

用法:
    python -m scripts.run_ai_judgements --limit 50
    python -m scripts.run_ai_judgements --base-url http://localhost:8000 --levels critical high
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request


def _get_json(url: str, timeout: float) -> dict:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post_json(url: str, timeout: float) -> tuple[int, dict]:
    req = urllib.request.Request(url, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"raw": body}


def _candidate_event_ids(base_url: str, level: str, limit: int, timeout: float) -> list[str]:
    """拉取某风险等级下仍待研判(ai_status=pending)的事件 id。"""

    query = urllib.parse.urlencode(
        {"risk_level": level, "ai_status": "pending", "limit": limit}
    )
    payload = _get_json(f"{base_url}/api/v1/anomalies?{query}", timeout)
    items = payload.get("items", []) if isinstance(payload, dict) else []
    return [str(item["event_id"]) for item in items if item.get("event_id")]


def run(base_url: str, levels: list[str], limit: int, timeout: float) -> int:
    base_url = base_url.rstrip("/")
    judged = real = mock = failed = 0

    for level in levels:
        try:
            event_ids = _candidate_event_ids(base_url, level, limit, timeout)
        except Exception as exc:  # noqa: BLE001 - 顶层驱动，打印后继续
            print(f"[{level}] 候选查询失败: {exc}", file=sys.stderr)
            continue

        print(f"[{level}] 待研判候选 {len(event_ids)} 条")
        for event_id in event_ids:
            status, body = _post_json(f"{base_url}/api/v1/ai/judge/{event_id}", timeout)
            if status != 200:
                failed += 1
                code = body.get("detail", {}).get("code") if isinstance(body, dict) else None
                print(f"  - {event_id} 研判失败 HTTP {status} {code or ''}", file=sys.stderr)
                continue
            judged += 1
            if body.get("is_mock"):
                mock += 1
            else:
                real += 1

    print(
        f"\n完成: judged={judged} (real={real}, mock={mock}) failed={failed}",
    )
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="批量 AI 研判 high/critical 异常事件")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument(
        "--levels",
        nargs="+",
        default=["critical", "high"],
        help="研判的风险等级（默认 critical high）",
    )
    parser.add_argument("--limit", type=int, default=50, help="每个等级最多研判多少条")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()
    return run(args.base_url, args.levels, args.limit, args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
