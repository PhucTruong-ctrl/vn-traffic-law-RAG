# System-prompt research for a Vietnamese traffic-law assistant

**Scope.** This note extracts design principles rather than reproducing any proprietary or purportedly leaked prompt. The public repository provides a useful comparison set, but its contents are not automatically authoritative, current, or first-party. The claims below distinguish repository observations from vendor guidance.

## Sources checked

- [x1xhlol/system-prompts-and-models-of-ai-tools](https://github.com/x1xhlol/system-prompts-and-models-of-ai-tools) (public repository, `main`, accessed 2026-09-09). The repository includes folders such as `Anthropic`, `Google`, and many agent products. Its README describes the collection as public/open-source and includes a prominent “LeaksLab” community link. Treat individual prompt artifacts as comparative evidence, not verified vendor policy. Repository tree: [`main`](https://github.com/x1xhlol/system-prompts-and-models-of-ai-tools/tree/main).
- Anthropic, [Prompt engineering overview](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/overview): establish success criteria and empirical tests before optimizing a prompt; links to prompting best practices and evaluation guidance.
- OpenAI, [Prompt engineering guide](https://platform.openai.com/docs/guides/prompt-engineering): first-party guidance for writing and refining instructions (use the current guide for model-specific behavior).
- OpenAI, [Model Spec](https://model-spec.openai.com/2025-12-18.html): normative behavioral principles and instruction hierarchy; use the version applicable to the deployed model.
- Google, [System instructions](https://ai.google.dev/gemini-api/docs/system-instructions): system-level instructions establish behavior, role, goals, and constraints.
- Google, [Grounding](https://ai.google.dev/gemini-api/docs/grounding): grounding connects answers to retrieved/search evidence and supports source attribution; verify current API behavior for the selected Gemini model.

## What the comparative corpus suggests

The repository's organization offers a useful signal: agent prompts commonly separate role, operating constraints, tools, workflow, and output behavior. Across the Claude-oriented, Google-oriented, and agent-tool materials, recurring patterns include explicit role definition, bounded tool use, staged task handling, concise user-facing summaries, and instructions not to invent unavailable information. These are **observations of a third-party corpus**, not claims that any vendor published or endorses the exact text. Do not copy repository prompt text wholesale; use these patterns as requirements to test.

The corpus is uneven. The GitHub web tree may expose folder names without proving provenance, version, or completeness, and it does not provide a verified OpenAI/Codex/Gemini “canonical system prompt.” Vendor documentation and the deployed model contract therefore take precedence over the corpus.

## Reusable principles for Vietnamese traffic law

### 1. Make the role and jurisdiction explicit

State that the assistant explains Vietnamese traffic law from the indexed legal corpus, in Vietnamese, and is not a court, police authority, or substitute for a licensed lawyer. Require the answer to identify the relevant date/version of the legal text. This applies the first-party system-instruction idea of role, goals, and constraints without importing a vendor persona ([Google system instructions](https://ai.google.dev/gemini-api/docs/system-instructions)).

### 2. Prefer clear, direct, friendly-professional language

Use short Vietnamese sentences, ordinary terms, and respectful “bạn/anh/chị” usage consistent with the product's voice. Explain legal terms once, then use the defined term consistently. Avoid theatrical certainty, scolding, and jokes about penalties. Vendor prompt guidance emphasizes explicit instructions; clarity is safer than a long persona block ([Anthropic overview](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/overview), [OpenAI guide](https://platform.openai.com/docs/guides/prompt-engineering)).

### 3. Use a stable multi-case answer structure

For fact patterns with alternatives, answer each case separately rather than blending them:

1. **Kết luận ngắn** (what is most likely true, with confidence qualifier).
2. **Căn cứ** (document title, article/clause/point, effective date, and retrieved citation).
3. **Phân tích điều kiện** (facts that trigger or defeat the rule).
4. **Mức xử lý/hậu quả** (only when directly supported; distinguish fine, points, license action, vehicle impoundment, civil/criminal exposure).
5. **Ngoại lệ và trường hợp khác**.
6. **Việc nên làm tiếp theo** (facts/documents to check, authority or official channel to contact).

If the user asks several questions, preserve numbering and label each scenario. This local design recommendation comes from the corpus's recurring separation of workflow and output, not from copied prompt wording.

### 4. Treat citations as part of the answer, not decoration

Every material legal proposition should point to retrieved evidence. Prefer stable official sources, such as the legal database or issuing authority, and include the title, provision, and link when available. Never manufacture an article number, URL, quotation, or effective date. Keep citations attached to the proposition they support; do not imply that one citation supports unrelated claims. Grounding documentation ties generated answers to sources and attribution ([Google grounding](https://ai.google.dev/gemini-api/docs/grounding)).

### 5. Disclose evidence limits and uncertainty

Separate **facts supplied by the user**, **facts found in retrieved documents**, and **assumptions**. Say when the corpus lacks the controlling text, when a document may have been amended, or when facts are insufficient to choose between provisions. Use calibrated language (“the retrieved text indicates…”, “this depends on…”, “I cannot verify…”) instead of an unsupported yes/no. Ask only the smallest set of clarifying questions that could change the result: date/time, road/location, vehicle class, conduct, sign/marking, injury/property damage, and whether a ticket/decision already exists.

Anthropic's first-party overview begins with success criteria and empirical evaluation. Apply that guidance by testing uncertain, amended-law, conflicting-source, and missing-citation cases rather than rewarding fluent guesses ([Anthropic overview](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/overview)).

### 6. Make anti-hallucination operational

The system instruction should require the assistant to:

- answer only from retrieved legal evidence plus clearly labeled general reasoning;
- quote only text actually present in the evidence;
- refuse to fill gaps with plausible-sounding law;
- flag conflicts between sources and prefer the newer authoritative instrument only when its status/effective date is verified;
- never infer a penalty table from memory;
- state “chưa đủ căn cứ” when the record is insufficient;
- preserve unsupported alternatives instead of silently dropping them.

This is stronger than saying “be accurate”: it defines observable failure conditions and a safe fallback. It also follows the Model Spec's general principle that higher-priority instructions and truthful capability limits govern behavior ([OpenAI Model Spec](https://model-spec.openai.com/2025-12-18.html)).

### 7. Always provide helpful next steps without overreaching

When evidence is incomplete, give a practical checklist: capture the notice and incident record, verify the vehicle/road/sign details, locate the current consolidated instrument, and contact the competent authority or qualified lawyer for a binding decision. Do not advise evasion, destruction of evidence, bribery, or unsafe conduct. Distinguish informational guidance from legal representation.

### 8. Evaluate behavior, not prompt resemblance

Create a small regression set before changing the system prompt: straightforward rule lookup; two fact patterns with different outcomes; missing date; amended provision; conflicting retrieved sources; no supporting citation; a user request for certainty; and a request involving immediate safety. Score citation entailment, correct separation of cases, uncertainty disclosure, language/tone, and useful next action. This applies Anthropic's recommendation to define success criteria and test empirically ([Anthropic overview](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/overview)).

## Suggested compact contract (original wording)

> You are a Vietnamese traffic-law information assistant. Answer in clear, respectful Vietnamese. Use the retrieved legal evidence as the authority for legal claims. For each scenario, give the short conclusion, cited legal basis, conditions/facts, supported consequences, exceptions, and next steps. Separate scenarios and distinguish user facts, evidence, and assumptions. Cite the exact title and provision when verified. If evidence is missing, outdated, conflicting, or insufficient, say so plainly; do not guess article numbers, penalties, quotations, dates, or links. Ask focused clarifying questions when the missing fact could change the result. This information is not a binding decision or legal representation.

This is an original synthesis, not a reproduction of any repository or vendor prompt.

## Caveats

The public corpus is a snapshot assembled by a third party and may contain redactions, outdated artifacts, or material without provenance. First-party docs describe prompting interfaces and desired behavior, not a guarantee that every model will follow every instruction. Pin the assistant’s behavior to the exact model/API version in deployment, keep legal sources current, and evaluate after prompt or corpus changes.
