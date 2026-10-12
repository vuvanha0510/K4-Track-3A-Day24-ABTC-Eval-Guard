from __future__ import annotations

"""Phase B: LLM-as-Judge — pairwise, swap-and-average, Cohen κ, bias analysis."""

import json
import os
import re
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import OPENAI_API_KEY, JUDGE_MODEL, HUMAN_LABELS_PATH


@dataclass
class JudgeResult:
    question: str
    answer_a: str
    answer_b: str
    winner_pass1: str       # "A" | "B" | "tie"  (original order)
    winner_pass2: str       # "A" | "B" | "tie"  (after swap, ALREADY converted back)
    final_winner: str       # consensus after swap-and-average
    reasoning_pass1: str
    reasoning_pass2: str
    position_consistent: bool  # True if both passes agree on same answer
    scores_pass1: dict = field(default_factory=dict)  # {"A": float, "B": float}
    scores_pass2: dict = field(default_factory=dict)


# ─── Task 5: Pairwise Judge ───────────────────────────────────────────────────

def _parse_judge_json(content: str) -> dict:
    r"""Parse JSON của judge, chịu được output bọc markdown và text thừa.

    Model đôi khi trả ```json ... ```, có prose trước/sau, hoặc JSON hợp lệ
    rồi kèm câu giải thích. raw_decode lấy đúng object đầu tiên nên không bị
    "Extra data"; escape \u hỏng vẫn ném lỗi để retry chứ không đoán mò.
    """
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        if start == -1:
            raise
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
        return obj


def pairwise_judge(question: str, answer_a: str, answer_b: str, reference: str = "") -> dict:
    """Task 5: Gọi LLM để chọn answer tốt hơn (A hoặc B) theo 3 tiêu chí.

    Tiêu chí đánh giá:
        - Độ chính xác (accuracy): có khớp với thực tế chính sách không?
        - Độ đầy đủ (completeness): có trả lời đủ câu hỏi không?
        - Tính súc tích (conciseness): có thừa / thiếu thông tin không?

    Returns:
        {"winner": "A"|"B"|"tie", "reasoning": str, "scores": {"A": float, "B": float}}
    """
    # Implemented below.
    # PROMPT_TEMPLATE = '''Bạn là một expert đánh giá chất lượng câu trả lời RAG.
    #
    # Câu hỏi: {question}
    # Chính sách/đáp án tham chiếu: {reference}
    #
    # Answer A:
    # {answer_a}
    #
    # Answer B:
    # {answer_b}
    #
    # Đánh giá dựa trên 3 tiêu chí: độ chính xác, đầy đủ, súc tích.
    # Trả lời JSON (chỉ JSON, không text khác):
    # {{"winner": "A" hoặc "B" hoặc "tie", "reasoning": "giải thích ngắn gọn", "scores": {{"A": 0.0-1.0, "B": 0.0-1.0}}}}
    # '''
    #
    # from openai import OpenAI
    # client = OpenAI()
    # resp = client.chat.completions.create(
    #     model=JUDGE_MODEL,
    #     messages=[
    #         {"role": "system", "content": "Bạn là expert đánh giá RAG. Chỉ trả lời JSON."},
    #         {"role": "user",   "content": PROMPT_TEMPLATE.format(
    #             question=question, answer_a=answer_a, answer_b=answer_b,
    #             reference=reference)},
    #     ],
    #     response_format={"type": "json_object"},
    # )
    # return json.loads(resp.choices[0].message.content)
    prompt = {
        "question": question,
        "reference": reference,
        "answer_a": answer_a,
        "answer_b": answer_b,
        "criteria": ["accuracy against reference", "completeness", "conciseness"],
    }
    schema = ('{"winner": "A" | "B" | "tie", '
              '"reasoning": "giải thích ngắn gọn", '
              '"scores": {"A": 0.0-1.0, "B": 0.0-1.0}}')
    from openai import OpenAI
    from config import call_llm
    client = OpenAI()
    # 2 lần thử: lỗi JSON/parse là lỗi hình thức của model, không phải lỗi dữ liệu.
    for parse_attempt in range(2):
        resp = call_llm(
            client.chat.completions.create,
            model=JUDGE_MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content":
                    "You evaluate RAG answers. Return only one valid JSON object with exactly "
                    f'these keys: {schema}. "winner" must be the letter A, B or tie; "scores" '
                    "must contain both A and B as numbers between 0 and 1. Do not add any "
                    "other key and do not wrap the JSON in markdown. Never use backslash "
                    "escapes inside string values."},
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
        )
        try:
            result = _parse_judge_json(resp.choices[0].message.content)
            break
        except (json.JSONDecodeError, ValueError):
            if parse_attempt == 1:
                raise
    # Chuẩn hoá winner: model có thể trả "a"/"A " hoặc "answer_a"/"answer_b".
    if isinstance(result.get("winner"), str):
        alias = {"answer_a": "A", "answer_b": "B", "tie": "tie"}
        normalized = alias.get(result["winner"].strip().lower().replace(" ", "_"),
                               result["winner"].strip().upper())
        result["winner"] = normalized
    if result.get("winner") not in ("A", "B", "tie"):
        raise ValueError("Pairwise judge winner must be A, B, or tie.")
    scores = result.get("scores", {})
    if set(scores) != {"A", "B"}:
        raise ValueError("Pairwise judge scores must include A and B.")
    result["scores"] = {"A": float(scores["A"]), "B": float(scores["B"])}
    if any(value < 0 or value > 1 for value in result["scores"].values()):
        raise ValueError("Pairwise judge scores must be in [0, 1].")
    if not isinstance(result.get("reasoning"), str) or not result["reasoning"].strip():
        raise ValueError("Pairwise judge must include reasoning.")
    return result


