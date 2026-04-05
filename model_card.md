# DocuBot Model Card

This model card is a short reflection on your DocuBot system. Fill it out after you have implemented retrieval and experimented with all three modes:

1. Naive LLM over full docs  
2. Retrieval only  
3. RAG (retrieval plus LLM)

Use clear, honest descriptions. It is fine if your system is imperfect.

---

## 1. System Overview

**What is DocuBot trying to do?**  
Describe the overall goal in 2 to 3 sentences.

> DocuBot answers developer questions using local project docs in three modes: naive LLM, retrieval only, and RAG. The goal is to ground answers in evidence from files like AUTH.md, API_REFERENCE.md, DATABASE.md, and SETUP.md. The system should prefer refusal over guessing when evidence is weak.

**What inputs does DocuBot take?**  
For example: user question, docs in folder, environment variables.

> Inputs are: a user question string, markdown/text files in the docs folder, retrieval settings (top_k and score threshold), and environment variables such as GEMINI_API_KEY for LLM modes.

**What outputs does DocuBot produce?**

> Outputs are either retrieved snippets with filenames (retrieval only), generated answers from Gemini (naive mode), grounded generated answers from retrieved snippets (RAG), or an explicit refusal message when evidence is insufficient.

---

## 2. Retrieval Design

**How does your retrieval system work?**  
Describe your choices for indexing and scoring.

- How do you turn documents into an index?
- How do you score relevance for a query?
- How do you choose top snippets?

> Documents are split into paragraph chunks using double-newline boundaries. An inverted index maps lowercase tokens to chunk references instead of full files. Query tokens are normalized with regex tokenization, common stopwords are removed, and each chunk gets a numeric relevance score based on token overlap plus a small co-occurrence bonus when at least two meaningful tokens appear in the same chunk. Top chunks are returned after sorting by score, and low-scoring chunks are filtered by a minimum threshold.

**What tradeoffs did you make?**  
For example: speed vs precision, simplicity vs accuracy.

> I prioritized simplicity and transparency over semantic accuracy. Regex token overlap is fast and easy to debug, but it can still over-rank generic chunks and miss intent-level meaning. Threshold guardrails improve safety but can increase false refusals in RAG.

---

## 3. Use of the LLM (Gemini)

**When does DocuBot call the LLM and when does it not?**  
Briefly describe how each mode behaves.

- Naive LLM mode:
- Retrieval only mode:
- RAG mode:

> Naive LLM mode: always calls Gemini directly from the user question and does not rely on retrieval evidence.  
> Retrieval only mode: never calls Gemini; it returns ranked snippets and filenames only.  
> RAG mode: calls retrieval first, then passes only retrieved snippets to Gemini for answer generation.

**What instructions do you give the LLM to keep it grounded?**  
Summarize the rules from your prompt. For example: only use snippets, say "I do not know" when needed, cite files.

> The RAG prompt tells Gemini to use only provided snippets, not invent missing endpoints/configs, and return exactly "I do not know based on the docs I have." when evidence is insufficient. It also asks the model to mention which files were used.

---

## 4. Experiments and Comparisons

Run the **same set of queries** in all three modes. Fill in the table with short notes.

You can reuse or adapt the queries from `dataset.py`.

| Query | Naive LLM: helpful or harmful? | Retrieval only: helpful or harmful? | RAG: helpful or harmful? | Notes |
|------|---------------------------------|--------------------------------------|---------------------------|-------|
| Example: Where is the auth token generated? | Harmful: confident generic auth advice, not grounded in project docs | Mixed: returns one AUTH snippet but may miss the best token-generation paragraph | Harmful (for usefulness): refuses with "I do not know" because retrieved evidence is weak/noisy | Shows safety but also false refusal due retrieval quality |
| Example: How do I connect to the database? | Harmful: generic DB connection steps not project-specific | Harmful/mixed: returned a troubleshooting chunk from SETUP, not direct connection instructions | Harmful (for usefulness): refusal due insufficient strong snippets | This is the failure case I observed in testing |
| Example: Which endpoint lists all users? | Mixed: plausible but generic REST answer | Helpful: retrieved API_REFERENCE chunk with "Returns a list of all users" | Harmful (for usefulness): refused despite relevant retrieval snippets | RAG is currently over-conservative given current retrieval quality |
| Example: How does a client refresh an access token? | Harmful: generic OAuth-style answer not tied to docs | Mixed: retrieved token-related API snippets, but not cleanly focused on refresh flow | Harmful (for usefulness): refusal | Needs better ranking/coverage for refresh-specific chunks |

