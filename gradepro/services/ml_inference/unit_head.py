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


class UnitGradingHead(nn.Module):
    """
    Lightweight classification head per unit.
    Trained on top of bge-small 384-dimensional task embeddings.

    Architecture:
      - TaskAttentionPool across all task embeddings → 384-dim (task-count invariant)
      - Shared classifier → overall pass/refer probability
      - Per-criterion sigmoid heads → individual criterion pass scores
        Each criterion gets its own 384→32→1 head, so they can learn
        different decision boundaries from the same pooled representation.
    """

    def __init__(self, embed_dim: int = 384, num_criteria: int = 3):
        super().__init__()
        self.num_criteria = num_criteria

        # Learned task attention pooling (replaces max-pool)
        self.pool = TaskAttentionPool(embed_dim)

        # Overall pass/refer classifier
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

        # One independent head per criterion — different scores per criterion
        self.criterion_heads = nn.ModuleList([
            nn.Sequential(
                nn.Linear(embed_dim, 32),
                nn.GELU(),
                nn.Linear(32, 1),
                nn.Sigmoid(),
            )
            for _ in range(num_criteria)
        ])

    def forward(self, task_embeddings: list) -> dict:
        stacked = torch.stack(task_embeddings, dim=0)   # (N_tasks, 384)
        pooled = self.pool(stacked)                     # (384,) — attention-pooled

        # Overall document pass probability
        doc_logits = self.classifier(pooled)
        doc_pass_prob = torch.softmax(doc_logits, dim=0)[1].item()

        # Per-criterion scores — each head produces a distinct value
        criterion_scores = [
            head(pooled).squeeze().item()
            for head in self.criterion_heads
        ]

        return {
            "logits": doc_logits,
            "pass_probability": doc_pass_prob,
            "criterion_scores": criterion_scores,
        }