# ─── Task 6: Swap-and-Average ─────────────────────────────────────────────────

def swap_and_average(question: str, answer_a: str, answer_b: str, reference: str = "") -> JudgeResult:
    """Task 6: Chạy pairwise 2 lần (hoán đổi thứ tự), lấy kết quả nhất quán.

    Lý do: LLM thường có position bias (ưu tiên answer xuất hiện trước).
    Bằng cách swap, ta phát hiện và giảm bias này.

    Logic:
        Pass 1: judge(q, A, B) → winner_1 (trong không gian A/B)
        Pass 2: judge(q, B, A) → winner_2_raw (trong không gian B/A)
        Convert: nếu winner_2_raw="A" thì thực ra là B (vì đã swap)
        Final:   nếu winner_1 == winner_2 → final = winner_1
                 nếu khác nhau → final = "tie"
    """
    # Implemented below.
    # pass1 = pairwise_judge(question, answer_a, answer_b, reference=reference)
    # pass2_raw = pairwise_judge(question, answer_b, answer_a, reference=reference)  # SWAP!
    #
    # # Convert pass2 back to original A/B space
    # swap_map = {"A": "B", "B": "A", "tie": "tie"}
    # winner_pass2 = swap_map[pass2_raw["winner"]]
    #
    # # Average: consensus only if both agree
    # if pass1["winner"] == winner_pass2:
    #     final = pass1["winner"]
    # else:
    #     final = "tie"  # disagreement = inconclusive
    #
    # position_consistent = (pass1["winner"] == winner_pass2)
    #
    # return JudgeResult(
    #     question=question, answer_a=answer_a, answer_b=answer_b,
    #     winner_pass1=pass1["winner"], winner_pass2=winner_pass2,
    #     final_winner=final,
    #     reasoning_pass1=pass1["reasoning"], reasoning_pass2=pass2_raw["reasoning"],
    #     position_consistent=position_consistent,
    #     scores_pass1=pass1["scores"],
    #     scores_pass2={"A": pass2_raw["scores"]["B"], "B": pass2_raw["scores"]["A"]},
    # )
    pass1 = pairwise_judge(question, answer_a, answer_b, reference=reference)
    pass2_raw = pairwise_judge(question, answer_b, answer_a, reference=reference)
    winner_pass2 = {"A": "B", "B": "A", "tie": "tie"}[pass2_raw["winner"]]
    position_consistent = pass1["winner"] == winner_pass2
    final = pass1["winner"] if position_consistent else "tie"
    return JudgeResult(
        question=question, answer_a=answer_a, answer_b=answer_b,
        winner_pass1=pass1["winner"], winner_pass2=winner_pass2, final_winner=final,
        reasoning_pass1=pass1["reasoning"], reasoning_pass2=pass2_raw["reasoning"],
        position_consistent=position_consistent,
        scores_pass1=pass1["scores"],
        scores_pass2={"A": pass2_raw["scores"]["B"], "B": pass2_raw["scores"]["A"]},
    )


# ─── Task 7: Cohen's κ ────────────────────────────────────────────────────────

def cohen_kappa(judge_labels: list[int], human_labels: list[int]) -> float:
    """Task 7: Tính Cohen's κ giữa LLM judge và human labels.

    Args:
        judge_labels:  nhãn từ LLM judge (0 = bad answer, 1 = good answer)
        human_labels:  nhãn từ human_labels_10q.json

    Returns:
        κ ∈ [-1, 1]
        Thang đo Landis-Koch: <0=poor, 0-0.2=slight, 0.2-0.4=fair,
                               0.4-0.6=moderate, 0.6-0.8=substantial, 0.8-1=almost perfect

    Gợi ý A — dùng scikit-learn:
        from sklearn.metrics import cohen_kappa_score
        return cohen_kappa_score(human_labels, judge_labels)

    Gợi ý B — tính tay:
        n = len(judge_labels)
        p_o = sum(j == h for j, h in zip(judge_labels, human_labels)) / n
        p_e = (judge_labels.count(1)/n * human_labels.count(1)/n +
               judge_labels.count(0)/n * human_labels.count(0)/n)
        κ = (p_o - p_e) / (1 - p_e) if p_e != 1 else 0
        return κ
    """
    if len(judge_labels) != len(human_labels) or not judge_labels:
        raise ValueError("judge_labels and human_labels must be non-empty and aligned.")
    if any(label not in (0, 1) for label in judge_labels + human_labels):
        raise ValueError("Cohen kappa labels must be binary integers 0/1.")
    n = len(judge_labels)
    observed = sum(j == h for j, h in zip(judge_labels, human_labels)) / n
    expected = sum(judge_labels.count(label) * human_labels.count(label) / n**2
                   for label in (0, 1))
    if expected == 1:
        return 1.0 if observed == 1 else 0.0
    return (observed - expected) / (1 - expected)


