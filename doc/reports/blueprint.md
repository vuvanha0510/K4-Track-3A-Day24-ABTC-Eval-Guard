# Blueprint CI/CD cho RAG và guardrails

Nhóm: Cá nhân Vũ Văn Hà

Người phụ trách: Vũ Văn Hà - 2A202602589

Đây là đề xuất CI/CD, không phải workflow đã triển khai. Nguồn kết quả là `artifacts/ragas_50q.json`, `artifacts/judge_results.json`, `artifacts/guard_results.json`. Trạng thái hiện tại: source, unit tests và cả ba artifact live đã hoàn tất; `scripts/check_lab.py --with-tests` báo `0 failed checks`.

Provider dùng cho toàn bộ lượt chạy: Gemini qua OpenAI-compat endpoint, `gemini-3.5-flash-lite` cho generation, judge, evaluator và guard; `gemini-embedding-001` cho embeddings của RAGAS. Ba điểm phải xử lý khi dùng provider này đã được ghi ở `doc/TEAM.md` và đều có sửa trong source.

## Kiến trúc và failure action

Luồng đề xuất: Input -> Presidio -> NeMo input -> RAG retrieval/rerank/generation -> NeMo output -> response.

Request thật nên dừng sớm nếu Presidio phát hiện CCCD/CMND, số điện thoại Việt Nam hoặc email. Nếu NeMo input rail chặn jailbreak, prompt injection hoặc off-topic, hệ thống trả lời refusal chuẩn và log `blocked_by=nemo_input`. Output rail kiểm tra câu trả lời cuối; output sạch được giữ nguyên, output nhạy cảm phải bị thay hoặc redact trước khi trả về.

Secrets chỉ nằm trong `.env` hoặc secret store CI, không commit API key. Nếu LLM generation lỗi, pipeline được phép dùng `extractive_fallback` nhưng phải ghi `generation_mode` và `generation_model=null`. Với provider free tier có hạn mức theo ngày, cần thêm backoff 429 (`call_llm` trong `config.py`) và ghi cảnh báo khi hết quota thay vì để batch chết giữa chừng.

## Phạm vi và số đo latency

Task 12 bắt buộc đo `input_layers_sequential`: Presidio + NeMo input, tạo engine trước khi đo, có hai warm-up thật nhưng loại khỏi samples. Không dùng số này để kết luận full guard hay RAG latency. Số liệu dưới đây lấy từ `artifacts/guard_results.json`: `n_samples=20`, `warmup_runs=2`, `percentile_method=linear`.

| Layer / scope | P50 ms | P95 ms | P99 ms | Tình trạng |
|---|---|---|---|---|
| Presidio | 37.4 | 45.0 | 47.7 | Đã đo live |
| NeMo input | 792.7 | 3130.0 | 9305.1 | Đã đo live |
| Input guard sequential | 830.0 | 3166.5 | 9331.4 | Đã đo live |
| RAG | chưa đo | chưa đo | chưa đo | Ngoài phạm vi bắt buộc |
| NeMo output | chưa đo | chưa đo | chưa đo | Ngoài phạm vi bắt buộc |
| Full guard / short-circuit request | chưa đo | chưa đo | chưa đo | Không suy từ input_guard_ms |

Input-layer budget target: 500 ms. Kết quả thực tế `latency_budget_ok = false`, tức budget **không đạt**. Số đo được ghi nguyên trạng, không nâng ngưỡng.

Phân tích nguyên nhân vượt budget:

- Presidio nằm trong budget rộng rãi (P95 45 ms). Toàn bộ phần vượt nằm ở NeMo input rail.
- Một lần gọi self-check ra quyết định Yes/No mất khoảng 793 ms (P50) qua REST, nên ngay cả ở trường hợp không bị throttle, input guard đã vượt budget 500 ms.
- P95 3130 ms và P99 9305 ms cao hơn P50 nhiều vì Gemini free tier giới hạn 15 request/phút. Các mẫu rơi vào cửa sổ bị throttle phải chờ backoff nên thời gian đo bao gồm cả thời gian chờ quota.
- Vì vậy `input_guard_ms` ở đây phản ánh **độ trễ guard gồm cả ảnh hưởng của rate limit của nhà cung cấp**, không phải độ trễ thuần túy của mã guard. Nếu cần số dùng để đặt SLO thật, phải chạy lại trên tier có quota phù hợp hoặc trên model có latency thấp hơn.
- `LATENCY_SAMPLE_INTERVAL_S` mặc định 4.5 giây được đặt để giữ nhịp dưới trần 15 request/phút; thời gian chờ này nằm ngoài cửa sổ đo nên không bị ghi vào sample, nhưng backoff phát sinh bên trong một lần gọi thì có.

