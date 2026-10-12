# Nhóm thực hiện K4 Track 3A

Tên nhóm: ABTC

Repo chung: local workspace `K4-Track-3A-Day24-ABTC-Eval-Guard`

Trưởng nhóm/người nộp: Vũ Văn Hà - 2A202602589

Ngày lab/deadline áp dụng: 2026-10-12, Asia/Ho_Chi_Minh (UTC+07:00)

Commit dùng để chấm: sẽ cập nhật sau khi commit/push repo nộp bài.

## Thành viên và phân công

| STT | Họ và tên | MSSV | Vai trò / công việc thật | Bằng chứng |
|---|---|---|---|---|
| 1 | Vũ Văn Hà | 2A202602589 | Làm một mình: hoàn thành `src/phase_a_ragas.py`, `src/phase_b_judge.py`, `src/phase_c_guard.py`; kiểm tra unit/mock; chuẩn bị báo cáo | Source phase A/B/C, test log `86 passed, 3 deselected` |

Người tích hợp/chạy batch/nộp link: Vũ Văn Hà - tự tích hợp source, chạy unit tests, chuẩn bị repo để nộp.

## Môi trường và chuẩn bị trước lớp

OS/Python/compiler: Windows, chạy PowerShell trong workspace dự án; Python hiện tại chạy được pytest.

Virtualenv/dependencies/imports: đã tạo lại `.venv` bằng Python 3.11.9, cài runtime dependencies, cài `annoy` trong `.venv`, hạ `pyarrow` về 15.0.2 để tương thích NumPy 1.26. Kết quả kiểm tra: `.venv\Scripts\python.exe -m pip check` báo `No broken requirements found`; `.venv\Scripts\python.exe -m pytest tests/ -q` báo `86 passed, 3 deselected`.

Models/Qdrant/50 answers đã chuẩn bị: đã chạy `.venv\Scripts\python.exe scripts\setup_answers.py --live` và tạo `artifacts/answers_50q.json` đủ 50 câu với distribution 20 factual, 20 multi_hop, 10 adversarial; cả 50 câu đều ở `generation_mode=llm` với `generation_model=gemini-3.5-flash-lite`. Ba artifact Phase A/B/C đã chạy live và được `scripts\check_lab.py --with-tests` xác nhận pass.

Provider dùng cho toàn bộ phase: Gemini qua OpenAI-compat endpoint (`GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai`), model `gemini-3.5-flash-lite` cho generation/judge/evaluator/guard, `gemini-embedding-001` cho embeddings của RAGAS. Chỉ giữ trong `.env`, `.env.example` không có key thật.

Ba điểm phải xử lý khi chuyển sang provider này, đều đã được sửa trong source và ghi lại ở `doc/reports/blueprint.md`:

1. NeMo Guardrails 0.10 chọn `ChatOpenAI` hay `OpenAI` (completions) bằng substring tên model (`"gpt-3.5"`/`"gpt-4"`), nên model Gemini bị đẩy sang endpoint legacy `/completions` và trả 404. Đã đăng ký provider `engine: gemini` trỏ thẳng về `ChatOpenAI` trong `setup_nemo_rails()`.
2. NeMo ép `max_tokens=3` cho self-check; Gemini 3 mặc định bật thinking nên 3 token bị thinking dùng hết, completion rỗng và mọi input đều bị block. Đã khai báo `max_tokens: 64` cho `self_check_input` và `self_check_output` trong `guardrails/config.yml`.
3. Gemini free tier giới hạn 15 request/phút và 500 request/ngày cho mỗi model. Đã thêm `call_llm` (backoff 429) và `LATENCY_SAMPLE_INTERVAL_S` để các mẫu latency không đo nhầm thời gian chờ rate limit.

## INDIVIDUAL

### VuVanHa-2A202602589

- Phần được giao và phần thực tế đã làm: hoàn thành toàn bộ hàm TODO của Phase A, Phase B và Phase C theo contract trong đề bài. Phase A gồm grouping, RAGAS adapter, bottom 10 và cluster analysis. Phase B gồm pairwise judge JSON, swap-and-average, Cohen kappa và bias report. Phase C gồm PII scan, input/output rail, adversarial suite và đo latency input layers.
- Bằng chứng: các file `src/phase_a_ragas.py`, `src/phase_b_judge.py`, `src/phase_c_guard.py`; báo cáo trong `doc/reports/`.
- Cách kiểm tra: chạy `.venv\Scripts\python.exe -m pytest tests/test_phase_a.py tests/test_phase_b.py tests/test_phase_c.py -q` được `26 passed`; chạy toàn bộ test được `86 passed, 3 deselected`. `scripts\check_lab.py --with-tests` báo `0 failed checks`, tức đã pass answers và cả ba artifact Phase A/B/C.
- Điều đã học: phân biệt đánh giá RAGAS theo từng metric, calibration nhãn 0/1 khác với pairwise A/B, và guardrail phải kiểm tra cả attack lẫn clean controls để tránh always-block. Trong lúc chạy thật còn phát hiện hai lỗi chỉ lộ ra ở live: `PERSON` mặc định của Presidio gắn nhầm tiếng Việt nên chặn nhầm clean controls, và prompt judge Phase B không nêu schema JSON nên Gemini tự chế schema khác.
- Kết quả live đã đo: Phase A 50 câu với RAGAS 4 metric trên `gemini-3.5-flash-lite` + `gemini-embedding-001`; Phase B 5 cặp swap-and-average và κ = 1.0 trên 10 nhãn binary; Phase C 20/20 attacks bị chặn, 8/8 clean được cho qua (false-positive rate = 0), 4/4 output đúng kỳ vọng, latency input layers p95 = 3166.5 ms so với budget 500 ms.
- Giới hạn/cách xử lý: latency p95 của input guard vượt budget 500 ms vì một lần gọi Gemini qua REST khoảng 793 ms (p50); đã giãn cách 4.5 giây giữa các mẫu và thêm backoff 429 để số đo không lẫn thời gian chờ rate limit, nhưng vẫn ghi nguyên số thật và không nâng ngưỡng. 25/200 ô metric RAGAS bằng 0 do evaluator không parse được output của model, không phải do pipeline; đã ghi rõ trong `doc/reports/failure_clusters.md`.
- Nguồn/AI hỗ trợ nếu có: dùng Codex để đọc đề, hiện thực các hàm, chuyển provider sang Gemini, chạy test và soạn báo cáo; kết quả được tự kiểm chứng bằng unit tests trong repo và bằng các artifact live trong `artifacts/`.

## Cập nhật sau khi nộp

Chưa có cập nhật sau nộp. Khi có commit cuối và link GitHub, cập nhật lại dòng commit dùng để chấm.