**What patterns did you notice?**  

- When does naive LLM look impressive but untrustworthy?  
- When is retrieval only clearly better?  
- When is RAG clearly better than both?

> Naive mode often sounds polished and confident but is weakly grounded because it can answer from prior knowledge rather than these docs. Retrieval-only mode is usually more faithful to source text, but snippets can be noisy or hard to interpret without synthesis. RAG is safest (it refuses when evidence is weak), but in my current setup it refuses too often because retrieval sometimes fails to provide strong supporting chunks.

---

## 5. Failure Cases and Guardrails

**Describe at least two concrete failure cases you observed.**  
For each one, say:

- What was the question?  
- What did the system do?  
- What should have happened instead?

> Failure case 1: Query "How do I connect to the database?" in RAG mode.  
> Observed behavior: RAG answered "I do not know based on the docs I have."  
> Desired behavior: Use DATABASE.md and/or SETUP.md connection configuration snippets and provide a short grounded answer.

> Failure case 2: Query "Where is the auth token generated?" in retrieval-only mode.  
> Observed behavior: One relevant AUTH snippet returned, but top chunk ordering also surfaced less helpful API error/failure chunks in other tests.  
> Desired behavior: Prioritize the AUTH token-generation paragraph first and suppress unrelated token mentions.

**When should DocuBot say “I do not know based on the docs I have”?**  
Give at least two specific situations.

> It should refuse when no chunk passes the minimum evidence threshold, and when retrieved chunks only match generic terms without directly answering the question intent. It should also refuse when snippets conflict or are too incomplete to support a confident answer.

**What guardrails did you implement?**  
Examples: refusal rules, thresholds, limits on snippets, safe defaults.

> Implemented guardrails: chunk-level retrieval (paragraph chunks), stopword filtering for query tokens, a minimum score threshold, co-occurrence bonus for stronger local evidence, top-k limiting, and explicit refusal fallback when retrieval returns no meaningful snippets.

---

## 6. Limitations and Future Improvements

**Current limitations**  
List at least three limitations of your DocuBot system.

1. Lexical token overlap cannot capture semantic intent well.
2. Threshold-based guardrail can cause false refusals in RAG.
3. Chunk ranking can still surface generic paragraphs when key terms are common.

**Future improvements**  
List two or three changes that would most improve reliability or usefulness.

1. Add intent-aware weighting (e.g., boost heading matches and phrase proximity).
2. Use adaptive thresholds (lower for short/high-signal queries, higher for vague queries).
3. Add lightweight re-ranking before RAG prompt construction.

---

## 7. Responsible Use

**Where could this system cause real world harm if used carelessly?**  
Think about wrong answers, missing information, or over trusting the LLM.

> Harm can occur if users trust fluent but ungrounded LLM answers for security, auth, or deployment decisions. Missing or weak retrieval evidence can lead to false confidence, especially in naive mode. Over-reliance without checking source snippets could propagate incorrect implementation choices.

**What instructions would you give real developers who want to use DocuBot safely?**  
Write 2 to 4 short bullet points.

- Always inspect retrieved snippets and filenames before trusting an answer.
- Treat naive-mode output as a draft, not ground truth.
- Prefer refusal over guessing when evidence is weak.
- For critical decisions, verify directly in source docs/code.

---
