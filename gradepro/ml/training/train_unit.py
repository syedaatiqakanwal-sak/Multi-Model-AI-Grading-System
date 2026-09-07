"""
GradePro — High-Speed Per-Unit Model Training Pipeline

Enhancements over v1:
  - Task-aware attention pooling (replaces max-pool)
  - Focal Loss for imbalance (gamma=2, gracefully degrades to CrossEntropy on 50/50)
  - Early stopping on val F1-refer (patience=8)
  - ReduceLROnPlateau on val F1-refer (patience=4, factor=0.5)
  - Per-epoch F1/precision/recall logging
  - Stacked (N, T, 384) embedding cache (auto-regenerates on mismatch)
"""

import os
import gc
import json
import logging
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, List

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import optim
from torch.utils.data import DataLoader, TensorDataset, WeightedRandomSampler
from sklearn.model_selection import train_test_split
from sklearn.utils.class_weight import compute_class_weight
from sklearn.metrics import f1_score, recall_score, precision_score, roc_auc_score
import xgboost as xgb

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Focal Loss
# ─────────────────────────────────────────────────────────────────────────────

class FocalLoss(nn.Module):
    """
    Focal Loss for binary/multi-class classification.
    FL(p_t) = -alpha_t * (1 - p_t)^gamma * log(p_t)

    - gamma=2 focuses gradient on hard/minority examples.
    - alpha (class weights) still applied for explicit class balancing.
    - Degrades to weighted CrossEntropyLoss when gamma=0.
    - On perfectly balanced (50/50) data: alpha=[1,1], behavior = standard CE.
    """

    def __init__(self, alpha: Optional[torch.Tensor] = None, gamma: float = 2.0):
        super().__init__()
        self.alpha = alpha   # (num_classes,) class weights tensor
        self.gamma = gamma

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        # logits: (B, C), targets: (B,)
        log_probs = F.log_softmax(logits, dim=1)                     # (B, C)
        probs = torch.exp(log_probs)                                  # (B, C)

        # Gather log_prob and prob for the true class
        log_pt = log_probs.gather(1, targets.unsqueeze(1)).squeeze(1) # (B,)
        pt = probs.gather(1, targets.unsqueeze(1)).squeeze(1)          # (B,)

        focal_factor = (1.0 - pt) ** self.gamma
        loss = -focal_factor * log_pt                                  # (B,)

        if self.alpha is not None:
            alpha_t = self.alpha.to(logits.device)[targets]
            loss = alpha_t * loss

        return loss.mean()


# ─────────────────────────────────────────────────────────────────────────────
# Dataclasses
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TrainingMetrics:
    accuracy: float
    f1_macro: float
    f1_refer: float
    refer_recall: float
    refer_precision: float
    auc: float
    pass_recall: float
    training_samples: int
    refer_samples: int
    pass_samples: int
    class_weights: list
    epochs_trained: int
    best_epoch: int


@dataclass
class TrainedUnit:
    unit_id: str
    unit_code: str
    head_state_dict_path: str
    xgb_model_path: str
    metrics: TrainingMetrics
    embed_dim: int = 384
    num_criteria: int = 3


# ─────────────────────────────────────────────────────────────────────────────
# Early Stopping
# ─────────────────────────────────────────────────────────────────────────────

class EarlyStopping:
    """
    Stops training when val F1-refer doesn't improve for `patience` epochs.
    Saves the best model state dict automatically.
    """

    def __init__(self, patience: int = 8, min_delta: float = 1e-4):
        self.patience = patience
        self.min_delta = min_delta
        self.best_score = -1.0
        self.best_state = None
        self.best_epoch = 0
        self.counter = 0

    def step(self, score: float, model: nn.Module, epoch: int) -> bool:
        """Returns True if training should stop."""
        if score >= self.best_score + self.min_delta:
            self.best_score = score
            self.best_state = {k: v.clone() for k, v in model.state_dict().items()}
            self.best_epoch = epoch
            self.counter = 0
        else:
            self.counter += 1

        return self.counter >= self.patience

    def restore_best(self, model: nn.Module):
        if self.best_state is not None:
            model.load_state_dict(self.best_state)


# ─────────────────────────────────────────────────────────────────────────────
# Evaluation Helper
# ─────────────────────────────────────────────────────────────────────────────

def _evaluate(model: nn.Module, X_val: torch.Tensor, y_val: np.ndarray):
    """Run validation pass and return (preds, probs, metrics_dict)."""
    model.eval()
    with torch.no_grad():
        logits = model.forward_logits(X_val)
        probs = torch.softmax(logits, dim=1)[:, 1].numpy()
        preds = (probs >= 0.5).astype(int)

    metrics = {
        "f1_macro":       float(f1_score(y_val, preds, average="macro",   zero_division=0)),
        "f1_refer":       float(f1_score(y_val, preds, pos_label=0,        zero_division=0)),
        "refer_recall":   float(recall_score(y_val, preds, pos_label=0,    zero_division=0)),
        "refer_precision":float(precision_score(y_val, preds, pos_label=0, zero_division=0)),
        "pass_recall":    float(recall_score(y_val, preds, pos_label=1,    zero_division=0)),
        "accuracy":       float(np.mean(y_val == preds)),
    }
    return preds, probs, metrics


