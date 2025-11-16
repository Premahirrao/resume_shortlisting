# Tesseract OCR Setup Guide

## Step-by-Step Installation and Configuration

### Step 1: Install Tesseract OCR

#### Windows:
1. **Download Tesseract OCR:**
   - Visit: https://github.com/UB-Mannheim/tesseract/wiki
   - Download the latest Windows installer (e.g., `tesseract-ocr-w64-setup-5.x.x.exe`)

2. **Install Tesseract:**
   - Run the installer
   - **Important:** During installation, make sure to check "Additional language data" and select "English"
   - Default installation path: `C:\Program Files\Tesseract-OCR\`
   - The installer will create:
     - `C:\Program Files\Tesseract-OCR\tesseract.exe`
     - `C:\Program Files\Tesseract-OCR\tessdata\` (contains language files)

3. **Verify Installation:**
   ```powershell
   # Check if Tesseract is installed
   tesseract --version
   
   # Check if tessdata directory exists
   Test-Path "C:\Program Files\Tesseract-OCR\tessdata"
   
   # Check if English language data exists
   Test-Path "C:\Program Files\Tesseract-OCR\tessdata\eng.traineddata"
   ```

#### Alternative: Using Chocolatey (if installed)
```powershell
choco install tesseract
```

### Step 2: Verify Language Data Files

The `eng.traineddata` file must exist in the tessdata directory:

```powershell
# Check if English language data exists
Get-ChildItem "C:\Program Files\Tesseract-OCR\tessdata\eng.traineddata"
```

If the file doesn't exist:
1. Reinstall Tesseract and ensure "English" language data is selected
2. Or download manually from: https://github.com/tesseract-ocr/tessdata
3. Place `eng.traineddata` in `C:\Program Files\Tesseract-OCR\tessdata\`

### Step 3: Configure Environment Variables (Optional)

If Tesseract is installed in a non-standard location, set these environment variables:

```powershell
# Set Tesseract executable path
$env:TESSERACT_PATH = "C:\Your\Custom\Path\tesseract.exe"

# Set tessdata directory path
$env:TESSDATA_PREFIX = "C:\Your\Custom\Path\tessdata"
```

Or create a `.env` file in the `backend` directory:

```env
TESSERACT_PATH=C:\Program Files\Tesseract-OCR\tesseract.exe
TESSDATA_PREFIX=C:\Program Files\Tesseract-OCR\tessdata
```

### Step 4: Test Tesseract OCR

Test if Tesseract works from Python:

```python
import pytesseract
from PIL import Image
import os

# Set path if needed
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
os.environ['TESSDATA_PREFIX'] = r'C:\Program Files\Tesseract-OCR\tessdata'

# Test OCR
# Create a simple test image or use an existing one
# text = pytesseract.image_to_string(Image.open('test.png'))
# print(text)
```

### Step 5: Restart Backend Server

After installation, restart your backend server:

```powershell
cd backend
python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

Check the logs for:
```
✓ Tesseract OCR configured successfully
  Tesseract: C:\Program Files\Tesseract-OCR\tesseract.exe
  Tessdata: C:\Program Files\Tesseract-OCR\tessdata
  Language data: C:\Program Files\Tesseract-OCR\tessdata\eng.traineddata
```

## Troubleshooting

### Error: "Could not find language data"
**Solution:**
1. Verify `eng.traineddata` exists in tessdata directory
2. Check TESSDATA_PREFIX is set correctly
3. Ensure the path doesn't have permission issues

### Error: "Tesseract not found"
**Solution:**
1. Verify Tesseract is installed: `tesseract --version`
2. Set TESSERACT_PATH in environment or `.env` file
3. Check the path in server logs

### Error: "Permission denied"
**Solution:**
1. Run PowerShell/Command Prompt as Administrator
2. Check folder permissions for tessdata directory
3. Ensure Python has read access to Tesseract installation

### Path with Spaces Issue
If you see errors with paths containing spaces:
- The code now handles this automatically
- Ensure TESSDATA_PREFIX is set correctly
- Check server logs for the actual path being used

## How It Works

1. **Text Extraction:**
   - PDFs: First tries PyPDF2 text extraction
   - If minimal text: Converts PDF pages to images using PyMuPDF, then runs OCR
   - Images: Direct OCR using Tesseract

2. **Translation:**
   - Detects source language automatically
   - Translates to English if needed
   - Uses free `translate` library (no API keys required)

3. **Processing Flow:**
   ```
   Upload Resume
   ↓
   Extract Text (PDF/Image)
   ↓
   Translate to English (if needed)
   ↓
   Bi-Encoder Scoring
   ↓
   Cross-Encoder Refinement
   ↓
   Social Score Calculation
   ↓
   Final Ranking
   ```

## Quick Verification

Run this command to verify everything is set up:

```powershell
python -c "import pytesseract; from PIL import Image; import os; os.environ['TESSDATA_PREFIX'] = r'C:\Program Files\Tesseract-OCR\tessdata'; pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'; print('Tesseract configured:', pytesseract.pytesseract.tesseract_cmd)"
```

If you see the path printed, Tesseract is configured correctly!

