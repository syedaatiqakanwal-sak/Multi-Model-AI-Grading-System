# GradePro — 1-Click Google Colab Sub-Model Trainer (Enhanced v2)
# Run in Google Colab with GPU enabled: Runtime -> Change runtime type -> T4 GPU
#
# Enhancements over v1:
#   - Task-aware attention pooling (replaces max-pool)
#   - Focal Loss (gamma=2, graceful on 50/50 balanced data)
#   - Early stopping on val F1-refer (patience=8)
#   - ReduceLROnPlateau on val F1-refer (patience=4)
#   - Per-epoch F1/precision/recall logging

import subprocess
subprocess.run(["pip", "install", "sentence-transformers", "xgboost", "openpyxl", "pandas", "scikit-learn", "torch"], check=True)

import os
import time
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import optim
from torch.utils.data import DataLoader, TensorDataset, WeightedRandomSampler
from sklearn.model_selection import train_test_split
from sklearn.utils.class_weight import compute_class_weight
from sklearn.metrics import f1_score, recall_score, precision_score
from sentence_transformers import SentenceTransformer
import xgboost as xgb
from google.colab import files

print("=" * 60)
print("GradePro Sub-Model Trainer v2 (GPU Accelerated + Attention Pool)")
print("=" * 60)

# ─── 1. Upload Dataset ────────────────────────────────────────────────────────
print("\n[1/5] Please upload your Unit Excel file:")
uploaded = files.upload()
file_name = list(uploaded.keys())[0]
unit_code = input("Enter unit code (e.g. HSC301): ").strip() or "HSC301"

df = pd.read_excel(file_name)
df = df.dropna(subset=["final_result"])
print(f"Loaded {len(df)} labeled rows from {file_name}")

# ─── 2. GPU Embedder ──────────────────────────────────────────────────────────
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"\n[2/5] Loading BAAI/bge-small-en-v1.5 on {device.upper()}...")
embedder = SentenceTransformer("BAAI/bge-small-en-v1.5", device=device)

# ─── 3. Stacked GPU Embeddings (N, T, 384) ────────────────────────────────────
task_cols = sorted([c for c in df.columns if c.startswith("task_") and c.endswith("_content")])
labels = (df["final_result"].astype(str).str.lower().str.strip() == "pass").astype(int).values

print(f"\n[3/5] Fast GPU Embedding across {len(task_cols)} tasks...")
task_embeddings = []
for col in task_cols:
    texts = [str(t)[:1500].strip() if (t is not None and str(t).strip()) else "No content" for t in df[col]]
    embs = embedder.encode(texts, batch_size=128, show_progress_bar=True, normalize_embeddings=True)
    task_embeddings.append(embs)

stacked = np.stack(task_embeddings, axis=1)  # (N, T, 384)

# ─── 4. Model Definition ──────────────────────────────────────────────────────

class TaskAttentionPool(nn.Module):
    """Learned attention pooling across task embeddings — replaces max-pool."""
    def __init__(self, embed_dim=384):
        super().__init__()
        self.attn = nn.Linear(embed_dim, 1, bias=False)

    def forward_batch(self, x):
        # x: (B, T, embed_dim)
        weights = F.softmax(self.attn(x), dim=1)   # (B, T, 1)
        return (weights * x).sum(dim=1)             # (B, embed_dim)

    def forward(self, x):
        # x: (T, embed_dim) — inference path
        weights = F.softmax(self.attn(x), dim=0)   # (T, 1)
        return (weights * x).sum(dim=0)             # (embed_dim,)


class UnitGradingHead(nn.Module):
    def __init__(self, embed_dim=384, num_criteria=3):
        super().__init__()
        self.pool = TaskAttentionPool(embed_dim)
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

    def forward_logits(self, x):
        return self.classifier(x)


class FocalLoss(nn.Module):
    """Focal Loss — gracefully degrades to CE on balanced (50/50) data."""
    def __init__(self, alpha=None, gamma=2.0):
        super().__init__()
        self.alpha = alpha
        self.gamma = gamma

    def forward(self, logits, targets):
        log_probs = F.log_softmax(logits, dim=1)
        probs = torch.exp(log_probs)
        log_pt = log_probs.gather(1, targets.unsqueeze(1)).squeeze(1)
        pt = probs.gather(1, targets.unsqueeze(1)).squeeze(1)
        loss = -((1.0 - pt) ** self.gamma) * log_pt
        if self.alpha is not None:
            loss = self.alpha.to(logits.device)[targets] * loss
        return loss.mean()

