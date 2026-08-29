# AI Agent Decision Log

Khong can copy full conversation. Ghi cac decision quan trong.

## Decision 1
- Hypothesis: `src/contract_validator.py` không phát hiện được type drift (vd `amount` chứa string) vì `pd.to_numeric(..., errors="coerce")` âm thầm biến giá trị lỗi thành NaN rồi bị `range` check bỏ qua (`invalid.fillna(False)`); và contract không kiểm tra freshness dù `contracts/orders_contract.yaml` đã khai báo `freshness.max_delay_minutes: 30`.
- Prompt / request to agent: "Hoàn thiện Phase 1: thêm type validation, freshness validation, và severity→action (block/quarantine/warn) vào src/contract_validator.py, giữ nguyên stable API validate_orders(df, contract_path)."
- Agent proposal: thêm `_type_invalid_mask()` (kiểm tra riêng integer/number/datetime/boolean/string thay vì dựa vào side-effect của `to_numeric`), `_validate_freshness()` (so latest timestamp của cột freshness với `pd.Timestamp.now(tz="UTC")`), và `ACTION_BY_SEVERITY` map (critical→block, warning→quarantine, info→warn) gắn vào mọi issue qua `action_for_severity()`; thêm `pipeline_action()` để tổng hợp action nghiêm trọng nhất của cả batch. Cũng thêm 1 dòng in `recommended pipeline action` trong `scripts/run_baseline.py` để thấy action hoạt động thật khi chạy baseline.
- Evidence/test: chạy `pytest tests_public -q` → phát hiện `test_healthy_contract_passes_starter_checks` FAIL vì fixture dùng timestamp cứng "2026-08-28" (hơn 24h so với ngày chạy thật 2026-08-29), vượt ngưỡng freshness 30 phút — không phải lỗi logic. Sau khi sửa fixture sang timestamp tương đối (`_recent(minutes_ago)`), `pytest tests_public -q` → `10 passed`. Chạy `python scripts/inject_fault.py duplicate_pk` rồi `python scripts/run_baseline.py`: `critical contract fails: 1`, `recommended pipeline action: block`. Test thủ công thêm 2 case qua `student_api.validate_orders`: (A) `amount="one-hundred"` → issue `type` severity=critical action=block; (B) `updated_at` cũ 180 phút → issue `freshness` severity=warning action=quarantine. Log đầy đủ lưu tại `reports/evidence/phase1_before_fix.txt` và `reports/evidence/phase1_after_fix.txt`.
- Accept / reject / revise: Accept toàn bộ proposal của agent; revise thêm test fixture `tests_public/test_contracts.py` (đổi timestamp cứng sang tương đối) vì đây là lỗi dữ liệu test time-bomb, không phải lỗi validator.
- Why: type check tách riêng khỏi range check giúp phân biệt rõ "giá trị sai kiểu dữ liệu" và "giá trị đúng kiểu nhưng ngoài khoảng" — hai nguyên nhân gốc khác nhau khi điều tra incident. Action map theo severity giúp pipeline biết nên block/quarantine/warn thay vì chỉ biết pass/fail.

## Decision 2
- Hypothesis:
- Prompt / request to agent:
- Agent proposal:
- Evidence/test:
- Accept / reject / revise:
- Why:
