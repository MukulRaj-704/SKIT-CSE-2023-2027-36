import re
from collections import Counter
from itertools import combinations


class QueryExpander:
    def __init__(self, max_queries=8, max_items=30, max_terms=40):
        self.max_queries = max(1, max_queries)
        self.max_items = max(1, max_items)
        self.max_terms = max(1, max_terms)
        self.stop_words = {
            "a", "an", "and", "are", "as", "at", "be", "been",
            "by", "can", "could", "do", "does", "for", "from",
            "has", "have", "how", "i", "if", "in", "into", "is",
            "it", "its", "me", "more", "my", "of", "on", "or",
            "our", "that", "the", "their", "them", "there", "these",
            "they", "this", "those", "to", "was", "we", "were",
            "what", "when", "where", "which", "who", "why", "will",
            "with", "would", "you", "your"
        }

    def expand(self, query, context=None):
        query = self.clean(query)
        if not query:
            return []

        context = context or {}
        tokens = self.tokenize(query)
        items = self.extract_context(context)
        candidates = []

        self.add_candidate(candidates, query, 1.0, "original")

        normalized = self.normalize(query)
        if normalized and normalized != query.lower():
            self.add_candidate(
                candidates, normalized, 0.92, "normalized"
            )

        if tokens:
            self.add_candidate(
                candidates, self.join(tokens), 0.88, "keywords"
            )

        ranked = self.rank_context(items, tokens)
        candidates.extend(self.context_candidates(query, ranked))
        candidates.extend(self.keyword_candidates(tokens, ranked))
        candidates.extend(self.phrase_candidates(tokens))

        return self.select(candidates, query)

    def expand_for_jobs(self, query, profile=None):
        return self.expand(query, profile)

    def expand_for_resume(self, query, profile=None):
        return self.expand(query, profile)

    def expand_for_documents(self, query, documents=None):
        return self.expand(query, self.document_context(documents or []))

    def build_context_query(self, query, context=None):
        query = self.clean(query)
        if not query:
            return ""

        items = self.extract_context(context or {})
        ranked = self.rank_context(items, self.tokenize(query))

        terms = []
        for item in ranked[:self.max_items]:
            terms.extend(item["tokens"])

        return self.join(self.tokenize(query) + self.unique(terms))

    def extract_context(self, context):
        result = []
        self.walk(context, result, [])
        return result[:self.max_items]

    def walk(self, value, result, path):
        if value is None:
            return

        if isinstance(value, dict):
            for key, child in value.items():
                new_path = path + [str(key)]
                if isinstance(child, (dict, list, tuple, set)):
                    self.walk(child, result, new_path)
                else:
                    self.add_context(result, child, new_path)
            return

        if isinstance(value, (list, tuple, set)):
            for index, child in enumerate(value):
                new_path = path + [str(index)]
                if isinstance(child, (dict, list, tuple, set)):
                    self.walk(child, result, new_path)
                else:
                    self.add_context(result, child, new_path)
            return

        self.add_context(result, value, path)

    def add_context(self, result, value, path):
        text = self.clean(value)
        tokens = self.tokenize(text)
        if not tokens:
            return

        result.append({
            "value": text,
            "tokens": tokens,
            "path": path,
            "score": 0.0
        })

    def rank_context(self, items, query_tokens):
        if not items:
            return []

        query_set = set(query_tokens)
        frequency = Counter()

        for item in items:
            frequency.update(item["tokens"])

        ranked = []

        for item in items:
            relevance = self.overlap(item["tokens"], query_set)
            frequency_score = self.frequency(
                item["tokens"], frequency
            )
            length_score = self.length_score(item["tokens"])
            depth_score = self.depth_score(item["path"])

            score = (
                relevance * 0.55
                + frequency_score * 0.20
                + length_score * 0.15
                + depth_score * 0.10
            )

            current = dict(item)
            current["score"] = score
            ranked.append(current)

        return sorted(
            ranked,
            key=lambda item: item["score"],
            reverse=True
        )

    def context_candidates(self, query, items):
        candidates = []
        values = self.unique(item["value"] for item in items)

        for index, value in enumerate(values[:self.max_items]):
            score = max(0.55, 0.82 - min(index, 10) * 0.025)
            self.add_candidate(
                candidates,
                self.clean(f"{query} {value}"),
                score,
                "context"
            )

        for first, second in combinations(values[:8], 2):
            self.add_candidate(
                candidates,
                self.clean(f"{query} {first} {second}"),
                0.65,
                "context_pair"
            )

        return candidates

    def keyword_candidates(self, tokens, items):
        if not tokens or not items:
            return []

        candidates = []
        important = []

        for item in items:
            for token in item["tokens"]:
                if token not in important:
                    important.append(token)

        important = important[:self.max_terms]

        for token in important:
            if token in tokens:
                continue

            self.add_candidate(
                candidates,
                self.join(list(tokens) + [token]),
                0.62,
                "context_keyword"
            )

        for group in combinations(important[:8], 2):
            self.add_candidate(
                candidates,
                self.join(list(tokens) + list(group)),
                0.58,
                "context_pair_keyword"
            )

        return candidates

    def phrase_candidates(self, tokens):
        candidates = []

        for size in (2, 3):
            for index in range(len(tokens) - size + 1):
                phrase = self.join(tokens[index:index + size])
                if phrase:
                    self.add_candidate(
                        candidates, phrase, 0.50, "phrase"
                    )

        return candidates

    def add_candidate(self, candidates, query, score, strategy):
        query = self.clean(query)
        if not query:
            return

        candidates.append({
            "query": query,
            "score": max(0.0, min(1.0, score)),
            "strategy": strategy,
            "tokens": self.tokenize(query)
        })

    def select(self, candidates, original):
        if not candidates:
            return [original]

        original_tokens = set(self.tokenize(original))
        scored = []

        for candidate in candidates:
            tokens = set(candidate["tokens"])
            overlap = self.overlap(tokens, original_tokens)
            diversity = self.diversity(tokens, original_tokens)

            score = (
                candidate["score"] * 0.60
                + overlap * 0.20
                + diversity * 0.20
            )

            current = dict(candidate)
            current["final_score"] = score
            scored.append(current)

        scored.sort(
            key=lambda item: item["final_score"],
            reverse=True
        )

        result = []
        seen = set()

        for item in scored:
            query = item["query"]
            key = query.lower()

            if key in seen:
                continue

            seen.add(key)
            result.append(query)

            if len(result) >= self.max_queries:
                break

        return self.remove_similar(result)

    def remove_similar(self, queries):
        result = []

        for query in queries:
            tokens = set(self.tokenize(query))
            similar = False

            for existing in result:
                other = set(self.tokenize(existing))
                if self.overlap(tokens, other) >= 0.90:
                    similar = True
                    break

            if not similar:
                result.append(query)

        return result[:self.max_queries]

    def document_context(self, documents):
        context = {}

        for index, document in enumerate(documents):
            context[str(index)] = document

        return context

    def tokenize(self, text):
        text = self.clean(text)
        if not text:
            return []

        words = re.findall(
            r"[a-zA-Z0-9+#.-]+",
            text.lower()
        )

        return [
            word for word in words
            if len(word) > 1 and word not in self.stop_words
        ]

    def keywords(self, text):
        return self.unique(self.tokenize(text))

    def normalize(self, text):
        return self.join(self.tokenize(text))

    def normalize_term(self, value):
        value = self.clean(value).lower()
        value = re.sub(r"[^\w+#.-]+", " ", value)
        return self.clean(value)

    def join(self, values):
        result = []

        for value in values:
            value = self.normalize_term(value)
            if value:
                result.append(value)

        return self.clean(" ".join(result))

    def clean(self, value):
        if value is None:
            return ""

        value = str(value)
        value = value.replace("\n", " ")
        value = value.replace("\t", " ")
        return re.sub(r"\s+", " ", value).strip()

    def unique(self, values):
        result = []
        seen = set()

        for value in values:
            value = self.clean(value)
            if not value:
                continue

            key = value.lower()
            if key in seen:
                continue

            seen.add(key)
            result.append(value)

        return result

    def overlap(self, first, second):
        first = set(first)
        second = set(second)

        if not first or not second:
            return 0.0

        return len(first & second) / len(first | second)

    def frequency(self, tokens, counter):
        values = [
            counter[token]
            for token in set(tokens)
            if token in counter
        ]

        if not values:
            return 0.0

        maximum = max(counter.values(), default=1)
        return sum(values) / (len(values) * maximum)

    def length_score(self, tokens):
        size = len(tokens)

        if size == 0:
            return 0.0
        if size <= 3:
            return 0.45
        if size <= 8:
            return 0.80
        if size <= 20:
            return 1.0

        return max(0.40, 1.0 - (size - 20) / 100)

    def depth_score(self, path):
        depth = len(path)

        if depth <= 2:
            return 1.0
        if depth <= 4:
            return 0.85
        if depth <= 7:
            return 0.65

        return 0.45

    def diversity(self, candidate, original):
        if not candidate:
            return 0.0

        new_terms = set(candidate) - set(original)
        return min(1.0, len(new_terms) / len(candidate))

    def similarity(self, first, second):
        return self.overlap(
            self.tokenize(first),
            self.tokenize(second)
        )

    def score_query(self, query, context=None):
        tokens = self.tokenize(query)
        if not tokens:
            return 0.0

        items = self.extract_context(context or {})
        if not items:
            return 0.5

        context_tokens = []
        for item in items:
            context_tokens.extend(item["tokens"])

        return self.overlap(tokens, context_tokens)

    def get_keywords(self, query, limit=None):
        counts = Counter(self.tokenize(query))
        result = [word for word, _ in counts.most_common()]

        if limit is not None:
            return result[:max(0, limit)]

        return result

    def get_context_keywords(self, context, limit=None):
        counts = Counter()

        for item in self.extract_context(context or {}):
            counts.update(item["tokens"])

        result = [word for word, _ in counts.most_common()]

        if limit is not None:
            return result[:max(0, limit)]

        return result

    def generate_combinations(self, values, size=2):
        values = self.unique(values)

        if size <= 0 or len(values) < size:
            return []

        return [
            self.join(group)
            for group in combinations(values, size)
        ]

    def generate_variants(self, query, context=None):
        query = self.clean(query)
        if not query:
            return []

        items = self.extract_context(context or {})
        ranked = self.rank_context(items, self.tokenize(query))
        variants = []

        for item in ranked[:self.max_items]:
            variants.append({
                "query": self.clean(
                    f"{query} {item['value']}"
                ),
                "source": item["path"],
                "score": item["score"]
            })

        return variants

    def merge_contexts(self, *contexts):
        return {
            str(index): context
            for index, context in enumerate(contexts)
            if context is not None
        }

    def filter_context(self, context, minimum_score=0.0):
        items = self.extract_context(context or {})
        ranked = self.rank_context(
            items,
            []
        )

        return [
            item for item in ranked
            if item["score"] >= minimum_score
        ]

    def compact(self, query, max_tokens=None):
        limit = max_tokens or self.max_terms
        return self.join(self.tokenize(query)[:limit])

    def is_valid_query(self, query):
        return bool(self.tokenize(query))

    def finalize(self, queries):
        queries = [
            self.clean(query)
            for query in queries
            if self.is_valid_query(query)
        ]

        return self.remove_similar(
            self.unique(queries)
        )

    def explain(self, query, context=None):
        context = context or {}
        expanded = self.expand(query, context)

        return {
            "original": self.clean(query),
            "keywords": self.keywords(query),
            "expanded": expanded,
            "query_count": len(expanded),
            "context_items": len(
                self.extract_context(context)
            ),
            "context_score": self.score_query(query, context)
        }

    def stats(self, query, context=None):
        context = context or {}
        items = self.extract_context(context)

        return {
            "query_length": len(self.clean(query)),
            "query_tokens": len(self.tokenize(query)),
            "context_items": len(items),
            "context_tokens": sum(
                len(item["tokens"])
                for item in items
            ),
            "expanded_queries": len(
                self.expand(query, context)
            ),
            "max_queries": self.max_queries,
            "max_terms": self.max_terms
        }
