"""Event-sourced epistemic store — JSONL append-only with replay.

Source of truth is events.jsonl. State is derived by replaying events.
Enables: time-travel, trivial debugging, trivial collaboration (merge JSONL files).

Design sources:
- DEG architecture (Internal-context/memory_challange/)
- Graphiti bi-temporal validity (arXiv:2501.13956)
- FPF confidence-gated supersession (arXiv:2601.21116)
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()

EVENT_TYPES = (
    "claim.asserted",
    "edge.asserted",
    "position.stated",
    "challenge.raised",
    "claim.rank_changed",
    "claim.superseded",
    "meta.flag",
)

EDGE_TYPES = (
    "supports",
    "contradicts",
    "depends_on",
    "is_crux_for",
    "refines",
    "supersedes",
    "frames_differently",
    "qualifies",
)


@dataclass
class Event:
    event_id: str
    event_type: str
    tx: int
    timestamp: str
    actor: str
    method: str
    payload: dict[str, Any]
    supersedes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "tx": self.tx,
            "timestamp": self.timestamp,
            "actor": self.actor,
            "method": self.method,
            "supersedes": self.supersedes,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Event:
        return cls(
            event_id=data["event_id"],
            event_type=data["event_type"],
            tx=data["tx"],
            timestamp=data["timestamp"],
            actor=data["actor"],
            method=data["method"],
            supersedes=data.get("supersedes"),
            payload=data["payload"],
        )


class EpistemicStore:
    """Event-sourced store for epistemic claims, edges, and positions.

    All mutations go through append(). State is derived by replay.
    """

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.events_path = self.data_dir / "events.jsonl"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self._tx_counter = 0
        self._event_counter = 0

        # Derived state (rebuilt by replay)
        self.claims: dict[str, dict[str, Any]] = {}
        self.edges: dict[str, dict[str, Any]] = {}
        self.positions: dict[str, dict[str, Any]] = {}
        self.challenges: dict[str, dict[str, Any]] = {}
        self.flags: list[dict[str, Any]] = []
        self._superseded: set[str] = set()

    def append(self, event_type: str, payload: dict[str, Any],
               actor: str = "pipeline", method: str = "llm_extraction",
               supersedes: str | None = None) -> Event:
        """Append an event to the store. Returns the created event."""
        if event_type not in EVENT_TYPES:
            raise ValueError(f"Unknown event_type: {event_type}. Valid: {EVENT_TYPES}")

        self._tx_counter += 1
        self._event_counter += 1

        event = Event(
            event_id=f"evt_{self._event_counter:06d}",
            event_type=event_type,
            tx=self._tx_counter,
            timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            actor=actor,
            method=method,
            supersedes=supersedes,
            payload=payload,
        )

        # Write to JSONL
        with open(self.events_path, "a") as f:
            f.write(json.dumps(event.to_dict()) + "\n")

        # Apply to in-memory state
        self._apply_event(event)

        log.debug("event_appended", event_id=event.event_id, event_type=event_type,
                  tx=event.tx)
        return event

    def replay(self) -> None:
        """Rebuild state from events.jsonl. Idempotent."""
        self._reset_state()

        if not self.events_path.exists():
            return

        with open(self.events_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                event = Event.from_dict(data)
                self._apply_event(event)
                self._tx_counter = max(self._tx_counter, event.tx)
                self._event_counter = max(
                    self._event_counter,
                    int(event.event_id.split("_")[1])
                )

        log.info("store_replayed", claims=len(self.claims), edges=len(self.edges),
                 positions=len(self.positions), tx=self._tx_counter)

    def replay_to(self, target_tx: int) -> None:
        """Replay only up to a specific transaction (time-travel)."""
        self._reset_state()

        if not self.events_path.exists():
            return

        with open(self.events_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                event = Event.from_dict(data)
                if event.tx > target_tx:
                    break
                self._apply_event(event)
                self._tx_counter = max(self._tx_counter, event.tx)
                self._event_counter = max(
                    self._event_counter,
                    int(event.event_id.split("_")[1])
                )

    def snapshot(self) -> dict[str, Any]:
        """Dump current state for fast reload."""
        return {
            "tx": self._tx_counter,
            "event_counter": self._event_counter,
            "claims": self.claims,
            "edges": self.edges,
            "positions": self.positions,
            "challenges": self.challenges,
            "flags": self.flags,
            "superseded": list(self._superseded),
        }

    def load_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Load state from a snapshot."""
        self._tx_counter = snapshot["tx"]
        self._event_counter = snapshot["event_counter"]
        self.claims = snapshot["claims"]
        self.edges = snapshot["edges"]
        self.positions = snapshot["positions"]
        self.challenges = snapshot["challenges"]
        self.flags = snapshot["flags"]
        self._superseded = set(snapshot["superseded"])

    def save_snapshot(self) -> Path:
        """Save snapshot to disk for fast reload."""
        path = self.data_dir / "snapshot.json"
        with open(path, "w") as f:
            json.dump(self.snapshot(), f)
        return path

    def is_valid(self, claim_id: str, at_date: date | None = None) -> bool:
        """Check if a claim is currently valid (bi-temporal)."""
        claim = self.claims.get(claim_id)
        if not claim:
            return False

        at_date = at_date or date.today()

        if claim.get("expired_at"):
            return False
        if claim.get("status") in ("superseded", "refuted"):
            return False

        valid_from = claim.get("valid_from")
        if valid_from and date.fromisoformat(valid_from) > at_date:
            return False

        valid_until = claim.get("valid_until")
        if valid_until and date.fromisoformat(valid_until) < at_date:
            return False

        return True

    def can_supersede(self, new_confidence: float, old_claim_id: str,
                      decay_period_days: int = 365) -> tuple[bool, str]:
        """Check if new evidence can supersede an existing claim.

        Confidence-gated: new must exceed old × (1 - time_decay).
        Source: DEG trust.py, FPF arXiv:2601.21116.
        """
        old = self.claims.get(old_claim_id)
        if not old:
            return True, "old claim not found"

        old_confidence = old.get("confidence", 0.5)
        old_created = old.get("created_at")

        temporal_decay = 0.0
        if old_created:
            try:
                age_days = (date.today() - date.fromisoformat(old_created[:10])).days
                temporal_decay = min(0.3, age_days / decay_period_days)
            except (ValueError, TypeError):
                pass

        effective_old = old_confidence * (1 - temporal_decay)

        if new_confidence >= effective_old:
            return True, f"new={new_confidence:.2f} >= effective_old={effective_old:.2f}"
        return False, f"BLOCKED: new={new_confidence:.2f} < effective_old={effective_old:.2f}"

    @property
    def tx(self) -> int:
        """Current transaction counter."""
        return self._tx_counter

    @property
    def claim_count(self) -> int:
        return len(self.claims)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    def _apply_event(self, event: Event) -> None:
        """Apply a single event to in-memory state."""
        # Handle supersession
        if event.supersedes:
            self._superseded.add(event.supersedes)
            # Mark old claim/edge as superseded
            if event.supersedes in self.claims:
                self.claims[event.supersedes]["status"] = "superseded"
                self.claims[event.supersedes]["expired_at"] = event.timestamp
            if event.supersedes in self.edges:
                self.edges[event.supersedes]["status"] = "superseded"

        if event.event_type == "claim.asserted":
            claim_id = event.payload.get("claim_id", event.event_id)
            self.claims[claim_id] = {
                **event.payload,
                "claim_id": claim_id,
                "event_id": event.event_id,
                "tx": event.tx,
                "created_at": event.timestamp,
                "status": "active",
            }

        elif event.event_type == "edge.asserted":
            edge_id = event.payload.get("edge_id", event.event_id)
            edge_type = event.payload.get("edge_type", "supports")
            if edge_type not in EDGE_TYPES:
                log.warning("unknown_edge_type", edge_type=edge_type, event_id=event.event_id)
            self.edges[edge_id] = {
                **event.payload,
                "edge_id": edge_id,
                "event_id": event.event_id,
                "tx": event.tx,
                "status": "active",
            }

        elif event.event_type == "position.stated":
            pos_id = event.payload.get("position_id", event.event_id)
            self.positions[pos_id] = {
                **event.payload,
                "position_id": pos_id,
                "event_id": event.event_id,
                "tx": event.tx,
            }

        elif event.event_type == "challenge.raised":
            challenge_id = event.payload.get("challenge_id", event.event_id)
            self.challenges[challenge_id] = {
                **event.payload,
                "challenge_id": challenge_id,
                "event_id": event.event_id,
                "tx": event.tx,
            }

        elif event.event_type == "claim.rank_changed":
            claim_id = event.payload.get("claim_id")
            if claim_id and claim_id in self.claims:
                self.claims[claim_id]["rank"] = event.payload.get("new_rank", "normal")
                if "confidence" in event.payload:
                    self.claims[claim_id]["confidence"] = event.payload["confidence"]

        elif event.event_type == "claim.superseded":
            old_id = event.payload.get("old_claim_id")
            if old_id and old_id in self.claims:
                self.claims[old_id]["status"] = "superseded"
                self.claims[old_id]["expired_at"] = event.timestamp
                self._superseded.add(old_id)

        elif event.event_type == "meta.flag":
            self.flags.append({
                **event.payload,
                "event_id": event.event_id,
                "tx": event.tx,
            })

    def _reset_state(self) -> None:
        """Reset all derived state."""
        self._tx_counter = 0
        self._event_counter = 0
        self.claims = {}
        self.edges = {}
        self.positions = {}
        self.challenges = {}
        self.flags = []
        self._superseded = set()
