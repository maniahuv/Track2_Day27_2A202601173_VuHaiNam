# Incident Report

> **Lưu ý phạm vi:** Phase 6 (Mystery incident) đòi hỏi giảng viên cung cấp một
> dataset/fault riêng mà học viên không được xem script tạo ra. Dataset đó
> chưa có trong lần làm bài này, nên report dưới đây dùng lại public fault
> `volume_drop` (`scripts/inject_fault.py volume_drop`) làm case study thật —
> khớp đúng với scenario mở đầu của lab ("CEO thấy revenue giảm bất thường").
> Toàn bộ số liệu là kết quả chạy thật, log đầy đủ tại
> `reports/evidence/phase7_incident_investigation.txt`. Khi có mystery
> dataset thật từ giảng viên, thay dữ liệu và lặp lại đúng quy trình điều tra
> này (không đổi cấu trúc report).

## Severity
**P2** — Dashboard doanh thu cho CEO bị sai lệch nghiêm trọng (revenue/số đơn
báo cáo thấp hơn thực tế ~75%), có thể dẫn tới quyết định kinh doanh sai nếu
không phát hiện kịp thời. Không phải P1 vì: không có mất dữ liệu vĩnh viễn,
không có bản ghi sai định dạng/trùng khóa, dữ liệu gốc có thể tái nạp đầy đủ.

## Summary
Ingestion đơn hàng chỉ nạp được 150/600 dòng của ngày (giữ 25% đầu file,
tương tự lỗi export/job upstream bị cắt giữa chừng). Pipeline vẫn chạy xong,
không có lỗi hệ thống, không có bản ghi null/trùng/sai định dạng — nên
`contract_validator`/Great Expectations báo **0 lỗi, PASS hoàn toàn**. Chỉ có
tầng anomaly detection (dựa trên lịch sử cùng thứ trong tuần) phát hiện được
số dòng thấp bất thường. Vì thiếu 450 đơn hàng completed, `fct_daily_revenue`
tính doanh thu ngày đó thấp hơn thực tế, lan tới CEO dashboard.

## Detection
- Signal: `row_count_anomaly` từ `detect_metric(..., method="auto")` trong
  `python scripts/run_baseline.py` — `is_anomaly=True`,
  `method=auto:same_segment_history+mad`, `score=5.53` (baseline cùng thứ
  trong tuần gần nhất: `[247, 262, 268, 235, 235, 258]`).
- **Contract/GX validation KHÔNG bắt được sự cố này** (19/19 check pass, 0
  lỗi) — vì mọi dòng còn lại vẫn hợp lệ ở cấp hàng (not-null/unique/type/
  accepted-values đều đúng), pipeline "SUCCESS" một cách đánh lừa. Đây đúng
  là ví dụ cho nguyên tắc mở đầu README: *"pipeline SUCCESS không có nghĩa
  data đúng"* — cần một tầng tín hiệu khác (anomaly) để phát hiện completeness
  issue mà contract cấp hàng không thể thấy.
- First observed time: `2026-08-29T15:11:44Z` (thời điểm file `orders.csv`
  trong `data/incoming/` bị ghi lại với 150 dòng — mốc T1 trong log điều tra).

## Root Cause
Tệp `data/incoming/orders.csv` bị ghi đè bởi một phiên bản chỉ chứa 150/600
dòng (giữ đúng phần đầu file) — mô phỏng lỗi partial-write/truncation từ job
upstream (ví dụ: job export bị timeout/kill giữa chừng nhưng vẫn ghi file
"thành công" một phần, hoặc pagination bị dừng sớm). Không có exception nào
được raise nên hệ thống downstream (dbt, dashboard) coi đây là dữ liệu hợp lệ
và xử lý bình thường trên tập 150 dòng.

## Evidence
1. **Contract/GX (tầng 1 — không phát hiện được):**
   `validate_orders(...)` trên 150 dòng còn lại → `19 checks, 0 failed`.
   `gx/validate_orders.py` → 4/4 expectation `success=True`, "Starter GX
   result: PASS". Xác nhận: đây không phải data-quality issue cấp hàng.
2. **dbt build (tầng 2 — vẫn xanh, vì đúng là không có lỗi transform):**
   `dbt build` trên seed 150 dòng → `Done. PASS=18 WARN=0 ERROR=0 SKIP=0`.
   `fct_daily_revenue` vẫn build đúng logic, chỉ là tổng doanh thu thấp hơn vì
   input ít hơn — dbt không có cách nào biết 150 có "đủ" hay không nếu không
   có một test kiểm tra volume/completeness (xem Prevention).
3. **Anomaly detection (tầng 3 — tầng duy nhất bắt được):**
   `row-count anomaly: True (auto:same_segment_history+mad, score=5.53)` khi
   so với baseline cùng thứ trong tuần gần nhất. Để loại trừ khả năng đây chỉ
   là artifact của việc dữ liệu demo tĩnh (đã ghi nhận ở Phase 3 với ngày cuối
   tuần), đã kiểm tra chéo: so `current=150` với **cả 7 baseline ngày trong
   tuần có thể có** → `is_anomaly=True` ở toàn bộ 7/7 trường hợp, score dao
   động 5.53–52.72 (thấp nhất vẫn > ngưỡng 3.5 rất nhiều). Kết luận: đây là sự
   cố thật, không phải nhiễu từ cách baseline được tạo.
