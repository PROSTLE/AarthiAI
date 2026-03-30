
import torch
from transformers import BertTokenizer, BertForSequenceClassification, AutoConfig
import numpy as np

MODEL_NAME = "ProsusAI/finbert"

print(f"Loading {MODEL_NAME}...")
tokenizer = BertTokenizer.from_pretrained(MODEL_NAME)
model = BertForSequenceClassification.from_pretrained(MODEL_NAME)
config = AutoConfig.from_pretrained(MODEL_NAME)

print("\n--- Label Mapping ---")
print(f"id2label: {config.id2label}")
print(f"label2id: {config.label2id}")

# The code in sentiment.py uses: FINBERT_LABELS = ["negative", "neutral", "positive"]
# Let's see if that matches id2label.

headlines = [
    "RBI approves ICICI Group stake hike in eight banks",
    "This Emerging Markets ETF Charges Just 0.07% and Ran Way Past The S&P 500",
    "Asian Equities Traded in the US as American Depositary Receipts Edge Higher in Thursday Trading"
]

print("\n--- Testing Headlines ---")
for text in headlines:
    inputs = tokenizer(text, return_tensors="pt", padding=True, truncation=True)
    with torch.no_grad():
        logits = model(**inputs).logits
    
    probs = torch.nn.functional.softmax(logits, dim=-1).squeeze().tolist()
    
    print(f"\nHeadline: {text}")
    print(f"Raw Probabilities: {probs}")
    
    # Current logic in sentiment.py
    # FINBERT_LABELS = ["negative", "neutral", "positive"]
    # signed_score = probs[2] - probs[0]
    
    # Check what the model actually thinks
    predicted_id = int(np.argmax(probs))
    actual_label = config.id2label[predicted_id]
    print(f"Model Predicted ID: {predicted_id} -> Label: {actual_label}")