# ─── 5. Training ──────────────────────────────────────────────────────────────
print(f"\n[4/5] Setting up training...")

# Class weights (returns [1.0, 1.0] on balanced data — no special casing needed)
classes = np.unique(labels)
class_weights = compute_class_weight("balanced", classes=classes, y=labels) if len(classes) > 1 else np.array([1.0, 1.0])
class_weights_t = torch.tensor(class_weights, dtype=torch.float32)

# Stratified split
min_class = min(sum(labels == 0), sum(labels == 1))
split_kwargs = dict(test_size=0.20, random_state=42)
if min_class >= 2:
    split_kwargs["stratify"] = labels
X_train, X_val, y_train, y_val = train_test_split(stacked, labels, **split_kwargs)

X_train_t = torch.tensor(X_train, dtype=torch.float32)
X_val_t   = torch.tensor(X_val,   dtype=torch.float32)
y_train_t = torch.tensor(y_train, dtype=torch.long)

# Weighted sampler
sample_weights = class_weights[y_train]
sampler = WeightedRandomSampler(
    weights=torch.tensor(sample_weights, dtype=torch.float32),
    num_samples=len(sample_weights), replacement=True,
)
train_loader = DataLoader(TensorDataset(X_train_t, y_train_t), batch_size=32, sampler=sampler)

# Model
model = UnitGradingHead(num_criteria=len(task_cols)).to(device)
criterion = FocalLoss(alpha=class_weights_t, gamma=2.0)
optimizer = optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="max", factor=0.5, patience=4, min_lr=1e-5)

# Early stopping state
best_f1_refer = -1.0
best_state = None
best_epoch = 0
patience = 8
no_improve = 0
MAX_EPOCHS = 80

print(f"\n[5/5] Training (max {MAX_EPOCHS} epochs, early stop patience=8)...")
print(f"{'Epoch':>5}  {'F1-mac':>7}  {'F1-ref':>7}  {'Ref-Rec':>8}")

for epoch in range(1, MAX_EPOCHS + 1):
    model.train()
    for X_batch, y_batch in train_loader:
        X_batch, y_batch = X_batch.to(device), y_batch.to(device)
        optimizer.zero_grad()
        pooled = model.pool.forward_batch(X_batch)
        loss = criterion(model.forward_logits(pooled), y_batch)
        loss.backward()
        optimizer.step()

    # Validation
    model.eval()
    with torch.no_grad():
        X_val_pooled = model.pool.forward_batch(X_val_t.to(device)).cpu()
        val_logits = model.forward_logits(X_val_pooled)
        val_probs = torch.softmax(val_logits, dim=1)[:, 1].numpy()
        val_preds = (val_probs >= 0.5).astype(int)

    f1_mac  = float(f1_score(y_val, val_preds, average="macro",   zero_division=0))
    f1_ref  = float(f1_score(y_val, val_preds, pos_label=0,        zero_division=0))
    rec_ref = float(recall_score(y_val, val_preds, pos_label=0,    zero_division=0))

    if epoch % 5 == 0 or epoch == 1:
        print(f"{epoch:>5}  {f1_mac:>7.4f}  {f1_ref:>7.4f}  {rec_ref:>8.4f}")

    scheduler.step(f1_ref)

    # Early stopping
    if f1_ref >= best_f1_refer + 1e-4:
        best_f1_refer = f1_ref
        best_state = {k: v.clone().cpu() for k, v in model.state_dict().items()}
        best_epoch = epoch
        no_improve = 0
    else:
        no_improve += 1
        if no_improve >= patience:
            print(f"Early stopping at epoch {epoch}. Best epoch: {best_epoch}")
            break

# Restore best
if best_state:
    model.load_state_dict(best_state)

# Save and download
head_filename = f"{unit_code}_head.pt"
torch.save(model.to("cpu").state_dict(), head_filename)
print(f"\nTraining Complete! Best epoch: {best_epoch}  Best F1-refer: {best_f1_refer:.4f}")
print(f"Downloading {head_filename}...")
files.download(head_filename)
