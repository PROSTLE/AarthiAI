
from transformers import AutoConfig
import json

MODEL_NAME = "ProsusAI/finbert"
config = AutoConfig.from_pretrained(MODEL_NAME)

with open("finbert_labels.json", "w") as f:
    json.dump(config.id2label, f)