# ─── Task 8: Bias Report ──────────────────────────────────────────────────────

def bias_report(judge_results: list[JudgeResult]) -> dict:
    """Task 8: Đo lường position bias và verbosity bias.

    Position bias: LLM chọn answer theo vị trí (A hay B) thay vì chất lượng.
        → Đo bằng % cases where position_consistent = False

    Verbosity bias: LLM ưu tiên answer dài hơn dù không chính xác hơn.
        → Đo bằng: trong các case A thắng, A có dài hơn B không? Tương tự cho B.

    Returns:
        {
          "total_judged": int,
          "position_bias_rate": float,        # 0-1, cao = bias nhiều
          "position_bias_count": int,
          "verbosity_bias": float,            # 0-1, > 0.6 = đáng lo ngại
          "verbosity_details": {
            "a_wins_a_longer": int,           # A thắng VÀ A dài hơn
            "b_wins_b_longer": int,           # B thắng VÀ B dài hơn
            "total_decisive": int,            # tổng case có winner rõ ràng
          },
          "interpretation": str,
        }
    """
    # Implemented below.
    # total = len(judge_results)
    # if total == 0:
    #     return {"total_judged": 0, "position_bias_rate": 0.0, "verbosity_bias": 0.0}
    #
    # position_bias_count = sum(1 for r in judge_results if not r.position_consistent)
    # position_bias_rate  = position_bias_count / total
    #
    # a_wins_a_longer = sum(
    #     1 for r in judge_results
    #     if r.final_winner == "A" and len(r.answer_a) > len(r.answer_b)
    # )
    # b_wins_b_longer = sum(
    #     1 for r in judge_results
    #     if r.final_winner == "B" and len(r.answer_b) > len(r.answer_a)
    # )
    # decisive = sum(1 for r in judge_results if r.final_winner != "tie")
    # verbosity_bias = (a_wins_a_longer + b_wins_b_longer) / decisive if decisive > 0 else 0.0
    #
    # interpretation = ("Position bias cao — nên dùng swap-and-average."
    #                   if position_bias_rate > 0.3 else "Position bias thấp — judge ổn định.")
    # return {
    #     "total_judged": total, "position_bias_rate": round(position_bias_rate, 3),
    #     "position_bias_count": position_bias_count,
    #     "verbosity_bias": round(verbosity_bias, 3),
    #     "verbosity_details": {"a_wins_a_longer": a_wins_a_longer,
    #                           "b_wins_b_longer": b_wins_b_longer,
    #                           "total_decisive": decisive},
    #     "interpretation": interpretation,
    # }
    total = len(judge_results)
    details = {"a_wins_a_longer": 0, "b_wins_b_longer": 0, "total_decisive": 0}
    if total == 0:
        return {"total_judged": 0, "position_bias_rate": 0.0, "verbosity_bias": 0.0,
                "position_bias_count": 0, "verbosity_details": details,
                "interpretation": "No pairwise judgments were available for bias analysis."}

    position_bias_count = sum(1 for result in judge_results if not result.position_consistent)
    for result in judge_results:
        if result.final_winner == "A":
            details["total_decisive"] += 1
            details["a_wins_a_longer"] += len(result.answer_a) > len(result.answer_b)
        elif result.final_winner == "B":
            details["total_decisive"] += 1
            details["b_wins_b_longer"] += len(result.answer_b) > len(result.answer_a)
    longer_wins = details["a_wins_a_longer"] + details["b_wins_b_longer"]
    verbosity = longer_wins / details["total_decisive"] if details["total_decisive"] else 0.0
    position_rate = position_bias_count / total
    interpretation = (
        "Swap-and-average found notable position inconsistency; inspect those cases manually."
        if position_rate > 0.3
        else "Position inconsistency is low in this small sample; still keep swap-and-average."
    )
    return {
        "total_judged": total,
        "position_bias_rate": round(position_rate, 3),
        "position_bias_count": position_bias_count,
        "verbosity_bias": round(verbosity, 3),
        "verbosity_details": details,
        "interpretation": interpretation,
    }


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from scripts.run_experiments import main
    raise SystemExit(main(["--phase", "b", *sys.argv[1:]]))
