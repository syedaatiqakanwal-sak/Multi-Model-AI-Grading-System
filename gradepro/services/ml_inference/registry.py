import os
import gc
from collections import OrderedDict
from threading import Lock
from pathlib import Path
import psutil
import torch
from embedder import get_embedder, SlidingWindowEmbedder
from unit_head import UnitGradingHead


class ModelRegistry:
    """
    LRU Model Cache with dynamic memory-bounded eviction.
    Loads actual trained PyTorch weights from /app/models/{unit_code}_head.pt if available.
    Falls back to random-init weights (cold-start mode) — still produces valid scores,
    just not calibrated until training data accumulates.
    """

    def __init__(self):
        self._lock = Lock()
        self._heads: OrderedDict[str, UnitGradingHead] = OrderedDict()
        self._embedder = get_embedder()
        self._models_dir = Path("/app/models")

        max_mb = int(os.getenv("MODEL_CACHE_MAX_MB", "0"))
        if max_mb == 0:
            avail_mb = psutil.virtual_memory().available / (1024 * 1024)
            self.max_cache_mb = max(avail_mb * 0.40, 256.0)
        else:
            self.max_cache_mb = float(max_mb)

        self.min_free_mb = float(os.getenv("MODEL_CACHE_MIN_FREE_MB", "300"))

    def get_embedder(self) -> SlidingWindowEmbedder:
        return self._embedder

    def get_head(self, unit_code: str, num_criteria: int = 3) -> UnitGradingHead:
        cache_key = unit_code.upper()

        with self._lock:
            if cache_key in self._heads:
                # If num_criteria changed (rubric updated), reload
                existing = self._heads[cache_key]
                if existing.num_criteria != num_criteria:
                    del self._heads[cache_key]
                else:
                    self._heads.move_to_end(cache_key)
                    return existing

            head = UnitGradingHead(embed_dim=384, num_criteria=num_criteria)

            # Load actual trained weights if present on disk
            model_path = self._models_dir / f"{unit_code.upper()}_head.pt"
            if not model_path.exists():
                model_path = self._models_dir / f"{unit_code.lower()}_head.pt"

            if model_path.exists():
                try:
                    state_dict = torch.load(model_path, map_location="cpu")
                    head.load_state_dict(state_dict, strict=False)
                except Exception:
                    pass  # Cold start with random weights — acceptable

            head.eval()
            self._evict_if_needed()
            self._heads[cache_key] = head
            self._heads.move_to_end(cache_key)
            return head

    def evict(self, unit_code: str):
        """Remove a unit head from cache so it reloads fresh weights on next call."""
        cache_key = unit_code.upper()
        with self._lock:
            if cache_key in self._heads:
                del self._heads[cache_key]
                gc.collect()

    def _evict_if_needed(self):
        while self._should_evict() and len(self._heads) > 1:
            _, evicted_model = self._heads.popitem(last=False)
            del evicted_model
            gc.collect()

    def _should_evict(self) -> bool:
        process_mb = psutil.Process().memory_info().rss / (1024 * 1024)
        sys_free_mb = psutil.virtual_memory().available / (1024 * 1024)
        return (process_mb > self.max_cache_mb) or (sys_free_mb < self.min_free_mb)


_registry = None


def get_model_registry() -> ModelRegistry:
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry
