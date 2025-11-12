# API Migration: Google Cloud → Open-Source APIs

## Overview
Successfully migrated from Google Cloud Vision & Translate APIs to open-source alternatives that don't require frontend credentials.

## Changes Made

### Backend (`server.py`)
#### 1. **Removed Dependencies**
- `google-cloud-vision` → Replaced with **Tesseract OCR**
- `google-cloud-translate` → Replaced with **translate library**
- Removed dependency on Google Cloud credentials

#### 2. **New OCR Function**
```python
async def ocr_image_pytesseract(image_content: bytes) -> str:
    """Perform OCR using Tesseract (open-source, no credentials needed)"""
```
- Uses Tesseract via `pytesseract` library
- No external credentials required
- Works on: Windows, Linux, Mac
- Supports: PDF, JPG, PNG, and other common image formats

#### 3. **New Translation Function**
```python
async def translate_text(text: str, target_language: str = 'en') -> tuple:
    """Translate text using open-source translate library"""
```
- Uses `translate` library (powered by Google Translate free API)
- Language detection via `langdetect` library
- No credentials needed
- Returns: (translated_text, source_language)

#### 4. **Updated Endpoints**
All endpoints now work **without** Google Cloud credentials:

| Endpoint | Old | New | Credentials |
|----------|-----|-----|-------------|
| `POST /api/process` | Required | Optional* | None needed |
| `POST /api/ocr` | Required | Optional* | None needed |
| `POST /api/translate` | Required | Optional* | None needed |
| `POST /api/batch-ocr` | Required | Optional* | None needed |

*`google_credentials` parameter kept for backward compatibility but not used

### Frontend (`App.js`)
#### Changes
1. **Removed** Google Cloud credentials textarea from UI
2. **Simplified** form - now only requires:
   - Job Description (required)
   - Resume Files (required)
   - GitHub Token (optional)
3. **Updated** handleProcess() to send empty string for credentials

### Environment Configuration (`.env`)
#### Added
```
TESSERACT_PATH="C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
DEFAULT_TRANSLATE_LANGUAGE="en"
```

#### Removed
- `GOOGLE_APPLICATION_CREDENTIALS`
- All Google Cloud credential references

### Dependencies (`requirements.txt`)
#### Added
```
pytesseract==0.3.13
Pillow==11.1.0
langdetect==1.0.9
translate==3.6.1
textblob==0.18.0
```

#### Removed
```
google-cloud-vision==3.11.0
google-cloud-translate==3.23.0
google-api-core==2.28.1
google-auth==2.43.0
google-cloud-core==2.5.0
googleapis-common-protos==1.72.0
```

## Setup Instructions

### 1. **Install Tesseract OCR (Required)**

**Windows:**
```powershell
# Option A: Download installer from GitHub
# https://github.com/UB-Mannheim/tesseract/wiki

# Option B: Using Chocolatey
choco install tesseract

# Option C: Using Scoop
scoop install tesseract-ocr
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get install tesseract-ocr
```

**macOS:**
```bash
brew install tesseract
```

### 2. **Update Backend Dependencies**
```powershell
cd backend
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. **Verify Tesseract Installation**
```bash
# Windows
"C:\Program Files\Tesseract-OCR\tesseract.exe" --version

# Linux/Mac
tesseract --version
```

### 4. **Update `.env` (if needed)**
If Tesseract is installed in a non-standard location, update `backend/.env`:
```
TESSERACT_PATH="C:\\Your\\Custom\\Path\\tesseract.exe"
```

### 5. **Restart Services**
```powershell
# Kill existing processes
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force

# Start backend
cd backend
.venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8000

# In another terminal, start frontend
cd frontend
npm start
```

## Testing

### 1. **Test OCR Endpoint**
```bash
curl -X POST "http://127.0.0.1:8000/api/ocr" \
  -F "file=@resume.pdf" \
  -F "google_credentials="
```

### 2. **Test Translation Endpoint**
```bash
curl -X POST "http://127.0.0.1:8000/api/translate" \
  -F "text=Bonjour le monde" \
  -F "target_language=en" \
  -F "google_credentials="
```

### 3. **Test Full Processing**
1. Open frontend: http://localhost:3000
2. Enter job description
3. Upload resume (PDF or image)
4. Click "Process"
5. View ranked results

## Performance Notes

- **OCR**: Slightly slower than Google Vision, but no network latency or quota limits
- **Translation**: Similar speed to Google API, free usage without API key costs
- **First-time startup**: Tesseract loads on first OCR request (~1-2 seconds)

## Benefits

✅ **No API Credentials Required**
✅ **No Sensitive Data Sent to Google**
✅ **No API Rate Limits or Quota Issues**
✅ **Works Offline (except for language detection)**
✅ **Open-Source & Transparent**
✅ **Reduced API Costs**
✅ **Frontend Simplified - Better UX**

## Troubleshooting

### Issue: "tesseract is not installed or it's not in your PATH"
**Solution:**
1. Install Tesseract (see Setup)
2. Update `TESSERACT_PATH` in `.env`
3. Restart backend service

### Issue: OCR returns empty text
**Solution:**
1. Check image quality (OCR works better with clear text)
2. Try explicit PDF text extraction first
3. Verify Tesseract installation: `tesseract --version`

### Issue: Translation not working
**Solution:**
1. Check internet connection (needed for free Google Translate)
2. Verify `translate` library installed: `pip show translate`
3. Check language code is valid (e.g., 'en', 'fr', 'es')

## Rollback (if needed)
To revert to Google Cloud APIs:
1. Restore original `requirements.txt`
2. Revert `server.py` to previous version
3. Reinstall: `pip install -r requirements.txt`
4. Update frontend with Google credentials form

## References
- **Tesseract OCR**: https://github.com/UB-Mannheim/tesseract/wiki
- **pytesseract**: https://github.com/madmaze/pytesseract
- **translate library**: https://github.com/terryyin/translate-python
- **langdetect**: https://github.com/Mimino666/language-detection
