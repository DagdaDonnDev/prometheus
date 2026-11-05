"""
RAG engine with confidence scoring and redundancy checking.
Fully offline. Searches knowledge base and injects relevant,
scored context into prompts.
"""

import os
import json
from typing import List, Dict, Optional, Tuple
from pathlib import Path

from core.confidence import ConfidenceScorer, RedundancyChecker, CRITICAL_DOMAINS


KNOWLEDGE_PATH = "knowledge_base"
VECTOR_DB_PATH = "memory/chroma_db"
FALLBACK_PATH = "memory/chunks_fallback.json"


class KnowledgeBase:
    def __init__(self):
        self.embedder        = None
        self.collection      = None
        self.ready           = False
        self.scorer          = ConfidenceScorer()
        self.redundancy      = RedundancyChecker(self.scorer)
        self._fallback_chunks: List[Dict] = []
        self._personal       = None
        self._last_scores    = {}
        self._last_raw_chunks: List[Dict] = []
        self._last_images:   List[str] = []   # image paths from last search
        self._last_sources:  List[str] = []   # "Book title, p. 12" for each passage used
        # What goes into the prompt: at most this many passages, each trimmed
        # to about this many words around the question (see trim_passage)
        self.prompt_passages = 3
        self.passage_words   = 130
        self._load_fallback()

    def _init_personal_searcher(self):
        """Lazy-init personal doc searcher to avoid circular imports."""
        if self._personal is None:
            try:
                from ui.doc_context import PersonalDocSearcher
                self._personal = PersonalDocSearcher()
                self._personal.initialize()
            except Exception:
                self._personal = None

    def _load_fallback(self):
        """Load pre-chunked JSON fallback for keyword search."""
        if Path(FALLBACK_PATH).exists():
            try:
                self._fallback_chunks = json.loads(
                    Path(FALLBACK_PATH).read_text()
                )
                return
            except Exception:
                pass

        # Load raw text files on the fly
        kb_path = Path(KNOWLEDGE_PATH)
        if not kb_path.exists():
            return

        for domain_dir in kb_path.iterdir():
            if not domain_dir.is_dir():
                continue
            domain = domain_dir.name

            for file_path in domain_dir.rglob("*"):
                if not file_path.is_file():
                    continue
                if file_path.suffix.lower() not in (".txt", ".md"):
                    continue
                if file_path.name == "README.md":
                    continue

                try:
                    text = file_path.read_text(encoding="utf-8", errors="replace")
                    if len(text.strip()) < 100:
                        continue

                    source = file_path.stem.replace(" ", "_").lower()
                    chunks = self._chunk_text(text, source, domain)
                    self._fallback_chunks.extend(chunks)
                except Exception:
                    pass

    def _chunk_text(
        self, text: str, source: str, domain: str,
        chunk_size: int = 400, overlap: int = 50
    ) -> List[Dict]:
        """Split text into overlapping chunks."""
        import re
        text = re.sub(r'\s+', ' ', text).strip()
        words = text.split()
        chunks = []
        step = chunk_size - overlap

        for i in range(0, len(words), step):
            chunk_words = words[i:i + chunk_size]
            if len(chunk_words) < 20:
                continue
            chunks.append({
                "id": f"{domain}_{source}_{i}",
                "content": " ".join(chunk_words),
                "source": source,
                "domain": domain
            })
        return chunks

    def initialize_vector_db(self, status_callback=None):
        """Initialize ChromaDB and sentence-transformers after UI shown."""
        try:
            if status_callback:
                status_callback("Loading embedding model...")

            from core.embedder import get_embedder
            import chromadb

            self.embedder = get_embedder()   # shared, offline once downloaded

            client = chromadb.PersistentClient(path=VECTOR_DB_PATH)
            self.collection = client.get_or_create_collection(
                name="prometheus_knowledge",
                metadata={"hnsw:space": "cosine"}
            )

            count = self.collection.count()
            if status_callback:
                status_callback(f"Knowledge base ready — {count} chunks indexed.")

            self.ready = True

        except ImportError:
            if status_callback:
                status_callback(
                    "Vector search unavailable — using keyword search. "
                    "Run: pip install sentence-transformers chromadb"
                )
            self.ready = False
        except Exception as e:
            if status_callback:
                status_callback(f"Knowledge base: using keyword fallback ({e})")
            self.ready = False

    def search(
        self,
        query: str,
        domains: Optional[List[str]] = None,
        n_results: int = 3,
        routing_plan=None,   # RoutingPlan from IntentRouter
    ) -> Tuple[str, str]:
        """
        Tiered search with source precedence hierarchy:
          Tier 1: Tab-specific domain KB  (searched first, trusted most)
          Tier 2: General survival KBs    (cross-domain, lower priority)
          Tier 3: Wikipedia               (broad, lowest confidence)

        Returns (formatted_context, confidence_note) tuple.
        """
        if routing_plan is not None:
            return self._tiered_search(query, routing_plan)

        # Legacy path — used when no routing plan provided
        primary_domain = domains[0] if domains else "general"
        is_critical = self.redundancy.is_critical(primary_domain, query)
        fetch_n = n_results * 2 if is_critical else n_results

        if self.ready and self.collection and self.collection.count() > 0:
            raw_results = self._vector_search(query, domains, fetch_n)
        else:
            raw_results = self._keyword_search(query, domains, fetch_n)

        self._init_personal_searcher()
        if self._personal:
            personal_results = self._personal.search(query, n=2)
            if personal_results:
                raw_results = personal_results + raw_results

        return self._score_and_format(query, raw_results, is_critical, n_results)

    def _tiered_search(self, query: str, plan) -> Tuple[str, str]:
        """
        Execute tiered search in priority order.
        Tier 1 results take precedence. Lower tiers fill gaps.
        Hard domain isolation — no bleed between tiers unless plan allows.
        """
        all_results = []
        tier_results = {}

        # ── Tier 1: Primary domain sources ────────────────────────────────
        if plan.tier1_domains:
            t1 = self._search_domains(query, plan.tier1_domains, plan.n_tier1)
            tier_results["tier1"] = t1
            all_results.extend(t1)

        # ── Tier 2: General survival cross-domain ─────────────────────────
        # Only search tier 2 if:
        #   - Not strict isolation, OR
        #   - Tier 1 returned insufficient results
        t1_count = len(tier_results.get("tier1", []))
        tier2_needed = (
            not plan.is_strict or
            t1_count < 2  # always try tier 2 if tier 1 is thin
        )

        if tier2_needed and plan.tier2_domains:
            t2 = self._search_domains(query, plan.tier2_domains, plan.n_tier2)
            # Deduplicate vs tier 1
            t2 = [r for r in t2 if r["content"] not in
                  {x["content"] for x in all_results}]
            tier_results["tier2"] = t2
            all_results.extend(t2)

        # ── Tier 3: Wikipedia ──────────────────────────────────────────────
        # Only if not strict AND tier 1+2 are still thin
        t1t2_count = len(all_results)
        tier3_needed = (
            not plan.is_strict and
            plan.n_tier3 > 0 and
            t1t2_count < plan.n_tier1 and
            plan.tier3_domains
        )

        if tier3_needed:
            t3 = self._search_domains(query, plan.tier3_domains, plan.n_tier3)
            t3 = [r for r in t3 if r["content"] not in
                  {x["content"] for x in all_results}]
            tier_results["tier3"] = t3
            all_results.extend(t3)

        # ── Personal docs always included ─────────────────────────────────
        self._init_personal_searcher()
        if self._personal:
            personal = self._personal.search(query, n=2)
            if personal:
                all_results = personal + all_results

        is_critical = self.redundancy.is_critical(
            plan.tier1_domains[0] if plan.tier1_domains else "general",
            query
        )

        # Tag each result with its tier for display
        tier_map = {}
        for tier, results in tier_results.items():
            for r in results:
                tier_map[r["content"][:50]] = tier

        return self._score_and_format(
            query, all_results, is_critical,
            plan.n_tier1 + plan.n_tier2 + plan.n_tier3,
            tier_map=tier_map,
        )

    def _search_domains(
        self, query: str, domains: List[str], n: int
    ) -> List[Dict]:
        """Search a specific list of domains."""
        if not domains:
            return []

        if self.ready and self.collection and self.collection.count() > 0:
            results = self._vector_search(query, domains, n)
        else:
            results = self._keyword_search(query, domains, n)

        return results

    def _score_and_format(
        self,
        query: str,
        raw_results: List[Dict],
        is_critical: bool,
        n_results: int,
        tier_map: Optional[Dict] = None,
    ) -> Tuple[str, str]:
        """Score results, cache metadata, format for prompt."""
        if not raw_results:
            self._last_scores = {
                "top_score": 0,
                "sources_found": 0,
                "conflict": False,
                "has_sources": False,
            }
            self._last_images = []
            self._last_sources = []
            return (
                "",
                "NO SOURCES FOUND: No relevant knowledge retrieved for this query. "
                "You must acknowledge this explicitly and not fill the gap with "
                "training knowledge in strict domains."
            )

        # Score each result
        scored = []
        for r in raw_results:
            conf = self.scorer.score_chunk(r["content"], r["source"])
            tier = "tier2"
            if tier_map:
                key  = r["content"][:50]
                tier = tier_map.get(key, "tier2")
                if tier == "tier1":
                    conf["score"] = min(100, conf["score"] + 15)
                elif tier == "tier3":
                    conf["score"] = max(0, conf["score"] - 10)
            scored.append({**r, "confidence": conf, "_tier": tier})

        # Sort: tier1 boosted scores first
        scored.sort(key=lambda x: x["confidence"]["score"], reverse=True)

        # Redundancy check
        redundancy_met, redundancy_note = self.redundancy.redundancy_met(scored)
        confidence_note = self.scorer.build_confidence_note(scored, is_critical)

        if is_critical and not redundancy_met:
            confidence_note += f" {redundancy_note}"

        # Cache for decision gate
        scores = [r["confidence"]["score"] for r in scored]
        sources = set(r.get("source", "") for r in scored)
        conflict = (
            scored[0]["confidence"]["score"] - scored[-1]["confidence"]["score"] > 30
            if len(scored) > 1 else False
        )
        self._last_scores = {
            "top_score":     max(scores) if scores else 0,
            "sources_found": len(sources),
            "conflict":      conflict,
            "has_sources":   True,
        }
        self._last_raw_chunks = scored
        # The passages actually put in the prompt: their sources and page images
        used = scored[:min(n_results, self.prompt_passages)]
        self._last_images = list(dict.fromkeys(
            r["image_path"] for r in used if r.get("image_path")
        ))
        self._last_sources = list(dict.fromkeys(
            self.scorer._source_label(r.get("source", ""), r.get("domain", ""))
            + (f", p. {r['page_num']}" if r.get("page_num") else "")
            for r in used
        ))

        context = self.scorer.format_for_prompt(
            scored[:min(n_results, self.prompt_passages)],
            query=query, max_words=self.passage_words,
        )
        return context, confidence_note

    def get_last_scores(self) -> dict:
        return self._last_scores

    def get_last_sources(self) -> List[str]:
        """Readable source names (with page) behind the last answer."""
        return self._last_sources

    def get_last_images(self) -> List[str]:
        """Return image paths from the most recent search."""
        return self._last_images

    def _vector_search(
        self,
        query: str,
        domains: Optional[List[str]],
        n: int
    ) -> List[Dict]:
        try:
            query_embedding = self.embedder.encode([query]).tolist()
            where = {"domain": {"$in": domains}} if domains else None
            count = self.collection.count()

            results = self.collection.query(
                query_embeddings=query_embedding,
                n_results=min(n, count),
                where=where,
                include=["documents", "metadatas"]
            )

            if not results or not results["documents"]:
                return self._keyword_search(query, domains, n)

            chunks = []
            for doc, meta in zip(
                results["documents"][0],
                results["metadatas"][0]
            ):
                chunk = {
                    "content": doc,
                    "source": meta.get("source", "unknown"),
                    "domain": meta.get("domain", "general"),
                    "page_num": meta.get("page_num", 0),
                }
                # Resolve image path if available
                img = self._resolve_image(chunk)
                if img:
                    chunk["image_path"] = str(img)
                chunks.append(chunk)
            return chunks

        except Exception:
            return self._keyword_search(query, domains, n)

    def _resolve_image(self, chunk: Dict) -> Optional[Path]:
        """
        Look up the page image for a chunk.
        Returns Path if image exists, None otherwise.
        """
        page_num = chunk.get("page_num", 0)
        if not page_num:
            return None

        domain = chunk.get("domain", "")
        source = chunk.get("source", "")

        # Ingest decides which folders get page images; if one exists, use it
        img_path = (
            Path("knowledge_base") / domain / "_images" /
            f"{source}_p{page_num:03d}.jpg"
        )
        return img_path if img_path.exists() else None

    def _keyword_search(
        self,
        query: str,
        domains: Optional[List[str]],
        n: int
    ) -> List[Dict]:
        """Keyword search fallback."""
        query_words = set(query.lower().split())
        scored: List[Tuple[float, Dict]] = []

        search_chunks = self._fallback_chunks
        if domains:
            search_chunks = [
                c for c in self._fallback_chunks
                if c.get("domain") in domains
            ]

        for chunk in search_chunks:
            content_words = set(chunk["content"].lower().split())
            score = len(query_words & content_words)
            if query.lower() in chunk["content"].lower():
                score += 10
            if score > 0:
                scored.append((score, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for _, chunk in scored[:n]:
            r = {
                "content": chunk["content"],
                "source": chunk.get("source", "unknown"),
                "domain": chunk.get("domain", "general"),
                "page_num": chunk.get("page_num", 0),
            }
            img = self._resolve_image(r)   # page images work without ChromaDB too
            if img:
                r["image_path"] = str(img)
            results.append(r)
        return results
