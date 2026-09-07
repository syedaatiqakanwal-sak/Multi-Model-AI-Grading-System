"""
UnitGradingHeadTrainable — PyTorch MLP head for unit classification during training.
Enhanced with Task-Aware Attention Pooling (replaces max-pooling).
Matches UnitGradingHead in ml_inference after enhancement.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class TaskAttentionPool(nn.Module):
    """
    Learned attention pooling across variable-length task embeddings.

    Why:
      Max-pooling treats all tasks equally and discards task identity.
      This layer learns which tasks carry more weight for pass/refer decisions
      (e.g. Task 3 = citations may be the most predictive for a given unit).

    Input:  stacked  (N_tasks, embed_dim)
    Output: pooled   (embed_dim,)  — weighted sum, task-count invariant
    """

    def __init__(self, embed_dim: int = 384):
        super().__init__()
        self.attn = nn.Linear(embed_dim, 1, bias=False)

    def forward(self, stacked: torch.Tensor) -> torch.Tensor:
        # stacked: (N_tasks, embed_dim)
        weights = F.softmax(self.attn(stacked), dim=0)   # (N_tasks, 1)
        return (weights * stacked).sum(dim=0)             # (embed_dim,)

    def forward_batch(self, stacked: torch.Tensor) -> torch.Tensor:
        """
        Batched variant used during training.
        stacked: (B, N_tasks, embed_dim)
        returns: (B, embed_dim)
        """
        weights = F.softmax(self.attn(stacked), dim=1)   # (B, N_tasks, 1)
        return (weights * stacked).sum(dim=1)             # (B, embed_dim)


class UnitGradingHeadTrainable(nn.Module):
    """
    MLP classification head for a specific unit.
    Trained on 384-dimensional task embeddings from bge-small.

    Architecture:
      TaskAttentionPool  →  384-dim pooled vector (learned, task-count invariant)
      Classifier         →  384 → 128 → 64 → 2  (refer / pass logits)
      Criterion heads    →  N × (384 → 32 → 1 sigmoid)  (per-criterion scores)
    """

    def __init__(self, embed_dim: int = 384, num_criteria: int = 3):
        super().__init__()
        self.embed_dim = embed_dim
        self.num_criteria = num_criteria

        # Learned task attention pooling
        self.pool = TaskAttentionPool(embed_dim)

        # Binary classifier: logits shape (B, 2) -> [refer, pass]
        self.classifier = nn.Sequential(
            nn.Linear(embed_dim, 128),
            nn.LayerNorm(128),
            nn.GELU(),
            nn.Dropout(0.2),
            nn.Linear(128, 64),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(64, 2),
        )

        # Per-criterion auxiliary sigmoid heads (0.0 -> 1.0 score per criterion)
        self.criterion_heads = nn.ModuleList([
            nn.Sequential(
                nn.Linear(embed_dim, 32),
                nn.GELU(),
                nn.Linear(32, 1),
                nn.Sigmoid(),
            )
            for _ in range(num_criteria)
        ])

    def forward_logits(self, x: torch.Tensor) -> torch.Tensor:
        """
        Training path — x is already pooled embeddings: (B, 384).
        Attention pooling happens upstream (in UnitTrainer) during training
        so we can backprop through it efficiently in batches.
        """
        return self.classifier(x)

    def forward(self, task_embeddings: list[torch.Tensor]) -> dict:
        """
        Inference call.
        task_embeddings: list of N tensors, each shape (384,)
        """
        stacked = torch.stack(task_embeddings, dim=0)       # (N_tasks, 384)
        pooled = self.pool(stacked)                         # (384,) — attention-pooled

        logits = self.classifier(pooled)                    # (2,)
        pass_prob = torch.softmax(logits, dim=0)[1].item()

        crit_scores = [
            head(pooled).squeeze(-1).item()
            for head in self.criterion_heads
        ]

        return {
            "logits": logits,
            "pass_probability": pass_prob,
            "criterion_scores": crit_scores,
        }
