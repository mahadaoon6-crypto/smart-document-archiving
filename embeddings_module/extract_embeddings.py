import torch
from transformers import AutoTokenizer, AutoModel

tokenizer = AutoTokenizer.from_pretrained("CAMeL-Lab/bert-base-arabic-camelbert-msa")
model = AutoModel.from_pretrained("CAMeL-Lab/bert-base-arabic-camelbert-msa")

def extract_embeddings(text):
    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        max_length=512
    )

    with torch.no_grad():
        outputs = model(**inputs)

    # نأخذ CLS كتمثيل للنص
    emb = outputs.last_hidden_state[:, 0, :].squeeze().numpy()

    return emb.tolist()