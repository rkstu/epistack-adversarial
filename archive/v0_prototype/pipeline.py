"""Full Epistack pipeline — orchestrates Ingestion → Structure → Assessment.

This is the main entry point for running the full epistemic verification
pipeline on a case study. Designed to be callable from CLI or as library.
"""

import asyncio
import json
import os
from datetime import datetime
from typing import Optional

from .models import KnowledgeBase, ClaimStatus
from .ingestion import IngestionConfig, ingest_source, create_source
from .structure import build_claim_graph, build_discourse_map, detect_contradictions, find_unsupported_claims
from .assessment import AssessmentConfig, assess_knowledge_base
from .scoring import classify_confidence


class EpistackPipeline:
    """Main pipeline orchestrator."""

    def __init__(
        self,
        case_name: str,
        llm_call,  # async callable: (prompt, model) -> str
        ingestion_config: Optional[IngestionConfig] = None,
        assessment_config: Optional[AssessmentConfig] = None,
    ):
        self.case_name = case_name
        self.llm_call = llm_call
        self.ingestion_config = ingestion_config or IngestionConfig()
        self.assessment_config = assessment_config or AssessmentConfig()
        self.kb = KnowledgeBase(case_name=case_name)
        self.claim_counter = 0

    async def ingest(self, sources: list) -> "EpistackPipeline":
        """Layer 1: Ingest sources and extract claims.

        sources: list of dicts with keys: url, title, type, content,
                 optional: author, date_published, credibility_signals
        """
        for src_data in sources:
            source = create_source(
                url=src_data["url"],
                title=src_data["title"],
                source_type=src_data["type"],
                content=src_data["content"],
                author=src_data.get("author"),
                date_published=src_data.get("date_published"),
                credibility_signals=src_data.get("credibility_signals", {}),
            )
            self.kb.sources.append(source)

            claims = await ingest_source(
                content=src_data["content"],
                source=source,
                config=self.ingestion_config,
                llm_call=self.llm_call,
                case_name=self.case_name,
                claim_counter_start=self.claim_counter,
            )

            for claim in claims:
                self.kb.add_claim(claim)
                self.claim_counter += 1

        self.kb.metadata["ingestion_complete"] = True
        self.kb.metadata["total_claims"] = len(self.kb.claims)
        self.kb.metadata["total_sources"] = len(self.kb.sources)
        return self

    async def structure(self, questions: Optional[list] = None) -> "EpistackPipeline":
        """Layer 2: Build claim graph and discourse maps.

        questions: list of questions to map discourse around.
                   If None, auto-generates questions from claims.
        """
        claims_list = list(self.kb.claims.values())

        # Build claim relationship graph
        edges = await build_claim_graph(
            claims_list,
            self.llm_call,
            model=self.ingestion_config.model,
        )
        for edge in edges:
            self.kb.add_edge(edge)

        # Build discourse maps
        if questions:
            for question in questions:
                relevant_claims = claims_list  # TODO: filter by relevance
                dm = await build_discourse_map(
                    relevant_claims,
                    question,
                    self.llm_call,
                    model=self.ingestion_config.model,
                )
                self.kb.discourse_maps.append(dm)

        # Detect structural issues
        contradictions = detect_contradictions(self.kb)
        unsupported = find_unsupported_claims(self.kb)

        self.kb.metadata["structure_complete"] = True
        self.kb.metadata["total_edges"] = len(self.kb.edges)
        self.kb.metadata["contradictions_found"] = len(contradictions)
        self.kb.metadata["unsupported_claims"] = len(unsupported)
        return self

    async def assess(self, source_contents: Optional[dict] = None) -> "EpistackPipeline":
        """Layer 3: Run full assessment pipeline on all claims."""
        self.kb = await assess_knowledge_base(
            self.kb,
            self.assessment_config,
            self.llm_call,
            source_contents=source_contents,
        )
        return self

    async def run(
        self,
        sources: list,
        questions: list,
        source_contents: Optional[dict] = None,
    ) -> KnowledgeBase:
        """Run the full pipeline: ingest → structure → assess."""
        await self.ingest(sources)
        await self.structure(questions)
        await self.assess(source_contents)
        return self.kb

    def report_summary(self) -> dict:
        """Generate a summary report of the knowledge base state."""
        claims_by_status = {}
        claims_by_confidence = {}

        for claim in self.kb.claims.values():
            status = claim.status.value
            claims_by_status[status] = claims_by_status.get(status, 0) + 1

            if claim.confidence:
                level = claim.confidence.level.value
                claims_by_confidence[level] = claims_by_confidence.get(level, 0) + 1

        return {
            "case": self.case_name,
            "timestamp": datetime.now().isoformat(),
            "totals": {
                "claims": len(self.kb.claims),
                "sources": len(self.kb.sources),
                "edges": len(self.kb.edges),
                "discourse_maps": len(self.kb.discourse_maps),
            },
            "claims_by_status": claims_by_status,
            "claims_by_confidence": claims_by_confidence,
            "discourse_summary": [
                {
                    "question": dm.question,
                    "positions": len(dm.positions),
                    "live_cruxes": dm.live_cruxes[:3],
                    "empty_chairs": dm.empty_chairs[:3],
                }
                for dm in self.kb.discourse_maps
            ],
            "metadata": self.kb.metadata,
        }

    def export(self, path: str, format: str = "json"):
        """Export knowledge base to file."""
        if format == "json":
            with open(path, "w") as f:
                f.write(self.kb.export_json())
        elif format == "summary":
            with open(path, "w") as f:
                json.dump(self.report_summary(), f, indent=2)