# ─────────────────────────────────────────────────────────────────────────────
# UnitTrainer
# ─────────────────────────────────────────────────────────────────────────────

class UnitTrainer:
    EMBED_DIM = 384
    MAX_EPOCHS = 80           # Early stopping will cut this short on small datasets
    LEARNING_RATE = 1e-3
    BATCH_SIZE = 32
    EARLY_STOP_PATIENCE = 8
    LR_REDUCE_PATIENCE = 4
    FOCAL_GAMMA = 2.0

    def __init__(self, embedder, output_dir: str):
        self.embedder = embedder
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ── Embedding with stacked cache ──────────────────────────────────────

    def _get_stacked_embeddings(
        self, df: pd.DataFrame, task_cols: List[str], unit_code: str
    ) -> np.ndarray:
        """
        Returns (N, T, 384) stacked embeddings — one slice per task per sample.
        Cache is invalidated automatically if the shape no longer matches
        (e.g. new task columns added, or v1 pooled cache detected).
        """
        cache_path = self.output_dir / f"{unit_code}_stacked_embeddings.npy"
        expected_shape = (len(df), len(task_cols), self.EMBED_DIM)

        if cache_path.exists():
            cached = np.load(cache_path)
            if cached.shape == expected_shape:
                print(f"      Loading precomputed stacked embeddings from {cache_path.name}...")
                return cached
            else:
                print(f"      Cache shape mismatch {cached.shape} vs {expected_shape} — regenerating...")

        print(f"      Encoding {len(df)} records × {len(task_cols)} tasks...")
        task_embeddings = []
        for col in task_cols:
            texts = df[col].fillna("").tolist()
            print(f"        Encoding {col}...")
            embs = self.embedder.encode_dataset_tasks(texts, batch_size=64)  # (N, 384)
            task_embeddings.append(embs)

        stacked = np.stack(task_embeddings, axis=1)  # (N, T, 384)
        np.save(cache_path, stacked)
        print(f"      Stacked embeddings cached: {cache_path.name}  shape={stacked.shape}")
        return stacked

    # ── Main train ────────────────────────────────────────────────────────

    def train(self, df: pd.DataFrame, unit_id: str, unit_code: str) -> TrainedUnit:
        task_cols = sorted([c for c in df.columns if c.startswith("task_") and c.endswith("_content")])
        if not task_cols:
            raise ValueError(f"No task_*_content columns found for {unit_code}")

        labels = (df["final_result"].astype(str).str.lower().str.strip() == "pass").astype(int).values
        num_criteria = len(task_cols)

        # ── Stacked Embeddings (N, T, 384) ───────────────────────────────
        stacked = self._get_stacked_embeddings(df, task_cols, unit_code)  # (N, T, 384)

        # ── Class Weights (graceful on 50/50: returns [1.0, 1.0]) ────────
        classes = np.unique(labels)
        if len(classes) > 1:
            class_weights = compute_class_weight("balanced", classes=classes, y=labels)
        else:
            class_weights = np.array([1.0, 1.0])

        class_weights_tensor = torch.tensor(class_weights, dtype=torch.float32)

        # ── Stratified Train/Val Split ────────────────────────────────────
        min_class_count = min(sum(labels == 0), sum(labels == 1))
        can_stratify = min_class_count >= 2

        split_kwargs = dict(test_size=0.20, random_state=42)
        if can_stratify:
            split_kwargs["stratify"] = labels

        X_train, X_val, y_train, y_val = train_test_split(stacked, labels, **split_kwargs)

        # Pool dim kept as (N, T, 384) tensors — attention pooling happens in the loop
        X_train_t = torch.tensor(X_train, dtype=torch.float32)  # (B, T, 384)
        X_val_t   = torch.tensor(X_val,   dtype=torch.float32)  # (V, T, 384)
        y_train_t = torch.tensor(y_train, dtype=torch.long)
        y_val_np  = y_val  # kept as numpy for sklearn metrics

        # ── Weighted Sampler ──────────────────────────────────────────────
        sample_weights = class_weights[y_train]
        sampler = WeightedRandomSampler(
            weights=torch.tensor(sample_weights, dtype=torch.float32),
            num_samples=len(sample_weights),
            replacement=True,
        )
        train_loader = DataLoader(
            TensorDataset(X_train_t, y_train_t),
            batch_size=self.BATCH_SIZE,
            sampler=sampler,
        )

        # ── Model + Loss + Optimizer + Scheduler ──────────────────────────
        from unit_head_train import UnitGradingHeadTrainable
        model = UnitGradingHeadTrainable(embed_dim=self.EMBED_DIM, num_criteria=num_criteria)

        criterion = FocalLoss(alpha=class_weights_tensor, gamma=self.FOCAL_GAMMA)

        optimizer = optim.AdamW(model.parameters(), lr=self.LEARNING_RATE, weight_decay=1e-4)

        scheduler = optim.lr_scheduler.ReduceLROnPlateau(
            optimizer,
            mode="max",        # maximise F1-refer
            factor=0.5,
            patience=self.LR_REDUCE_PATIENCE,
            min_lr=1e-5,
        )

        early_stopper = EarlyStopping(patience=self.EARLY_STOP_PATIENCE)

        print(f"      Training MLP head (max {self.MAX_EPOCHS} epochs, early stop patience={self.EARLY_STOP_PATIENCE})...")
        print(f"      {'Epoch':>5}  {'LR':>8}  {'F1-mac':>7}  {'F1-ref':>7}  {'Ref-Rec':>8}  {'Pas-Rec':>8}")

        for epoch in range(1, self.MAX_EPOCHS + 1):
            # ── Training step ─────────────────────────────────────────────
            model.train()
            for X_batch, y_batch in train_loader:
                optimizer.zero_grad()

                # Attention pool inside train loop (B, T, 384) → (B, 384)
                pooled_batch = model.pool.forward_batch(X_batch)  # (B, 384)
                logits = model.forward_logits(pooled_batch)
                loss = criterion(logits, y_batch)
                loss.backward()
                optimizer.step()

            # ── Validation step ───────────────────────────────────────────
            # Pool val set once per epoch
            with torch.no_grad():
                X_val_pooled = model.pool.forward_batch(X_val_t)   # (V, 384)

            _, val_probs, val_metrics = _evaluate(model, X_val_pooled, y_val_np)

            lr_now = optimizer.param_groups[0]["lr"]
            if epoch % 5 == 0 or epoch == 1:
                print(
                    f"      {epoch:>5}  {lr_now:>8.2e}"
                    f"  {val_metrics['f1_macro']:>7.4f}"
                    f"  {val_metrics['f1_refer']:>7.4f}"
                    f"  {val_metrics['refer_recall']:>8.4f}"
                    f"  {val_metrics['pass_recall']:>8.4f}"
                )

            # LR scheduler step (on val F1-refer)
            scheduler.step(val_metrics["f1_refer"])

            # Early stopping step
            if early_stopper.step(val_metrics["f1_refer"], model, epoch):
                print(f"      Early stopping at epoch {epoch}. Best epoch: {early_stopper.best_epoch}")
                break

        # Restore best weights
        early_stopper.restore_best(model)
        best_epoch = early_stopper.best_epoch

        # ── Final validation with best weights ────────────────────────────
        model.eval()
        with torch.no_grad():
            X_val_pooled = model.pool.forward_batch(X_val_t)
        val_preds, val_probs, final_metrics = _evaluate(model, X_val_pooled, y_val_np)

        # ── XGBoost on pooled (N, 384) for fallback ───────────────────────
        # Pool training set with best model weights
        model.eval()
        with torch.no_grad():
            X_train_pooled_np = model.pool.forward_batch(X_train_t).numpy()  # (N_train, 384)
            X_val_pooled_np   = X_val_pooled.numpy()                          # (N_val, 384)

        xgb_model = xgb.XGBClassifier(
            n_estimators=60,
            max_depth=3,
            learning_rate=0.1,
            eval_metric="logloss",
            random_state=42,
        )
        xgb_model.fit(X_train_pooled_np, y_train, sample_weight=sample_weights)

        # ── Save artifacts ────────────────────────────────────────────────
        head_path = self.output_dir / f"{unit_code}_head.pt"
        torch.save(model.state_dict(), head_path)

        xgb_path = self.output_dir / f"{unit_code}_xgb.json"
        xgb_model.save_model(str(xgb_path))

        # Copy to ml_inference models directory
        inference_models_dir = Path(r"C:\Grading Software\gradepro\services\ml_inference\models")
        inference_models_dir.mkdir(parents=True, exist_ok=True)
        torch.save(model.state_dict(), inference_models_dir / f"{unit_code}_head.pt")

        auc_score = (
            float(roc_auc_score(y_val_np, val_probs))
            if len(np.unique(y_val_np)) > 1
            else 1.0
        )

        metrics = TrainingMetrics(
            accuracy=final_metrics["accuracy"],
            f1_macro=final_metrics["f1_macro"],
            f1_refer=final_metrics["f1_refer"],
            refer_recall=final_metrics["refer_recall"],
            refer_precision=final_metrics["refer_precision"],
            auc=auc_score,
            pass_recall=final_metrics["pass_recall"],
            training_samples=len(labels),
            refer_samples=int(sum(labels == 0)),
            pass_samples=int(sum(labels == 1)),
            class_weights=class_weights.tolist(),
            epochs_trained=epoch,
            best_epoch=best_epoch,
        )

        return TrainedUnit(
            unit_id=unit_id,
            unit_code=unit_code,
            head_state_dict_path=str(head_path),
            xgb_model_path=str(xgb_path),
            metrics=metrics,
            embed_dim=self.EMBED_DIM,
            num_criteria=num_criteria,
        )
