"""
Eval gate for the RAG pipeline.

This is what makes the CI/CD pipeline an *LLMOps* pipeline rather than a
plain CI pipeline: it doesn't just check that the code runs, it checks that
the answers are still good. Run this after any change to prompts, retrieval
settings, or the underlying model — a regression here should block the merge
the same way a failing unit test would.

Usage:
    python eval/run_eval.py [--threshold 0.75]
"""
import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))
from rag import answer_question  # noqa: E402


def evaluate_case(case: dict) -> dict:
    result = answer_question(case["question"], temperature=0)
    answer_lower = result["answer"].lower()

    if case.get("expect_no_answer"):
        # Groundedness check: for out-of-scope questions, the model should
        # decline rather than hallucinate. We check for refusal language.
        refusal_signals = ["don't have enough information", "cannot find", "not covered", "no information"]
        passed = any(s in answer_lower for s in refusal_signals)
        return {"question": case["question"], "passed": passed, "reason": "groundedness (should decline)"}

    missing = [kw for kw in case["expected_keywords"] if kw.lower() not in answer_lower]
    passed = len(missing) == 0
    return {
        "question": case["question"],
        "passed": passed,
        "reason": f"missing keywords: {missing}" if missing else "all expected keywords present",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=0.75)
    parser.add_argument("--testset", default=str(Path(__file__).parent / "testset.yaml"))
    args = parser.parse_args()

    with open(args.testset) as f:
        cases = yaml.safe_load(f)

    results = [evaluate_case(c) for c in cases]
    pass_count = sum(r["passed"] for r in results)
    pass_rate = pass_count / len(results)

    print(f"\n{'PASS' if pass_rate >= args.threshold else 'FAIL'} — "
          f"{pass_count}/{len(results)} cases passed ({pass_rate:.0%}), "
          f"threshold {args.threshold:.0%}\n")

    for r in results:
        status = "✓" if r["passed"] else "✗"
        print(f"  {status} {r['question']}")
        if not r["passed"]:
            print(f"      → {r['reason']}")

    if pass_rate < args.threshold:
        sys.exit(1)


if __name__ == "__main__":
    main()
