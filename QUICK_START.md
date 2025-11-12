# 🚀 Quick Start Guide

## TL;DR - What Changed?

| Component | Old | New |
|-----------|-----|-----|
| OCR | Google Vision API | Tesseract OCR ✨ |
| Translation | Google Translate API | translate library ✨ |
| Frontend Form | Needs Google credentials | Credentials removed ✨ |
| User Experience | Complex | Simple ✨ |

---

## ⚡ 5-Minute Setup

### 1. Install Tesseract (choose one)
```powershell
# Easiest: Chocolatey
choco install tesseract

# Or: Download from https://github.com/UB-Mannheim/tesseract/wiki
```

### 2. Update Backend
```powershell
cd backend
pip install -r requirements.txt
```

### 3. Start Services
```powershell
# Terminal 1: Backend
python -m uvicorn server:app --host 127.0.0.1 --port 8000

# Terminal 2: Frontend
cd frontend
npm start
```

### 4. Open Browser
```
http://localhost:3000
```

---

## 📝 New User Flow

```
1. Enter Job Description
   ↓
2. Upload Resume (PDF, JPG, PNG)
   ↓
3. (Optional) Add GitHub Token
   ↓
4. Click "Process"
   ↓
5. View Results
```

**No Google Cloud credentials needed! 🎉**

---

## 🔑 Key Points

✅ **No Credentials** - Frontend simplified
✅ **No API Costs** - Open-source tools
✅ **No Quota Limits** - Run as many times as you want
✅ **Works Offline** - OCR local processing
✅ **Same Features** - Same output quality

---

## 🐛 Common Issues

| Problem | Solution |
|---------|----------|
| "tesseract not found" | Install from choco or github |
| OCR returns empty text | Check image quality |
| Translation fails | Verify internet connection |
| Backend won't start | Check port 8000 is free |

---

## 📚 Full Docs

- **Setup Details**: See `MIGRATION_NOTES.md`
- **API Reference**: See `backend/server.py` comments
- **Troubleshooting**: See `SETUP_GUIDE.md`

---

## 🎯 What's Running

```
Frontend (React)        Backend (FastAPI)
http://localhost:3000   http://127.0.0.1:8000
├─ Job Description   ──→ ├─ PDF Extraction
├─ Resume Upload      ──→ ├─ OCR (Tesseract)
└─ Results Display    ←─ ├─ Translation
                        ├─ AI Ranking
                        └─ Social Stats
```

---

**Ready?** Run `npm start` in frontend folder! 🚀
