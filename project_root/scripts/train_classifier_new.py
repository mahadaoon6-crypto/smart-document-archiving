import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim

from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, confusion_matrix
from sklearn.utils import resample
from torch.utils.data import DataLoader, TensorDataset

# ---------------------------------------------------------
# إعداد المسارات
# ---------------------------------------------------------
DATASET_PATH = r"C:\Users\acc\archive_project\project_root\data\dataset.csv"
PROJECTION_MODEL_PATH = r"C:\Users\acc\archive_project\project_root\data\self_supervised_projection.pt"
CLASSIFIER_MODEL_PATH = r"C:\Users\acc\archive_project\project_root\data\classifier_model.pt"

# ---------------------------------------------------------
# تحميل dataset
# ---------------------------------------------------------
df = pd.read_csv(DATASET_PATH)

print("عدد الصفوف التي سيتم حذفها:", df["document_type"].isna().sum())
print("القيم الموجودة في document_type:", df["document_type"].unique())

# حذف الصفوف التي لا تحتوي document_type (احتياطًا)
df = df.dropna(subset=["document_type"])

# ---------------------------------------------------------
# تحميل نموذج التعلم الذاتي (Projection Head)
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
    torch.load(PROJECTION_MODEL_PATH, map_location=device)
)
projection_model.eval()

# ---------------------------------------------------------
# تجهيز البيانات (embeddings + labels)
# ---------------------------------------------------------
emb_cols = [c for c in df.columns if c.startswith("emb_")]
X = df[emb_cols].values.astype("float32")

label_map = {"est": 0, "ins": 1, "lic": 2, "sup": 3}
y = df["document_type"].map(label_map).values

# ---------------------------------------------------------
# استخراج التمثيل الذاتي لكل وثيقة
# ---------------------------------------------------------
X_tensor = torch.from_numpy(X).to(device)
with torch.no_grad():
    Z = projection_model(X_tensor).cpu().numpy()  # شكلها (N, 128)

# ---------------------------------------------------------
# دمج التمثيل الأصلي + التمثيل الذاتي (تحسين قوي)
# ---------------------------------------------------------
Z_combined = np.concatenate([X, Z], axis=1).astype("float32")  # (N, 768+128 = 896)

# ---------------------------------------------------------
# تقسيم البيانات إلى تدريب واختبار
# ---------------------------------------------------------
X_train, X_test, y_train, y_test = train_test_split(
    Z_combined, y, test_size=0.2, random_state=42, stratify=y
)

# ---------------------------------------------------------
# موازنة البيانات (Oversampling) لتحسين الفئات القليلة
# ---------------------------------------------------------
X_train, y_train = resample(
    X_train, y_train,
    replace=True,
    n_samples=len(X_train),
    random_state=42
)

# ---------------------------------------------------------
# تحويل البيانات إلى Tensors
# ---------------------------------------------------------
X_train_t = torch.from_numpy(X_train).to(device)
y_train_t = torch.from_numpy(y_train).to(device)

X_test_t = torch.from_numpy(X_test).to(device)
y_test_t = torch.from_numpy(y_test).to(device)

# ---------------------------------------------------------
# بناء طبقة التصنيف المحسّنة
# ---------------------------------------------------------
class Classifier(nn.Module):
    def __init__(self, input_dim=896, num_classes=4):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(64, num_classes)
        )

    def forward(self, x):
        return self.net(x)

classifier = Classifier().to(device)

optimizer = optim.Adam(classifier.parameters(), lr=5e-4)
criterion = nn.CrossEntropyLoss()

# ---------------------------------------------------------
# إعداد DataLoader للتدريب على دفعات
# ---------------------------------------------------------
train_dataset = TensorDataset(X_train_t, y_train_t)
train_loader = DataLoader(train_dataset, batch_size=32, shuffle=True)

# ---------------------------------------------------------
# تدريب المصنف (عدد Epochs أكبر لتحسين الأداء)
# ---------------------------------------------------------
num_epochs = 60

for epoch in range(num_epochs):
    classifier.train()
    total_loss = 0.0

    for batch_x, batch_y in train_loader:
        optimizer.zero_grad()
        outputs = classifier(batch_x)
        loss = criterion(outputs, batch_y)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()

    print(f"Epoch {epoch+1}, loss = {total_loss:.4f}")

# ---------------------------------------------------------
# تقييم النموذج
# ---------------------------------------------------------
classifier.eval()
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
# حفظ نموذج التصنيف النهائي
# ---------------------------------------------------------
torch.save(classifier.state_dict(), CLASSIFIER_MODEL_PATH)
print("✔ تم حفظ نموذج التصنيف النهائي.")
