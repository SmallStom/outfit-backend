"""Compatibility Model 推理服务。

加载训练好的 PyTorch 模型，对两件单品的兼容性进行评分。
如果 torch 未安装或模型文件不存在，is_available() 返回 False，推荐引擎将跳过此维度。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.models.item import Item

logger = logging.getLogger(__name__)

# 特征维度常量（与 prepare_data.py / train_model.py 保持一致）
_STYLE_KEYS = [
    "minimalist", "commute", "street", "sweet", "retro", "sporty",
    "luxury", "y2k", "japanese", "korean", "academic", "gorpcore",
]
_OCCASION_KEYS = ["office", "meeting", "date", "travel", "daily", "party"]
_SEASON_KEYS = ["spring", "summer", "autumn", "winter"]

# 特征总维度: 7(视觉) + 12(风格) + 6(场景) + 4(季节) + 768(embedding) = 797
_FEATURE_DIM = 7 + len(_STYLE_KEYS) + len(_OCCASION_KEYS) + len(_SEASON_KEYS) + 768

_MODEL_PATH = Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "compatibility" / "model_weights.pth"

_torch = None
_model = None
_loaded = False


# ===================== Model Architecture（与 train_model.py 保持同步） ===================== #

def _build_model(input_dim: int):
    """构建与 train_model.py 中 CompatibilityModel 相同结构的模型。

    将模型架构内联定义，避免从 scripts/ 导入（scripts/ 不是 Python 包）。
    """
    torch = _load_torch()
    if torch is None:
        return None

    import torch.nn as nn

    class ItemEncoder(nn.Module):
        def __init__(self, in_dim: int, hidden_dim: int = 256, out_dim: int = 128):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(in_dim, hidden_dim),
                nn.ReLU(),
                nn.Dropout(0.2),
                nn.Linear(hidden_dim, hidden_dim // 2),
                nn.ReLU(),
                nn.Dropout(0.2),
                nn.Linear(hidden_dim // 2, out_dim),
            )

        def forward(self, x):
            return self.net(x)

    class CompatibilityModel(nn.Module):
        def __init__(self, input_dim: int, hidden_dim: int = 256, embed_dim: int = 128):
            super().__init__()
            self.top_encoder = ItemEncoder(input_dim, hidden_dim, embed_dim)
            self.bottom_encoder = ItemEncoder(input_dim, hidden_dim, embed_dim)
            self.scorer = nn.Sequential(
                nn.Linear(embed_dim * 3, hidden_dim // 2),
                nn.ReLU(),
                nn.Dropout(0.2),
                nn.Linear(hidden_dim // 2, 1),
                nn.Sigmoid(),
            )

        def forward(self, top, bottom):
            top_emb = self.top_encoder(top)
            bottom_emb = self.bottom_encoder(bottom)
            combined = torch.cat([top_emb, bottom_emb, top_emb * bottom_emb], dim=1)
            return self.scorer(combined).squeeze(-1)

    return CompatibilityModel(input_dim)


def _load_torch():
    """惰性加载 torch。"""
    global _torch
    if _torch is None:
        try:
            import torch
            _torch = torch
        except ImportError:
            logger.info("PyTorch not installed, compatibility model disabled")
    return _torch


def _load_model():
    """惰性加载模型。"""
    global _model, _loaded
    if _loaded:
        return _model
    _loaded = True

    torch = _load_torch()
    if torch is None:
        return None

    if not _MODEL_PATH.exists():
        logger.info("compatibility model not found at %s, disabled", _MODEL_PATH)
        return None

    try:
        model = _build_model(_FEATURE_DIM)
        if model is None:
            return None
        model.load_state_dict(torch.load(str(_MODEL_PATH), map_location="cpu"))
        model.eval()
        _model = model
        logger.info("compatibility model loaded from %s", _MODEL_PATH)
    except Exception as exc:
        logger.warning("failed to load compatibility model: %s", exc)
    return _model


def is_available() -> bool:
    """模型是否可用。"""
    return _load_model() is not None


def _extract_features(item: Item, embedding: list[float] | None) -> list[float]:
    """将 Item 的 V2 属性 + embedding 转为固定长度特征向量。"""
    features: list[float] = []

    # V2 视觉属性 (7维)
    sil_val = 0.0
    if item.silhouette and item.silhouette in ("H", "A", "X", "O", "T"):
        sil_val = float(ord(item.silhouette) - 64) / 5.0
    features.append(sil_val)
    features.append(float(item.visual_weight or 3) / 5.0)
    features.append(float(item.volume or 3) / 5.0)
    features.append(float(item.drape or 3) / 5.0)
    features.append(float(item.structure or 3) / 5.0)
    features.append(float(item.thickness or 3) / 5.0)
    features.append(float(item.suitable_temp_min or 0) / 50.0)

    # style_vector (12维)
    sv = item.style_vector or {}
    for key in _STYLE_KEYS:
        features.append(float(sv.get(key, 0.0)))

    # occasion_scores (6维)
    oc = item.occasion_scores or {}
    for key in _OCCASION_KEYS:
        features.append(float(oc.get(key, 3)) / 5.0)

    # season_scores (4维)
    ss = item.season_scores or {}
    for key in _SEASON_KEYS:
        features.append(float(ss.get(key, 3)) / 5.0)

    # visual embedding (768维)
    if embedding:
        features.extend([float(v) for v in embedding[:768]])
        if len(embedding) < 768:
            features.extend([0.0] * (768 - len(embedding)))
    else:
        features.extend([0.0] * 768)

    return features


def score(
    top: Item,
    bottom: Item,
    top_embedding: list[float] | None = None,
    bottom_embedding: list[float] | None = None,
) -> float:
    """计算两件单品的兼容性分数。

    返回: [0.0, 1.0]，模型不可用时返回 0.5（中性分）。
    """
    model = _load_model()
    torch = _load_torch()
    if model is None or torch is None:
        return 0.5

    try:
        top_features = _extract_features(top, top_embedding)
        bottom_features = _extract_features(bottom, bottom_embedding)

        top_tensor = torch.tensor([top_features], dtype=torch.float32)
        bottom_tensor = torch.tensor([bottom_features], dtype=torch.float32)

        with torch.no_grad():
            output = model(top_tensor, bottom_tensor)
            result = float(output.squeeze().item())

        return max(0.0, min(1.0, result))
    except Exception as exc:
        logger.warning("compatibility model inference failed: %s", exc)
        return 0.5
