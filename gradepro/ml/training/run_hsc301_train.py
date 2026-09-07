"""
Runner script for training HSC301 Sub-Model from real dataset.
"""

import os
import sys
import time
import pandas as pd
from pathlib import Path

# Add paths
sys.path.append(r"C:\Grading Software\gradepro\services\ml_inference")
sys.path.append(r"C:\Grading Software\gradepro\ml\training")

from embedder import get_embedder
from train_unit import UnitTrainer


def main():
    print("=" * 60)
    print("GradePro Sub-Model Trainer — Unit HSC301")
    print("=" * 60)

    dataset_path = r"C:\Grading Software\An Introduction to Health and Social Care - Level 3.xlsx"
    if not os.path.exists(dataset_path):
        print(f"Error: Dataset not found at {dataset_path}")
        return

    start_time = time.time()

    print(f"\n[1/4] Loading dataset: {os.path.basename(dataset_path)}...")
    df = pd.read_excel(dataset_path)
    print(f"      Total records loaded: {len(df)}")
    print(f"      Columns: {len(df.columns)}")

    # Clean and check final_result
    df = df.dropna(subset=["final_result"])
    print(f"      Valid labeled samples: {len(df)}")
    pass_cnt = sum(df["final_result"].str.lower().str.strip() == "pass")
    refer_cnt = len(df) - pass_cnt
    print(f"      Class distribution: Pass = {pass_cnt} ({pass_cnt/len(df)*100:.1f}%), Refer = {refer_cnt} ({refer_cnt/len(df)*100:.1f}%)")

    print("\n[2/4] Initializing shared backbone embedder (bge-small-en-v1.5)...")
    embedder = get_embedder()
    print("      Embedder ready in RAM (130MB).")

    output_dir = r"C:\Grading Software\gradepro\ml\training\output"
    trainer = UnitTrainer(embedder=embedder, output_dir=output_dir)

    print("\n[3/4] Training MLP classification head + XGBoost feature model...")
    print("      Using WeightedRandomSampler and class-weighted CrossEntropyLoss...")
    
    trained_unit = trainer.train(
        df=df,
        unit_id="00000000-0000-0000-0000-000000000301",
        unit_code="HSC301",
    )

    elapsed = time.time() - start_time
    m = trained_unit.metrics

    print("\n" + "=" * 60)
    print("TRAINING COMPLETE — PERFORMANCE REPORT")
    print("=" * 60)
    print(f"Unit Code:           {trained_unit.unit_code}")
    print(f"Training Time:       {elapsed:.1f} seconds")
    print(f"Total Samples:       {m.training_samples}  (Pass={m.pass_samples}, Refer={m.refer_samples})")
    print(f"Best Epoch:          {m.best_epoch}  (of {m.epochs_trained} trained — early stopping)")
    print(f"Refer Recall:        {m.refer_recall * 100:.2f}%  (Target: >80% to catch all failures)")
    print(f"Refer Precision:     {m.refer_precision * 100:.2f}%")
    print(f"Refer F1:            {m.f1_refer * 100:.2f}%")
    print(f"Pass Recall:         {m.pass_recall * 100:.2f}%")
    print(f"Macro F1 Score:      {m.f1_macro * 100:.2f}%")
    print(f"ROC AUC:             {m.auc:.4f}")
    print(f"Class Weights:       {[round(w, 3) for w in m.class_weights]}")
    print("-" * 60)
    print("Artifacts Generated:")
    print(f"  • PyTorch State Dict:  {trained_unit.head_state_dict_path}")
    print(f"  • XGBoost JSON Model:  {trained_unit.xgb_model_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
