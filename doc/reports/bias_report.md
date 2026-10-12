# Đánh giá LLM Judge Phase B

Nhóm: Cá nhân Vũ Văn Hà

Người phụ trách: Vũ Văn Hà - 2A202602589

Nguồn: `artifacts/judge_results.json` (đã chạy live). Judge: `gemini-3.5-flash-lite` cho cả pairwise judge và binary judge, qua Gemini OpenAI-compat endpoint.

## Năm cặp A/B và hai lượt

Nguồn cố định theo đề bài, đúng như `pair_sources` ghi trong artifact:

| Thành phần | Nguồn |
|---|---|
| Candidate A | `artifacts/answers_50q.json:answer` |
| Candidate B | `fixtures/human_labels_10q.json:model_answer` |
| Reference | `fixtures/test_set_50q.json:ground_truth` |
| Question ids | 1, 5, 12, 21, 41 |

Candidate A là câu trả lời do pipeline sinh bằng LLM (`generation_mode=llm`, `generation_model=gemini-3.5-flash-lite`), không phải trích đoạn.

| id | winner lượt 1 (A/B) | winner lượt 2 sau khi đổi thứ tự | final | position_consistent | scores lượt 1 | scores lượt 2 (đã quy về A/B gốc) |
|---:|---|---|---|---|---|---|
| 1 | B | B | B | true | A 0.8 / B 1.0 | A 0.8 / B 0.9 |
| 5 | tie | A | tie | false | A 0.0 / B 0.0 | A 0.2 / B 0.0 |
| 12 | tie | B | tie | false | A 1.0 / B 1.0 | A 0.7 / B 1.0 |
| 21 | B | B | B | true | A 0.5 / B 1.0 | A 0.5 / B 1.0 |
| 41 | A | A | A | true | A 0.9 / B 0.4 | A 0.95 / B 0.2 |

Ba cặp có consensus rõ (1, 21, 41). Hai cặp 5 và 12 bất đồng nên `final_winner` là `tie` theo đúng quy tắc chỉ nhận consensus khi hai lượt đồng ý.

Nhìn nội dung scores thay vì chỉ nhìn chữ "tie": ở cặp 12, lượt 1 chấm A = B = 1.0 và lượt 2 chấm B = 1.0, A = 0.7, nên lượt 2 vẫn nghiêng về B cùng hướng với lượt 1 nhưng chênh điểm quá nhỏ để coi là đồng thuận. Việc quy về `tie` là bảo thủ đúng thiết kế, nhưng cũng cho thấy scores của judge không tách được hai answer gần nhau.

## Calibration đúng model_answer

Binary judge chạy trên đúng `question` và `model_answer` của `fixtures/human_labels_10q.json`, kèm `ground_truth` làm reference. `human_label` và `human_note` không được đưa vào prompt.

| question_id | nhãn judge | nhãn người |
|---|---|---|
| 1 | 1 | 1 |
| 5 | 0 | 0 |
| 12 | 1 | 1 |
| 21 | 1 | 1 |
| 23 | 1 | 1 |
| 29 | 0 | 0 |
| 33 | 1 | 1 |
| 41 | 0 | 0 |
| 46 | 1 | 1 |
| 50 | 0 | 0 |

**Cohen kappa = 1.0** trên 10 nhãn, tức judge khớp hoàn toàn bộ nhãn người. Với n = 10 và độ khớp tuyệt đối, kappa bị chạm trần: không có mâu thuẫn nào để tách độ tin cậy của ước lượng, nên con số này nên đọc cùng kích thước mẫu, không đọc như độ chính xác tuyệt đối của judge trên dữ liệu khác.

## Bias và giới hạn

| Chỉ số | Giá trị live |
|---|---|
| total_judged | 5 |
| position_bias_count | 2 |
| position_bias_rate | 0.4 |
| verbosity_bias | 0.333 |
| verbosity_details | a_wins_a_longer 1, b_wins_b_longer 0, total_decisive 3 |

Position bias rate 0.4 là cao, nhưng mẫu chỉ có 5 cặp nên mỗi cặp là 20%. Hai cặp bất đồng đều kết thúc bằng scores không tách được hai bên, nên chưa thể kết luận judge ưu tiên vị trí A hay B một cách có hệ thống; cần đọc reasoning của từng lượt trước khi quy kết. Verbosity bias 0.333 dựa trên 3 cặp có winner rõ nên quá nhỏ để suy ra xu hướng.

Giới hạn cần nêu:

- Năm cặp là đúng số cặp bắt buộc của đề, không phải mẫu đủ lớn để kết luận thống kê về bias. Mọi tỷ lệ ở trên phải đọc kèm mẫu n.
- Kappa = 1.0 có thể phản ánh bộ 10 `model_answer` tương đối dễ phân biệt, không khẳng định judge tốt trên mọi loại câu hỏi.
- Việc dùng cùng một model cho generation, judge và evaluator khiến phần điểm RAGAS và phần điểm judge cùng chia sẻ điểm yếu của model đó; đây là hệ quả của việc chỉ có một provider free tier, ghi lại để không diễn giải quá đà khi so sánh số liệu giữa các phase.
