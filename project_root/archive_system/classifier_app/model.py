import torch
import torch.nn as nn

class FullModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.projection = nn.Linear(128, 64)
        self.classifier = nn.Linear(64, 4)  # عدد الفئات

    def forward(self, x):
        z = torch.relu(self.projection(x))
        out = self.classifier(z)
        return out
