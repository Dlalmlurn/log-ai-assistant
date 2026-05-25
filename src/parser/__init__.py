from .log_parser import normalize_raw_record, parse_log_line

__all__ = ["parse_log_line", "normalize_raw_record", "run_raw_to_parsed_worker"]


def __getattr__(name: str):
    if name == "run_raw_to_parsed_worker":
        from .raw_to_parsed_worker import run_raw_to_parsed_worker

        return run_raw_to_parsed_worker
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