4. **Lineage (blast radius — xem mục riêng bên dưới).**
5. **SLO (định lượng mức độ nghiêm trọng):** coi mỗi lần chạy pipeline ngày là
   1 check với SLO hoàn chỉnh dữ liệu giả định 99% —
   `slo_status(0.99, bad_events=1, total_events=1)` →
   `actual_bad_rate=1.0`, `allowed_bad_rate=0.01`, `burn_rate≈100`,
   `breached=True`. Một burn rate ~100x là mức khẩn cấp cao nhất theo chính
   sách `multiwindow_burn` (Phase 5) nếu sự cố này lặp lại ở nhiều lần chạy
   liên tiếp (sustained) — cần page ngay, không chỉ ticket.

## Blast Radius
Dataset-level (`downstream_assets(dataset_graph, "stg_orders")`):
```text
stg_orders
-> fct_daily_revenue      (doanh thu ngày bị tính thiếu ~75%)
-> ceo_revenue_dashboard  (CEO nhìn thấy số liệu sai)
```
Column-level (`column_downstream(column_graph, "raw_orders.amount")`) — theo
đúng đường tiền chảy qua transform:
```text
raw_orders.amount
-> stg_orders.amount_usd
-> fct_daily_revenue.daily_revenue
-> ceo_revenue_dashboard.revenue
```
`kb_documents`/RAG/support agent **không** nằm trong blast radius của sự cố
này (chỉ liên quan đến nhánh `orders`, không đụng tới `kb_documents`).

## Mitigation
1. Gắn cờ "unreliable" cho số liệu `ceo_revenue_dashboard` của ngày bị ảnh
   hưởng ngay khi anomaly được phát hiện (thay vì để dashboard hiển thị số
   sai mà không cảnh báo).
2. Báo data engineering kiểm tra job ingest upstream (log job export, kiểm
   tra exit code/row count kỳ vọng so với thực nhận).
3. Re-ingest lại đầy đủ 600 dòng của ngày đó thay vì chỉ chấp nhận 150 dòng
   đã có — không "vá" bằng cách nội suy/ước lượng số thiếu.
4. `recommended_action` từ `pipeline_action(issues)` (Phase 1) trả về
   `"none"` trong sự cố này — đúng vì không có row nào vi phạm contract cấp
   hàng. Đây là khoảng trống cần vá: contract hiện tại không có rule cấp
   *dataset* (ví dụ "row_count tối thiểu theo ngày"), nên `pipeline_action`
   không thể tự động block/quarantine một sự cố completeness thuần túy — hành
   động chặn dashboard hiện phải dựa vào tín hiệu anomaly, không phải contract
   (ghi nhận vào Prevention bên dưới).

## Recovery
Mô phỏng re-ingest đầy đủ bằng `python scripts/reset_lab.py` lúc
`2026-08-29T15:12:08Z` (T2) — khôi phục `orders.csv` về 600 dòng.

## Verification
- [x] Contract healthy — `critical contract fails: 0` (đã healthy cả trước
      và sau sự cố, vì đây không phải contract-level issue).
- [x] dbt tests healthy — `dbt build` sau recovery: 18/18 PASS.
- [x] anomaly trở lại đúng dải kỳ vọng — `orders rows: 600` (khớp file
      baseline gốc); do hôm chạy thật là Thứ Bảy nên `is_anomaly` vẫn hiện
      `True/score=18.75` ngay cả ở trạng thái khỏe (đây là artifact đã biết
      của bộ dữ liệu demo tĩnh — xem `reports/agent_log.md` Decision 3, không
      phải sự cố thật); điểm cần verify đúng là **row count đã về đúng 600**,
      không phải giá trị boolean `is_anomaly` của riêng ngày demo này.
- [x] SLO hiểu rõ ngân sách lỗi — đã tính `burn_rate≈100` lúc sự cố, quay về
      0 khi `bad_events=0` sau recovery.
- [x] downstream output verified — `fct_daily_revenue`/`ceo_revenue_dashboard`
      build lại đúng trên 600 dòng qua `dbt build` (18/18 PASS).

## Prevention / Action Items
| Action | Owner | Deadline | Why |
|---|---|---|---|
| Thêm contract rule cấp **dataset** (vd `min_row_count`/`expected_row_count_range` theo ngày) vào `contracts/orders_contract.yaml` + `src/contract_validator.py`, không chỉ rule cấp hàng | Data platform | Sprint tới | Contract hiện tại chỉ thấy hàng riêng lẻ, không thấy "thiếu cả một mảng dữ liệu" — đây là lỗ hổng lớn nhất lộ ra từ sự cố này |
| Thêm alert tự động từ `detect_metric`/`multiwindow_burn` thẳng vào kênh on-call thay vì chỉ hiện trong `latest_metrics.json` | Data platform | Sprint tới | Hiện tại phải chạy `run_baseline.py` thủ công mới thấy anomaly; cần chạy tự động theo lịch + alert |
| Đối chiếu row count nhận được với row count kỳ vọng từ job upstream (checksum/manifest) trước khi đánh dấu ingest "SUCCESS" | Data engineering | 2 tuần | Ngăn chặn tận gốc, sớm hơn cả tầng anomaly detection |
| Gắn banner "data unreliable" trên CEO dashboard khi `contract_pipeline_action != "none"` HOẶC `row_count_anomaly.is_anomaly == True` | Analytics/BI | Sprint tới | Tránh CEO ra quyết định dựa trên số liệu đã biết là bất thường mà không có cảnh báo |
