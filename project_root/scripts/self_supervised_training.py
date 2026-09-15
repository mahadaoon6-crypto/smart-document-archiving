import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim

DATASET_PATH = r"C:\Users\acc\archive_project\project_root\data\dataset.csv"

df = pd.read_csv(DATASET_PATH)

emb_cols = [c for c in df.columns if c.startswith("emb_")]
X = df[emb_cols].values.astype("float32")
sources = df["source"].values

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

class ProjectionHead(nn.Module):
    def __init__(self, input_dim=768, hidden_dim=256, output_dim=128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, output_dim)
        )

    def forward(self, x):
        return self.net(x)

model = ProjectionHead().to(device)
optimizer = optim.Adam(model.parameters(), lr=1e-3)

def contrastive_loss(z1, z2, same_source):
    cos = nn.functional.cosine_similarity(z1, z2)
    pos = cos[same_source]
    neg = cos[~same_source]
    loss_pos = (1 - pos).mean() if len(pos) > 0 else 0
    loss_neg = torch.clamp(neg + 0.2, min=0).mean() if len(neg) > 0 else 0
    return loss_pos + loss_neg

X_torch = torch.from_numpy(X).to(device)

for epoch in range(10):
    total_loss = 0.0
    model.train()

    for i in range(0, len(X), 16):
        batch = X_torch[i:i+16]
        if batch.shape[0] < 2:
            continue

        z = model(batch)

        idx1 = torch.randint(0, batch.shape[0], (batch.shape[0],))
        idx2 = torch.randint(0, batch.shape[0], (batch.shape[0],))

        z1 = z[idx1]
        z2 = z[idx2]

        s1 = sources[i:i+16][idx1.cpu().numpy()]
        s2 = sources[i:i+16][idx2.cpu().numpy()]
        same = (s1 == s2)
        same_torch = torch.from_numpy(same).to(device)

        loss = contrastive_loss(z1, z2, same_torch)

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        total_loss += loss.item()

    print(f"Epoch {epoch+1}, loss = {total_loss:.4f}")

torch.save(model.state_dict(),
           r"C:\Users\acc\archive_project\project_root\data\self_supervised_projection.pt")
print("✔ تم تدريب نموذج التعلم الذاتي وحفظه.")
