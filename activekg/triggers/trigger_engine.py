from __future__ import annotations

from time import time as _now

import numpy as np

from activekg.common.logger import get_enhanced_logger
from activekg.observability.metrics import track_trigger_fired, track_trigger_run


class TriggerEngine:
    """Evaluates per-node triggers against named pattern embeddings.

    Each node has triggers: [{name, threshold}], and we store pattern vectors by name.
    """

    def __init__(self, pattern_store, repository):
        self.pattern_store = pattern_store
        self.repo = repository
        self.logger = get_enhanced_logger(__name__)

    def run(self) -> int:
        """Run triggers for all nodes (full scan)."""
        started = _now()
        count = 0
        for node in self.repo.all_nodes():
            if node.embedding is None:
                continue
            for trig in node.triggers or []:
                name = trig.get("name")
                threshold = float(trig.get("threshold", 0.85))
                ref = self.pattern_store.get(name)
                if ref is None:
                    continue
                sim = self._cos_sim(node.embedding, ref)
                if sim >= threshold:
                    self.repo.append_event(
                        node.id,
                        "trigger_fired",
                        {
                            "trigger": name,
                            "similarity": sim,
                        },
                        tenant_id=node.tenant_id,
                        actor_id="trigger_engine",
                        actor_type="trigger",
                    )
                    if name:
                        try:
                            track_trigger_fired(name, mode="full")
                        except Exception:
                            pass
                    count += 1
        try:
            track_trigger_run(max(0.0, _now() - started), mode="full", fired_count=count)
        except Exception:
            pass
        self.last_run = {"mode": "full", "events": count, "duration_s": max(0.0, _now() - started)}
        self.logger.info("TriggerEngine run", extra_fields={"events": count})
        return count

    def run_for(self, node_ids: list[str]) -> int:
        """Run triggers for specific nodes (efficient for post-refresh).

        Args:
            node_ids: List of node IDs to check triggers for

        Returns:
            Number of triggers fired
        """
        started = _now()
        count = 0
        for node_id in node_ids:
            node = self.repo.get_node(node_id)
            if not node or node.embedding is None:
                continue

            for trig in node.triggers or []:
                name = trig.get("name")
                threshold = float(trig.get("threshold", 0.85))
                ref = self.pattern_store.get(name)
                if ref is None:
                    continue

                sim = self._cos_sim(node.embedding, ref)
                if sim >= threshold:
                    self.repo.append_event(
                        node.id,
                        "trigger_fired",
                        {
                            "trigger": name,
                            "similarity": sim,
                        },
                        tenant_id=node.tenant_id,
                        actor_id="trigger_engine",
                        actor_type="trigger",
                    )
                    if name:
                        try:
                            track_trigger_fired(name, mode="targeted")
                        except Exception:
                            pass
                    count += 1

        try:
            track_trigger_run(max(0.0, _now() - started), mode="targeted", fired_count=count)
        except Exception:
            pass
        self.last_run = {
            "mode": "targeted",
            "events": count,
            "duration_s": max(0.0, _now() - started),
            "node_count": len(node_ids),
        }
        self.logger.info(
            "TriggerEngine run_for", extra_fields={"node_count": len(node_ids), "events": count}
        )
        return count

    @staticmethod
    def _cos_sim(a: np.ndarray, b: np.ndarray) -> float:
        denom = (float((a**2).sum()) ** 0.5) * (float((b**2).sum()) ** 0.5)
        if denom == 0:
            return 0.0
        return float((a @ b) / denom)
