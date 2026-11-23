"""Shared settings for the Whisper fine-tuning project (machine learning final)."""
import random
from pathlib import Path

import numpy as np

SEED = 42
ROOT = Path(__file__).resolve().parent
DATA, RESULTS, MODELS = ROOT / "data", ROOT / "results", ROOT / "models"

HF_REPO = "google/fleurs"                 # FLEURS (Google), CC BY 4.0, read speech of native speakers
LANG = "ru_ru"                            # Russian: the language of the lessons we care about
WHISPER = "openai/whisper-base"           # 74 M parameters: small enough to fine-tune on a laptop
LANG_NAME, TASK = "russian", "transcribe"
N_TRAIN, N_VAL, N_TEST = 1500, 300, 500   # subsets, chosen at random with a fixed seed, to keep the experiment feasible
MAX_SECONDS = 30.0                        # Whisper works on 30-second windows


def set_seed(seed: int = SEED) -> None:
    random.seed(seed)
    np.random.seed(seed)
    try:
        import torch
        torch.manual_seed(seed)
    except ImportError:
        pass
