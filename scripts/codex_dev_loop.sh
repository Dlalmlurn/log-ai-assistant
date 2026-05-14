#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="$ROOT_DIR/.codex-loop"
MODE="prepare"
ITERATIONS=1
GOAL=""
MODEL=""
SANDBOX="workspace-write"
APPROVAL="never"
RESUME_LAST=0

usage() {
  cat <<'EOF'
Usage:
  scripts/codex_dev_loop.sh --goal "small development goal"
  scripts/codex_dev_loop.sh --goal "small development goal" --run
  scripts/codex_dev_loop.sh --goal "small development goal" --run --iterations 3

Purpose:
  Build a repeatable Codex development loop for this project. Each iteration
  collects the project guardrails, current repository state, the previous
  iteration summary, and the requested small goal into a prompt.

Default behavior:
  prepare only. It writes the prompt/context files under .codex-loop/ and does
  not call Codex or modify the repository beyond those generated prompt files.

Options:
  --goal TEXT          Required. A small, reviewable development target.
  --run               Call `codex exec` with the generated prompt.
  --iterations N      Number of iterations. Default: 1.
  --model NAME        Optional Codex model override.
  --sandbox MODE      Codex sandbox mode. Default: workspace-write.
  --approval POLICY   Codex approval policy. Default: never.
  --resume-last       Use `codex exec resume --last` instead of a fresh exec.
  -h, --help          Show this help.

Examples:
  scripts/codex_dev_loop.sh --goal "Implement FastAPI /api/v1/health skeleton"
  scripts/codex_dev_loop.sh --goal "Implement FastAPI /api/v1/health skeleton" --run

Notes:
  - Keep each goal small. One API, one page, one contract update, or one testable
    link in the pipeline is the right size.
  - Formal product direction is controlled by docs/00-06.
  - Streamlit and Python Producer remain debug paths, not formal acceptance paths.
EOF
}