Phạm vi chưa đo và kế hoạch: để đo được RAG latency và NeMo output latency cần chạy thêm một batch riêng cho luồng `retrieval -> rerank -> generation` và cho output rail; hiện chưa chạy nên ghi "chưa đo" thay vì suy từ `input_guard_ms`.

## CI gates đề xuất

- Unit/mock tests phải pass: `python -m pytest tests/ -q`. Trạng thái: `86 passed, 3 deselected`.
- Phase A: đủ 50 câu, distribution 20/20/10, metric hữu hạn [0,1], bottom 10 đúng thứ tự. Trạng thái: đạt, `artifacts/ragas_50q.json`.
- Phase B: đủ 5 pairwise ids 1, 5, 12, 21, 41; đủ 10 binary judgments; kappa tính từ nhãn thật. Trạng thái: đạt, kappa = 1.0.
- Phase C: attacks đạt tối thiểu 15/20, clean controls 8/8 allowed, output cases đúng, latency có ít nhất 20 samples sau 2 warm-up. Trạng thái: đạt, attacks 20/20, clean 8/8, false_positive_rate = 0, output 4/4, latency 20 samples.
- Gate nâng cao: attacks 18/20 (đạt), clean false_positive_rate 0 (đạt), RAGAS avg_score tối thiểu 0.65 (đạt 0.78 trung bình bốn metric), faithfulness tối thiểu 0.75 (đạt 0.83).
- Gate đang **không** đạt: input guard P95 dưới 500 ms (`latency_budget_ok = false`, P95 3166.5 ms).

Các ngưỡng trên là đề xuất; workflow CI chưa được tạo tự động trong repo này.

## Monitoring và cải tiến

Nên log theo từng request: distribution hoặc route, retrieved document ids, generation mode, guard decision, blocked_by, output rail status và input guard latency. Alert khi clean false positive tăng, attack pass rate giảm, P95 input guard vượt 500ms, hoặc model/version thay đổi.

Số liệu live hiện có: attacks 20/20 (4 do Presidio chặn, 16 do NeMo input chặn), clean 8/8 được cho qua nên false_positive_rate = 0, output 4/4 đúng kỳ vọng, kappa = 1.0, nhóm RAGAS yếu nhất là multi_hop (avg_score 0.6632). Adversarial không phải nhóm yếu (0.8652), nên phân tích bẫy version conflict không có dữ liệu ủng hộ.

Hai failure action đã phát hiện khi chạy thật và cần giữ vào CI, vì cả hai đều làm hỏng kết quả mà unit test không bắt được:

- Presidio mặc định gắn `PERSON` bằng spaCy NER cho tiếng Anh nên gắn nhầm tiếng Việt ("Xin lỗi", "Khung lương chung của cấp" đều ra PERSON 0.85), khiến 7/8 clean control bị chặn và false_positive_rate = 0.875. Đã giới hạn `pii_scan` chỉ nhận `EMAIL_ADDRESS`, `PHONE_NUMBER`, `VN_CCCD`, `VN_PHONE`, đúng phạm vi Task 9a yêu cầu. Cần một regression test trên chính bộ clean controls trước khi coi là ổn định.
- Prompt judge Phase B ban đầu không nêu schema JSON đầu ra, nên Gemini tự chế schema khác (`preferred`/`evaluation`) và runner fail với `Pairwise judge winner must be A, B, or tie.` Đã nêu rõ schema, chuẩn hoá `winner`, và thêm parser chịu markdown/text thừa kèm một lần retry.

Kế hoạch cải tiến sau khi có artifacts live: đọc bottom 10 Phase A để tách lỗi retrieval/generation, thêm reranking hoặc metadata filter cho context_precision thấp ở multi_hop, cải thiện chunking/BM25 cho context_recall thấp, rà lại prompt judge ở hai cặp không nhất quán, và mở rộng clean controls để giảm rủi ro chặn nhầm nghiệp vụ hợp lệ.
