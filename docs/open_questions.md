# Open Questions

本文件记录暂不阻塞当前迭代、但后续必须确认的产品语义、API 契约、数据建模和技术债问题。

## Usage

- 新问题追加到 `Open Items` 顶部或底部均可，但编号必须递增。
- 编号格式：`OQ-YYYYMMDD-NN`。
- `Status` 只能使用 `Open`、`Decided`、`Deferred`、`Closed`。
- `Tags` 使用逗号分隔，方便 `rg "api, alerts"` 或 `rg "Status: Open"` 查询。
- 如果问题演变成架构决策，迁移到 `docs/02_architecture_decisions.md` 并在这里标记为 `Closed`。
- 如果问题影响 API 契约，解决后同步更新 `docs/05_api_contract.md` 和测试。

## Entry Template

```md
### OQ-YYYYMMDD-NN: Short Title

**Status:** Open | Decided | Deferred | Closed
**Tags:** api, frontend, es, product
**Owner:** TBD
**Related:** `file_or_endpoint`, REQ-XXX
**Created:** YYYY-MM-DD
**Last Updated:** YYYY-MM-DD

**Question:** The decision that remains unclear.

**Context:**
- Why this came up.
- Current implementation or workaround.

**Options:**
- Option A: Tradeoff.
- Option B: Tradeoff.

**Current Decision:** Temporary direction, if any.

**Risk If Unresolved:** What may break or become inconsistent.

**Resolution Criteria:**
- What must be decided or changed before closing.
```

## Open Items

### OQ-20260519-01: Clarify `/api/v1/alerts` `rule` Filter Semantics

**Status:** Open
**Tags:** api, alerts, elasticsearch, product, frontend
**Owner:** TBD
**Related:** `GET /api/v1/alerts`, `rule_hits`, `docs/05_api_contract.md`, REQ-004, REQ-006, REQ-008
**Created:** 2026-05-19
**Last Updated:** 2026-05-19

**Question:** Should the `rule` query parameter mean exact rule-name matching, keyword/phrase search, or broader fuzzy search?

**Context:**
- The current proposed implementation follows the existing Streamlit dashboard behavior with `{"match_phrase": {"rule_hits": rule}}`.
- This works well for keyword or short phrase search, such as searching `新IP登录` to match `新IP登录后短时间访问敏感资源`.
- `rule_hits` is modeled as an Elasticsearch `keyword` field, where `term` matching is usually the clearest exact-match strategy.

**Options:**
- Exact rule name: use `term` on `rule_hits`; best for a dropdown of known rule names.
- Keyword/phrase search: use `match_phrase`; best for an MVP search box and consistent with the existing dashboard.
- Broader fuzzy search: use `wildcard`, `match`, or add a dedicated analyzed field; more flexible but requires clearer ES mapping and performance checks.

**Current Decision:** Use keyword/phrase search for MVP to stay consistent with the existing dashboard behavior.

**Risk If Unresolved:** Frontend controls may imply different semantics from the backend query; a dropdown suggests exact matching, while a search input suggests keyword matching.

**Resolution Criteria:**
- Decide whether the frontend control is a free-text search input or a rule-name dropdown.
- Update `docs/05_api_contract.md` to name the semantic clearly.
- Update `GET /api/v1/alerts` implementation and tests if the final decision differs from `match_phrase`.