die() {
  echo "error: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "missing command: $1"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --goal)
      [[ $# -ge 2 ]] || die "--goal requires a value"
      GOAL="$2"
      shift 2
      ;;
    --run)
      MODE="run"
      shift
      ;;
    --iterations)
      [[ $# -ge 2 ]] || die "--iterations requires a value"
      ITERATIONS="$2"
      shift 2
      ;;
    --model)
      [[ $# -ge 2 ]] || die "--model requires a value"
      MODEL="$2"
      shift 2
      ;;
    --sandbox)
      [[ $# -ge 2 ]] || die "--sandbox requires a value"
      SANDBOX="$2"
      shift 2
      ;;
    --approval)
      [[ $# -ge 2 ]] || die "--approval requires a value"
      APPROVAL="$2"
      shift 2
      ;;
    --resume-last)
      RESUME_LAST=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

[[ -n "$GOAL" ]] || die "--goal is required"
[[ "$ITERATIONS" =~ ^[0-9]+$ ]] || die "--iterations must be a positive integer"
[[ "$ITERATIONS" -ge 1 ]] || die "--iterations must be >= 1"

require_command git
if [[ "$MODE" == "run" ]]; then
  require_command codex
fi

mkdir -p "$STATE_DIR"

collect_file() {
  local path="$1"
  local label="$2"
  local output="$3"

  if [[ -f "$ROOT_DIR/$path" ]]; then
    {
      echo
      echo "## $label"
      echo
      echo '```text'
      sed -n '1,260p' "$ROOT_DIR/$path"
      echo '```'
    } >> "$output"
  else
    {
      echo
      echo "## $label"
      echo
      echo "Missing: $path"
    } >> "$output"
  fi
}

build_context() {
  local output="$1"
  : > "$output"

  {
    echo "# Project Context Packet"
    echo
    echo "Generated at: $(date -Is)"
    echo "Workspace: $ROOT_DIR"
    echo
    echo "## Current Goal"
    echo
    echo "$GOAL"
    echo
    echo "## Repository State"
    echo
    echo '```text'
    git -C "$ROOT_DIR" status --short
    echo '```'
    echo
    echo "## File Inventory"
    echo
    echo '```text'
    if command -v rg >/dev/null 2>&1; then
      rg --files "$ROOT_DIR" \
        | sed "s#^$ROOT_DIR/##" \
        | sort \
        | sed -n '1,240p'
    else
      find "$ROOT_DIR" \
        -path "$ROOT_DIR/.git" -prune -o \
        -path "$ROOT_DIR/.venv" -prune -o \
        -path "$ROOT_DIR/.codex-loop" -prune -o \
        -type f -print \
        | sed "s#^$ROOT_DIR/##" \
        | sort \
        | sed -n '1,240p'
    fi
    echo '```'
  } >> "$output"

  collect_file "docs/00_gold_standard.md" "Gold Standard Requirements" "$output"
  collect_file "docs/01_product_shape.md" "Product Shape" "$output"
  collect_file "docs/02_architecture_decisions.md" "Architecture Decisions" "$output"
  collect_file "docs/03_data_contract.md" "Data Contract" "$output"
  collect_file "docs/04_security_analysis_spec.md" "Security Analysis Spec" "$output"
  collect_file "docs/05_api_contract.md" "API Contract" "$output"
  collect_file "docs/06_acceptance_checklist.md" "Acceptance Checklist" "$output"
  collect_file "README.md" "README Entry Point" "$output"

  if [[ -f "$STATE_DIR/latest_summary.md" ]]; then
    collect_file ".codex-loop/latest_summary.md" "Previous Iteration Summary" "$output"
  else
    {
      echo
      echo "## Previous Iteration Summary"
      echo
      echo "No previous loop summary found."
    } >> "$output"
  fi
}

build_prompt() {
  local context_file="$1"
  local prompt_file="$2"
  local iteration="$3"

  cat > "$prompt_file" <<EOF
You are continuing development on the log-ai-assistant project.

This is iteration $iteration of $ITERATIONS for the current small goal:

$GOAL

Operate as a careful senior engineer. Read and obey the context packet below.

Hard rules:
- Keep the goal small and reviewable. Do not broaden scope.
- Bind changes to the documented REQ-* requirements where relevant.
- Preserve the formal architecture: Filebeat -> Kafka -> Flink -> Elasticsearch -> FastAPI -> React.
- Do not promote Streamlit, Python Producer, or process-raw into the formal acceptance path.
- Do not introduce major new stacks such as Spring Boot, ClickHouse, or Logstash without adding an ADR first.
- Prefer existing code patterns and modules.
- Before editing, inspect the relevant files.
- After editing, run the smallest meaningful verification commands available in this repo.
- If verification cannot run because dependencies are missing, say that clearly and explain the exact blocker.
- Update docs or acceptance checklist only when the code change affects the contract or project口径.
- Final response must include: files changed, verification run, unresolved risks, and recommended next small goal.
- Be explicit about what changed in each touched file. The loop script will archive your final summary.

Context packet:

$(cat "$context_file")
EOF
}

append_history() {
  local iteration="$1"
  local iteration_dir="$2"
  local last_message_file="$3"
  local log_file="$4"
  local history_file="$STATE_DIR/history.md"
  local changed_files_file="$iteration_dir/changed_files.txt"
  local diff_stat_file="$iteration_dir/diff_stat.txt"
  local git_status_file="$iteration_dir/git_status_after.txt"

  git -C "$ROOT_DIR" status --short > "$git_status_file"
  git -C "$ROOT_DIR" diff --stat > "$diff_stat_file"
  {
    git -C "$ROOT_DIR" diff --name-only
    git -C "$ROOT_DIR" ls-files --others --exclude-standard
  } | sort -u > "$changed_files_file"

  {
    echo
    echo "## $(date -Is) - Iteration $iteration"
    echo
    echo "**Goal:** $GOAL"
    echo
    echo "**Iteration directory:** \`$iteration_dir\`"
    echo
    echo "**Codex log:** \`$log_file\`"
    echo
    echo "### Changed Files"
    echo
    if [[ -s "$changed_files_file" ]]; then
      sed 's/^/- `/' "$changed_files_file" | sed 's/$/`/'
    else
      echo "- No changed files detected."
    fi
    echo
    echo "### Diff Stat"
    echo
    echo '```text'
    if [[ -s "$diff_stat_file" ]]; then
      cat "$diff_stat_file"
    else
      echo "No tracked diff stat."
    fi
    echo '```'
    echo
    echo "### Git Status After Iteration"
    echo
    echo '```text'
    if [[ -s "$git_status_file" ]]; then
      cat "$git_status_file"
    else
      echo "Clean working tree."
    fi
    echo '```'
    echo
    echo "### Codex Summary"
    echo
    if [[ -s "$last_message_file" ]]; then
      cat "$last_message_file"
    else
      echo "No final Codex summary was written. Check the Codex log above."
    fi
  } >> "$history_file"

  echo "Updated history: $history_file"
}

run_codex() {
  local prompt_file="$1"
  local last_message_file="$2"
  local log_file="$3"

  local exec_help
  exec_help="$(codex exec --help 2>/dev/null || true)"

  local common_args=(-C "$ROOT_DIR" -o "$last_message_file")
  if grep -q -- "--sandbox" <<< "$exec_help"; then
    common_args+=(-s "$SANDBOX")
  fi
  if grep -q -- "--ask-for-approval" <<< "$exec_help"; then
    common_args+=(-a "$APPROVAL")
  fi
  if [[ -n "$MODEL" ]]; then
    common_args+=(-m "$MODEL")
  fi

  if [[ "$RESUME_LAST" -eq 1 ]]; then
    codex exec "${common_args[@]}" resume --last - < "$prompt_file" | tee "$log_file"
  else
    codex exec "${common_args[@]}" - < "$prompt_file" | tee "$log_file"
  fi
}

for ((i = 1; i <= ITERATIONS; i++)); do
  timestamp="$(date +%Y%m%d-%H%M%S)"
  iteration_dir="$STATE_DIR/$timestamp-iter-$i"
  mkdir -p "$iteration_dir"

  context_file="$iteration_dir/context.md"
  prompt_file="$iteration_dir/prompt.md"
  last_message_file="$iteration_dir/last_message.md"
  log_file="$iteration_dir/codex.log"

  build_context "$context_file"
  build_prompt "$context_file" "$prompt_file" "$i"

  ln -sfn "$iteration_dir" "$STATE_DIR/latest"

  echo "Prepared iteration $i:"
  echo "  context: $context_file"
  echo "  prompt:  $prompt_file"

  if [[ "$MODE" == "run" ]]; then
    echo "Running Codex iteration $i..."
    run_codex "$prompt_file" "$last_message_file" "$log_file"
    if [[ -s "$last_message_file" ]]; then
      cp "$last_message_file" "$STATE_DIR/latest_summary.md"
      echo "Updated summary: $STATE_DIR/latest_summary.md"
    else
      echo "warning: Codex did not write a last-message summary" >&2
    fi
    append_history "$i" "$iteration_dir" "$last_message_file" "$log_file"
  else
    echo "Prepare-only mode. Review the prompt, then rerun with --run when ready."
  fi
done
