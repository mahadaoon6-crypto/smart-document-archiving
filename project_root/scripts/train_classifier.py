import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, confusion_matrix

# ---------------------------------------------------------
# تحميل dataset
# ---------------------------------------------------------
DATASET_PATH = r"C:\Users\acc\archive_project\project_root\data\dataset.csv"
df = pd.read_csv(DATASET_PATH)

# حذف الصفوف التي لا تحتوي document_type
print("عدد الصفوف التي سيتم حذفها:", df["document_type"].isna().sum())
df = df.dropna(subset=["document_type"])
df = pd.read_csv(DATASET_PATH)

print("القيم الموجودة في document_type:", df["document_type"].unique())

df = df.dropna(subset=["document_type"])

# ---------------------------------------------------------
# تحميل نموذج التعلم الذاتي
# ---------------------------------------------------------
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

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

projection_model = ProjectionHead().to(device)
projection_model.load_state_dict(
    torch.load(r"C:\Users\acc\archive_project\project_root\data\self_supervised_projection.pt",
               map_location=device)
)
projection_model.eval()

# ---------------------------------------------------------
# تجهيز البيانات
# ---------------------------------------------------------
emb_cols = [c for c in df.columns if c.startswith("emb_")]
X = df[emb_cols].values.astype("float32")

# تحويل نوع الوثيقة إلى أرقام
label_map = {"lic": 0, "ins": 1, "est": 2, "sup": 3}
y = df["document_type"].map(label_map).values

# ---------------------------------------------------------
# استخراج التمثيل الذاتي لكل وثيقة
# ---------------------------------------------------------
X_tensor = torch.from_numpy(X).to(device)
with torch.no_grad():
    Z = projection_model(X_tensor).cpu().numpy()

# ---------------------------------------------------------
# تقسيم البيانات
# ---------------------------------------------------------
X_train, X_test, y_train, y_test = train_test_split(
    Z, y, test_size=0.2, random_state=42, stratify=y
)

# ---------------------------------------------------------
# بناء طبقة التصنيف
# ---------------------------------------------------------
class Classifier(nn.Module):
    def __init__(self, input_dim=128, num_classes=4):
        super().__init__()
        self.fc = nn.Linear(input_dim, num_classes)

    def forward(self, x):
        return self.fc(x)

classifier = Classifier().to(device)
optimizer = optim.Adam(classifier.parameters(), lr=1e-3)
criterion = nn.CrossEntropyLoss()

# ---------------------------------------------------------
# تدريب المصنف
# ---------------------------------------------------------
X_train_t = torch.from_numpy(X_train).to(device)
y_train_t = torch.from_numpy(y_train).to(device)

for epoch in range(20):
    classifier.train()
    optimizer.zero_grad()

    outputs = classifier(X_train_t)
    loss = criterion(outputs, y_train_t)

    loss.backward()
    optimizer.step()

    print(f"Epoch {epoch+1}, loss = {loss.item():.4f}")

# ---------------------------------------------------------
# تقييم النموذج
# ---------------------------------------------------------
classifier.eval()
X_test_t = torch.from_numpy(X_test).to(device)

with torch.no_grad():
    preds = classifier(X_test_t).argmax(dim=1).cpu().numpy()

acc = accuracy_score(y_test, preds)
cm = confusion_matrix(y_test, preds)

print("\n====================================")
print(f"✔ دقة النموذج: {acc*100:.2f}%")
print("✔ مصفوفة الالتباس:")
print(cm)
print("====================================\n")

# ---------------------------------------------------------
# حفظ النموذج النهائي
# ---------------------------------------------------------
torch.save(classifier.state_dict(),
           r"C:\Users\acc\archive_project\project_root\data\classifier_model.pt")

print("✔ تم حفظ نموذج التصنيف النهائي.")
