# Phân tích lỗi Phase A

Nhóm: Cá nhân Vũ Văn Hà

Người phụ trách: Vũ Văn Hà - 2A202602589

Nguồn: `artifacts/ragas_50q.json` (đã chạy live, 50 câu). Evaluator: `gemini-3.5-flash-lite` cho 4 metric sinh nhãn và `gemini-embedding-001` cho phần embedding; generation cũng dùng `gemini-3.5-flash-lite`.

## Điểm theo distribution

Lấy trực tiếp từ `per_distribution` của lượt chạy live:

| Metric | factual (20) | multi_hop (20) | adversarial (10) |
|---|---|---|---|
| faithfulness | 0.8500 | 0.7698 | 0.9000 |
| answer_relevancy | 0.8459 | 0.6955 | 0.9041 |
| context_precision | 0.9167 | 0.5333 | 0.9333 |
| context_recall | 0.8000 | 0.6542 | 0.7233 |
| avg_score | 0.8531 | 0.6632 | 0.8652 |

Nhóm yếu nhất là `multi_hop` (avg_score 0.6632). Nguyên nhân nổi bật là `context_precision` chỉ 0.5333: với câu hỏi nhiều bước, ba context được trả về cho `RERANK_TOP_K=3` thường chứa cả chunk của bước trung gian lẫn chunk không liên quan tới bước cuối, nên evaluator đánh dấu phần lớn context là nhiễu.

## Bottom 10 và nguyên nhân

| Rank | question_id | distribution | avg_score | worst_metric | diagnosis | suggested_fix |
|---:|---|---|---:|---|---|---|
| 1 | 33 | multi_hop | 0.1250 | faithfulness | LLM hallucinating | Tighten system prompt, lower temperature |
| 2 | 5 | factual | 0.2500 | answer_relevancy | Answer doesn't match question | Improve prompt template |
| 3 | 27 | multi_hop | 0.2500 | answer_relevancy | Answer doesn't match question | Improve prompt template |
| 4 | 6 | factual | 0.3333 | faithfulness | LLM hallucinating | Tighten system prompt, lower temperature |
| 5 | 30 | multi_hop | 0.3750 | answer_relevancy | Answer doesn't match question | Improve prompt template |
| 6 | 39 | multi_hop | 0.4747 | context_precision | Too many irrelevant chunks | Add reranking or metadata filter |
| 7 | 35 | multi_hop | 0.5282 | context_precision | Too many irrelevant chunks | Add reranking or metadata filter |
| 8 | 50 | adversarial | 0.5754 | faithfulness | LLM hallucinating | Tighten system prompt, lower temperature |
| 9 | 22 | multi_hop | 0.5833 | answer_relevancy | Answer doesn't match question | Improve prompt template |
| 10 | 21 | multi_hop | 0.6089 | context_precision | Too many irrelevant chunks | Add reranking or metadata filter |

7/10 câu bottom thuộc `multi_hop`, khớp với kết luận ở trên. Nhóm lỗi chia làm ba loại: câu multi_hop có context đúng nhưng câu trả lời lệch hoặc bịa (faithfulness, answer_relevancy), câu có context nhiễu (context_precision), và các câu hỏi đơn giản bị trả lời lệch trọng tâm dù pipeline chỉ nạp 107 chunk từ corpus mẫu của lab.

Câu 33 (multi_hop, avg_score 0.125) là ví dụ rõ nhất cho lỗi retrieval + generation: khi các bước trung gian không có trong ba context được trả về, mô hình vẫn sinh đáp án và bị đánh dấu không trung thực với context.

## Matrix và nhóm yếu nhất

| Metric | factual | multi_hop | adversarial |
|---|---|---|---|
| faithfulness | 3 | 5 | 1 |
| answer_relevancy | 10 | 5 | 3 |
| context_precision | 2 | 7 | 1 |
| context_recall | 5 | 3 | 5 |

Tổng mỗi cột đúng bằng kích thước nhóm (20/20/10) vì đây là phân bố worst_metric, không phải thước đo chất lượng. Metric xuất hiện nhiều nhất toàn bảng là `answer_relevancy` (18 câu), nhưng nhóm yếu vẫn là `multi_hop` vì mean `avg_score` thấp nhất. Hai con số này không mâu thuẫn: phần lớn câu `factual` có worst_metric là `answer_relevancy` nhưng điểm của chúng vẫn cao.

## Bẫy adversarial và giới hạn

Kết quả live **không** cho thấy adversarial yếu hơn factual: `adversarial` có avg_score 0.8652, cao hơn `factual` 0.8531 và là nhóm mạnh nhất. Nhóm yếu thật sự là `multi_hop`. Vì vậy kết luận rằng "adversarial là bẫy version conflict và phủ định" không được dữ liệu lượt chạy này ủng hộ, và nhóm không ghi nhận bonus hạng mục này.

Giới hạn cần nêu rõ về chính lượt đo:

- 25/200 ô metric ra 0.0 do evaluator không parse được output, thể hiện ở log `Failed to parse output. Returning None.` và `ValidationError ... ContextPrecisionVerifications`. Phân bố: context_precision 9 câu, faithfulness 6, answer_relevancy 6, context_recall 4. Đây là lỗi định dạng output của evaluator, không phải lỗi pipeline; các câu đó có thể điểm thấp hơn thực tế.
- Vì một số câu bị 0.0, mean theo từng metric và avg_score ở trên là **ước lượng thấp**; phải đọc cùng với số câu bằng 0 khi so sánh, không coi là điểm tuyệt đối.
- Thang điểm phụ thuộc evaluator đã dùng: mọi so sánh giữa các phase phải dùng cùng `gemini-3.5-flash-lite` và `gemini-embedding-001`.
