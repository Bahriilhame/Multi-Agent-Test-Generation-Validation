# HumanEval - Test generation evaluation

- Run status: `completed after manual test corrections`
- Tasks: 1
- Reference passed: 1/1
- Multi-agent tests after correction: 1/1

| Average measure per task | Baseline | Multi-agent after correction | Delta |
|---|---:|---:|---:|
| Line coverage (%) | 100.0 | 100.0 | 0.0 |
| Heuristic critic (/100) | - | 80.0 | - |

> Protocol: reference tests vs reference + generated unit tests; not official pass@k. The critic is a deterministic heuristic, not an LLM score.

## Per-task results

| Task ID | Baseline | Revalidated tests | Baseline coverage | Coverage after | Delta | Generated test functions | Critic |
|---|---|---|---:|---:|---:|---:|---:|
| HumanEval/49 | passed | 12 passed | 100.0 | 100.0 | 0.0 | 11 | 80.0 |

## Interpretation

The initial generated suite timed out because it tested an exponent of 1,000,000,000 against a reference implementation that loops once per exponent. The suite was then manually corrected: the exponent was bounded to 10,000, the zero-modulus check now expects `ZeroDivisionError`, the non-integer check expects `TypeError`, and the negative-modulus check asserts the observed result. Docker revalidation completed in about 2.1 seconds.

This is a post-correction revalidation, not an unmodified Ollama result. Coverage did not increase because the HumanEval reference test already covered 100% of the solution lines and branches. HumanEval here measures added tests for a reference solution; it does not calculate official solution-generation pass@k.
