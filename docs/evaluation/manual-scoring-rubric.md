# Manual scoring rubric for thesis answers

Each review row records five dimensions. `answer_correctness_manual` is the primary answer score and uses only `0`, `0.5`, or `1`.

## Accuracy

- **1**: States every provision requested by the question and the correct legal consequence (fine amount, point deduction, or obligation).
- **0.5**: Partially correct, or omits a required element.
- **0**: Wrong, unsupported as an answer to the question, or absent.

## Faithfulness

Score from `0` to `1`. Every legal statement must be traceable to one of the returned citation excerpts. Penalize claims that go beyond the cited text.

## Completeness

Score from `0` to `1` based on whether all parts of a multi-part question are answered.

## Citation support

Score from `0` to `1` based on whether the returned citations actually contain the text grounding the answer. Deterministic coordinate checks are included in the judge prompt and must not be ignored.

## Refusal and out-of-corpus cases

For `expected_abstain` cases, correctness is `1` only when the system abstains with a sensible reason; answering is `0`. Faithfulness, completeness, and citation support are `None` for abstentions. Cases marked `coverage_status=out_of_corpus` are listed separately in the summary and must not be mixed into corpus-answerable means.

## Human override

`human_override` is intentionally an empty string in generated reviews. The student may enter a replacement accuracy score or explanatory note during defense review without changing the judge's original fields.
