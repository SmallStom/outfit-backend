"""Compatibility Model 训练脚本。

双塔 Siamese 网络：每件单品 → MLP encoder → 128维特征向量
兼容性评分：两向量拼接 → MLP → sigmoid(0-1)

用法:
    python -m scripts.compatibility.train_model --epochs 50 --batch-size 32 --lr 0.001
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("train_model")

try:
    import torch
    import torch.nn as nn
    from torch.utils.data import Dataset, DataLoader
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    logger.error("PyTorch 未安装，请运行: pip install torch")
    sys.exit(1)


# ===================== Model ===================== #

class ItemEncoder(nn.Module):
    """单品特征编码器：MLP → 128维特征向量。"""

    def __init__(self, input_dim: int, hidden_dim: int = 256, output_dim: int = 128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim // 2, output_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class CompatibilityModel(nn.Module):
    """双塔兼容性模型：两个编码器 + 兼容性评分头。"""

    def __init__(self, input_dim: int, hidden_dim: int = 256, embed_dim: int = 128):
        super().__init__()
        self.top_encoder = ItemEncoder(input_dim, hidden_dim, embed_dim)
        self.bottom_encoder = ItemEncoder(input_dim, hidden_dim, embed_dim)
        # 兼容性评分头：拼接两向量 + 差值 + 乘积
        self.scorer = nn.Sequential(
            nn.Linear(embed_dim * 3, hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim // 2, 1),
            nn.Sigmoid(),
        )

    def forward(self, top: torch.Tensor, bottom: torch.Tensor) -> torch.Tensor:
        top_emb = self.top_encoder(top)
        bottom_emb = self.bottom_encoder(bottom)
        # 拼接: [top_emb, bottom_emb, top_emb * bottom_emb]
        combined = torch.cat([top_emb, bottom_emb, top_emb * bottom_emb], dim=1)
        return self.scorer(combined).squeeze(-1)


# ===================== Dataset ===================== #

class CompatibilityDataset(Dataset):
    def __init__(self, jsonl_path: str):
        self.samples = []
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                self.samples.append(data)
        logger.info("loaded %d samples from %s", len(self.samples), jsonl_path)

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor, float]:
        s = self.samples[idx]
        top = torch.tensor(s["top_features"], dtype=torch.float32)
        bottom = torch.tensor(s["bottom_features"], dtype=torch.float32)
        label = float(s["label"])
        return top, bottom, label


# ===================== Train ===================== #

def train(
    data_path: str,
    model_path: str,
    epochs: int = 50,
    batch_size: int = 32,
    lr: float = 0.001,
) -> None:
    dataset = CompatibilityDataset(data_path)
    if len(dataset) < 4:
        logger.error("训练数据不足（最少需要4条），当前: %d", len(dataset))
        return

    # 80/20 训练/验证分割
    train_size = int(0.8 * len(dataset))
    val_size = len(dataset) - train_size
    train_dataset, val_dataset = torch.utils.data.random_split(dataset, [train_size, val_size])

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)

    # 确定输入维度
    sample = dataset[0]
    input_dim = len(sample[0])

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = CompatibilityModel(input_dim).to(device)
    criterion = nn.BCELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)

    logger.info("training on %s, input_dim=%d, train=%d, val=%d",
                device, input_dim, train_size, val_size)

    best_val_loss = float("inf")
    for epoch in range(1, epochs + 1):
        # Train
        model.train()
        train_loss = 0.0
        train_correct = 0
        train_total = 0
        for top, bottom, labels in train_loader:
            top, bottom, labels = top.to(device), bottom.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(top, bottom)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * len(labels)
            preds = (outputs > 0.5).float()
            train_correct += (preds == labels).sum().item()
            train_total += len(labels)

        # Validate
        model.eval()
        val_loss = 0.0
        val_correct = 0
        val_total = 0
        with torch.no_grad():
            for top, bottom, labels in val_loader:
                top, bottom, labels = top.to(device), bottom.to(device), labels.to(device)
                outputs = model(top, bottom)
                loss = criterion(outputs, labels)
                val_loss += loss.item() * len(labels)
                preds = (outputs > 0.5).float()
                val_correct += (preds == labels).sum().item()
                val_total += len(labels)

        train_loss /= train_total
        val_loss /= val_total
        train_acc = train_correct / train_total
        val_acc = val_correct / val_total

        if epoch % 10 == 0 or epoch == 1:
            logger.info(
                "epoch %3d/%d | train_loss=%.4f train_acc=%.3f | val_loss=%.4f val_acc=%.3f",
                epoch, epochs, train_loss, train_acc, val_loss, val_acc,
            )

        # 保存最佳模型
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save(model.state_dict(), model_path)

    logger.info("training complete, best val_loss=%.4f, model saved to %s", best_val_loss, model_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="训练 Compatibility Model")
    parser.add_argument("--data", type=str, default="data/train.jsonl", help="训练数据路径")
    parser.add_argument("--output", type=str, default="scripts/compatibility/model_weights.pth", help="模型输出路径")
    parser.add_argument("--epochs", type=int, default=50, help="训练轮数")
    parser.add_argument("--batch-size", type=int, default=32, help="批大小")
    parser.add_argument("--lr", type=float, default=0.001, help="学习率")
    args = parser.parse_args()

    data_path = Path(args.data)
    if not data_path.exists():
        logger.error("训练数据不存在: %s，请先运行 prepare_data.py", data_path)
        sys.exit(1)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    train(str(data_path), str(output_path), args.epochs, args.batch_size, args.lr)


if __name__ == "__main__":
    main()
