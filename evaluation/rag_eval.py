import asyncio
import json
from pathlib import Path

from app.rag.agent import answer_question


async def main():
    
    from deepeval.metrics import (
        AnswerRelevancyMetric,
        ContextualPrecisionMetric,
        ContextualRecallMetric,
        ContextualRelevancyMetric,
        FaithfulnessMetric,
    )
    from deepeval.test_case import LLMTestCase
    
    model = "gpt-4o-mini-2024-07-18"
    
    metrics = {
        "contextual_precision": ContextualPrecisionMetric(model=model),
        "contextual_recall": ContextualRecallMetric(model=model),
        "contextual_relevancy": ContextualRelevancyMetric(model=model),
        "answer_relevancy": AnswerRelevancyMetric(model=model),
        "faithfulness": FaithfulnessMetric(model=model),
    }

    question = "Explain the Group Health Insurance benefit offered by Dynamisch."
    result = await answer_question(question=question, top_k=2)
    
    # print(result["chunks"])
    context = [
        f"Page Content: {chunk.text} \n"
        for chunk in result["chunks"]
    ]
    
    test_case = LLMTestCase(
        input=question,
        actual_output=result["answer"],
        expected_output = (
            "The Group Health Insurance benefit is available to permanent full-time "
            "employees from their very first day of joining the company. "
            "It provides medical coverage of up to ₹2,00,000. Employees can also "
            "include their spouse and up to two children under the policy, "
            "with the dependent premium deducted monthly from the employee's salary. "
            "Interns, contractual employees, employees on notice period, "
            "and those covered under the ESIC Act are excluded from this benefit."
        ),
        retrieval_context=context
    )
    
    for name, metric in metrics.items():
        metric.measure(test_case)

        print(f"\n{name}")
        print(f"Score: {metric.score}")
        print(f"Reason: {metric.reason}")

    scores = {
        name: metric.score
        for name, metric in metrics.items()
    }
    
    reasons = {
        name: metric.reason
        for name, metric in metrics.items()
    }
    
    average_score = sum(scores.values()) / len(scores)


    print("\n" + "=" * 50)
    print("RAG EVALUATION")
    print("=" * 50)

    print(f"Average score: {average_score:.4f}")
    print(f"Answer: {result['answer']}")

    report = {
        "question": question,
        "scores": scores,
        "average_score": average_score,
        "reasons": reasons,
        "answer": result["answer"],
    }

    report_path = Path("reports.json")

    with report_path.open("w", encoding="utf-8") as file:
        json.dump(
            report,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print(f"\nReport saved to {report_path}")

    
if __name__ == "__main__":
    asyncio.run(main())
    