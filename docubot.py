"""
Core DocuBot class responsible for:
- Loading documents from the docs/ folder
- Building a simple retrieval index (Phase 1)
- Retrieving relevant snippets (Phase 1)
- Supporting retrieval only answers
- Supporting RAG answers when paired with Gemini (Phase 2)
"""

import glob
import os
import re

# Minimum score threshold: a chunk must match at least this many query tokens to be returned
MIN_SCORE_THRESHOLD = 2

# Simple stopword set for query-time filtering
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how",
    "i", "in", "is", "it", "of", "on", "or", "that", "the", "this", "to",
    "was", "what", "when", "where", "which", "who", "why", "with"
}

# Tiny query expansion map to improve lexical recall for common variants.
QUERY_SYNONYMS = {
    "connect": ["connection", "database_url"],
    "generated": ["generation", "created"],
    "lists": ["list"],
    "users": ["user"],
    "endpoint": ["endpoints", "route"],
    "api": ["/api"],
}


class DocuBot:
    def __init__(self, docs_folder="docs", llm_client=None):
        """
        docs_folder: directory containing project documentation files
        llm_client: optional Gemini client for LLM based answers
        """
        self.docs_folder = docs_folder
        self.llm_client = llm_client

        # Load documents into memory
        self.documents = self.load_documents()  # List of (filename, text)
        self.document_map = dict(self.documents)

        # Split documents into chunks (paragraphs)
        # self.chunks is a list of (filename, chunk_index, chunk_text) tuples
        self.chunks = self._build_chunks()

        # Build a retrieval index at chunk granularity
        self.index = self.build_index()

    # -----------------------------------------------------------
    # Document Loading
    # -----------------------------------------------------------

    def load_documents(self):
        """
        Loads all .md and .txt files inside docs_folder.
        Returns a list of tuples: (filename, text)
        """
        docs = []
        pattern = os.path.join(self.docs_folder, "*.*")
        for path in glob.glob(pattern):
            if path.endswith(".md") or path.endswith(".txt"):
                with open(path, "r", encoding="utf8") as f:
                    text = f.read()
                filename = os.path.basename(path)
                docs.append((filename, text))
        return docs

    # -----------------------------------------------------------
    # Chunking
    # -----------------------------------------------------------

    def split_into_chunks(self, text):
        """
        Split document text into paragraphs (chunks) by double newline.
        Returns a list of non-empty chunk strings.
        """
        paragraphs = text.split("\n\n")
        return [p.strip() for p in paragraphs if p.strip()]

    def _build_chunks(self):
        """
        Convert all documents into a flat list of chunks with metadata.
        Returns list of (filename, chunk_index, chunk_text) tuples.
        """
        chunks = []
        for filename, text in self.documents:
            paragraphs = self.split_into_chunks(text)
            for chunk_idx, chunk_text in enumerate(paragraphs):
                chunks.append((filename, chunk_idx, chunk_text))
        return chunks

    # -----------------------------------------------------------
    # Index Construction
    # -----------------------------------------------------------

    def tokenize(self, text):
        """
        Convert text into lowercase word tokens.
        """
        return re.findall(r"\b\w+\b", text.lower())

    def meaningful_query_tokens(self, query):
        """
        Return query tokens with common stopwords removed and lightweight expansion.
        """
        base_tokens = [token for token in self.tokenize(query) if token not in STOPWORDS]

        expanded = []
        seen = set()
        for token in base_tokens:
            if token not in seen:
                expanded.append(token)
                seen.add(token)

            for alt in QUERY_SYNONYMS.get(token, []):
                if alt not in seen:
                    expanded.append(alt)
                    seen.add(alt)

        return expanded

    def build_index(self):
        """
        Build an inverted index mapping tokens to chunks.
        Maps each token to a list of (chunk_list_index, chunk_text, filename) tuples.
        """
        index = {}

        for chunk_list_idx, (filename, _, chunk_text) in enumerate(self.chunks):
            tokens = set(self.tokenize(chunk_text))
            for token in tokens:
                if token not in index:
                    index[token] = []
                index[token].append((chunk_list_idx, chunk_text, filename))

        return index

    # -----------------------------------------------------------
    # Scoring and Retrieval
    # -----------------------------------------------------------

    def min_score_threshold(self, query_tokens):
        """
        Adaptive threshold:
        - 1 for short/high-signal queries (single meaningful token)
        - 2 otherwise
        """
        if len(query_tokens) <= 1:
            return 1
        return MIN_SCORE_THRESHOLD

    def score_document(self, query, text):
        """
        Return a numeric relevance score for how well the chunk matches the query.
        """
        query_tokens = self.meaningful_query_tokens(query)
        if not query_tokens:
            return 0

        text_tokens = set(self.tokenize(text))
        matched_tokens = 0
        for token in query_tokens:
            if token in text_tokens:
                matched_tokens += 1

        # Bonus when multiple query terms co-occur in one chunk.
        bonus = 1 if matched_tokens >= 2 else 0

        # Bonus for matched markdown heading chunks, which often summarize a section.
        heading_bonus = 1 if text.strip().startswith("#") and matched_tokens >= 1 else 0

        return matched_tokens + bonus + heading_bonus

    def retrieve(self, query, top_k=3):
        """
        Chunk-based retrieval with adaptive score threshold.

        1. Find candidate chunks via index lookup
        2. Score each chunk independently
        3. Filter out chunks below threshold (guardrail)
        4. Sort by score descending
        5. Return top_k chunks as (filename, chunk_text) tuples
        """
        query_tokens = self.meaningful_query_tokens(query)
        if not query_tokens:
            return []

        threshold = self.min_score_threshold(query_tokens)

        candidates_seen = set()
        candidates = []
        for token in query_tokens:
            for chunk_list_idx, chunk_text, filename in self.index.get(token, []):
                if chunk_list_idx not in candidates_seen:
                    candidates_seen.add(chunk_list_idx)
                    candidates.append((chunk_list_idx, chunk_text, filename))

        results = []
        for _, chunk_text, filename in candidates:
            score = self.score_document(query, chunk_text)
            if score >= threshold:
                results.append((score, filename, chunk_text))

        results.sort(key=lambda item: (-item[0], item[1]))
        return [(filename, chunk_text) for score, filename, chunk_text in results[:top_k]]

    # -----------------------------------------------------------
    # Answering Modes
    # -----------------------------------------------------------

    def answer_retrieval_only(self, query, top_k=3):
        """
        Phase 1 retrieval only mode.
        Returns raw snippets and filenames with no LLM involved.
        """
        snippets = self.retrieve(query, top_k=top_k)

        if not snippets:
            return "I do not know based on these docs."

        formatted = []
        for filename, text in snippets:
            formatted.append(f"[{filename}]\n{text}\n")

        return "\n---\n".join(formatted)

    def answer_rag(self, query, top_k=3):
        """
        Phase 2 RAG mode.
        Uses retrieval to select snippets, then asks Gemini
        to generate an answer using only those snippets.
        """
        if self.llm_client is None:
            raise RuntimeError(
                "RAG mode requires an LLM client. Provide a GeminiClient instance."
            )

        snippets = self.retrieve(query, top_k=top_k)

        if not snippets:
            return "I do not know based on these docs."

        return self.llm_client.answer_from_snippets(query, snippets)

    # -----------------------------------------------------------
    # Bonus Helper: concatenated docs for naive generation mode
    # -----------------------------------------------------------

    def full_corpus_text(self):
        """
        Returns all documents concatenated into a single string.
        This is used in Phase 0 for naive 'generation only' baselines.
        """
        return "\n\n".join(text for _, text in self.documents)
