# main.py - Corrected full file for FastAPI AI Resume Shortlisting
# Key fixes:
# - Robust Tesseract configuration for Windows (use env var only, no --tessdata-dir)
# - Avoid replacing backslashes in Windows paths
# - Ensure pytesseract.pytesseract.tesseract_cmd is set early
# - Fix batch-translate calling translate_text with wrong signature
# - Keep original app structure and endpoint logic

from fastapi import FastAPI, APIRouter, UploadFile, File, Form, HTTPException, Query
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict
import uuid
from datetime import datetime, timezone
import io
import PyPDF2
import fitz  # PyMuPDF
from utils.vector_db import PineconeSingleton
from utils.mongo import MongoDB
import json
import asyncio
import aiohttp
import numpy as np
from sentence_transformers import SentenceTransformer, CrossEncoder
import pytesseract
from PIL import Image
from langdetect import detect, LangDetectException
from translate import Translator
import tempfile

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# ---------------------------
# Configure basic logging
# ---------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ---------------------------
# Tesseract configuration
# ---------------------------
def configure_tesseract_from_env():
    """
    Configure Tesseract executable and TESSDATA_PREFIX based on environment variables
    and common installation paths on Windows. Avoid using --tessdata-dir CLI option;
    only rely on environment variable TESSDATA_PREFIX (recommended for Windows).
    """
    # Read from environment variables (if provided)
    tesseract_path_env = "C:\Program Files\Tesseract-OCR\tessdata.exe"
    tessdata_prefix_env = "C:\Program Files\Tesseract-OCR\tessdata"

    tesseract_cmd = None
    tessdata_prefix = None

    # If user provided explicit TESSERACT_PATH in env and it exists, use it
    if tesseract_path_env and os.path.exists(tesseract_path_env):
        tesseract_cmd = tesseract_path_env
        logger.info(f"Using TESSERACT_PATH from environment: {tesseract_cmd}")

    # Otherwise try common Windows install paths
    if not tesseract_cmd:
        common_paths = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"
        ]
        for p in common_paths:
            if os.path.exists(p):
                tesseract_cmd = p
                logger.info(f"Found tesseract at common path: {p}")
                break

    # Set the tesseract command if found
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    else:
        logger.warning("Tesseract executable not found. Please install Tesseract or set TESSERACT_PATH in .env")

    # If user provided TESSDATA_PREFIX in env and it exists, use it
    if tessdata_prefix_env and os.path.exists(tessdata_prefix_env):
        tessdata_prefix = tessdata_prefix_env
        os.environ['TESSDATA_PREFIX'] = tessdata_prefix_env
        logger.info(f"Using TESSDATA_PREFIX from environment: {tessdata_prefix_env}")
    else:
        # If not provided, try to infer tessdata directory adjacent to tesseract executable
        if tesseract_cmd:
            inferred = os.path.join(os.path.dirname(tesseract_cmd), 'tessdata')
            if os.path.exists(inferred):
                tessdata_prefix = inferred
                os.environ['TESSDATA_PREFIX'] = inferred
                logger.info(f"Inferred TESSDATA_PREFIX: {inferred}")

    # Final verification: check eng.traineddata exists
    if tessdata_prefix and os.path.exists(tessdata_prefix):
        eng_data = os.path.join(tessdata_prefix, "eng.traineddata")
        if os.path.exists(eng_data):
            logger.info("✓ Tesseract is configured and eng.traineddata found.")
            logger.info(f"  Tesseract cmd: {pytesseract.pytesseract.tesseract_cmd}")
            logger.info(f"  TESSDATA_PREFIX: {os.environ.get('TESSDATA_PREFIX')}")
            return True
        else:
            logger.warning(f"eng.traineddata not found in tessdata folder: {tessdata_prefix}")
            logger.warning("Please download language data (eng.traineddata) into tessdata directory.")
            return False
    else:
        logger.warning("TESSDATA_PREFIX not configured or tessdata directory not found.")
        return False

# Run configuration at import/startup
tesseract_configured = configure_tesseract_from_env()

# ---------------------------
# MongoDB connection (Atlas or local)
# ---------------------------
mongo_url = os.environ.get('MONGO_URL')
db_name = os.environ.get('DB_NAME', 'resume_shortlisting')

client = None
db = None

if mongo_url:
    try:
        client = AsyncIOMotorClient(
            mongo_url,
            serverSelectionTimeoutMS=10000,
            connectTimeoutMS=15000,
            socketTimeoutMS=30000,
            retryWrites=True,
            retryReads=True
        )
        db = client[db_name]
        logger.info(f"MongoDB client initialized for database: {db_name}")
    except Exception as e:
        logger.warning(f"MongoDB connection failed: {e}. Server will continue without DB persistence.")
        client = None
        db = None
else:
    logger.warning("MONGO_URL not set. Server will continue without database persistence.")

# ---------------------------
# AI model lazy loaders
# ---------------------------
bi_encoder = None
cross_encoder = None

def get_bi_encoder():
    global bi_encoder
    if bi_encoder is None:
        bi_encoder = SentenceTransformer('all-MiniLM-L6-v2')
    return bi_encoder

def get_cross_encoder():
    global cross_encoder
    if cross_encoder is None:
        cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
    return cross_encoder

# ---------------------------
# FastAPI app + router
# ---------------------------
app = FastAPI()
api_router = APIRouter(prefix="/api")

# ---------------------------
# Pydantic models
# ---------------------------
class JobDescription(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Resume(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    filename: str
    original_text: str
    translated_text: Optional[str] = None
    language: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CandidateResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    resume_id: str
    filename: str
    bi_encoder_score: float
    cross_encoder_score: float
    social_score: float
    combined_score: float
    github_data: Optional[Dict] = None
    leetcode_data: Optional[Dict] = None
    codechef_data: Optional[Dict] = None
    resume_text: str

class APIKeys(BaseModel):
    google_cloud_credentials: str
    github_token: Optional[str] = None
    leetcode_session: Optional[str] = None
    codechef_key: Optional[str] = None

# ---------------------------
# Helper functions (PDF, OCR, translation, social)
# ---------------------------
def extract_text_from_pdf(file_content: bytes) -> str:
    """Extract text using PyPDF2 text extraction. Returns empty string on failure."""
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
        text = ""
        for page in pdf_reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text.strip()
    except Exception as e:
        logger.error(f"PDF extraction error: {e}")
        return ""

def is_valid_image(content: bytes) -> bool:
    """Check if bytes represent a valid image file"""
    try:
        image = Image.open(io.BytesIO(content))
        image.verify()
        return True
    except Exception:
        return False

async def pdf_to_images(pdf_content: bytes) -> List[bytes]:
    """Convert PDF pages to PNG images using PyMuPDF (fitz). Returns list of png bytes."""
    if fitz is None:
        logger.error("PyMuPDF (fitz) not installed. Cannot convert PDF to images.")
        return []
    images = []
    try:
        pdf_document = fitz.open(stream=pdf_content, filetype="pdf")
        for page_num in range(len(pdf_document)):
            page = pdf_document[page_num]
            mat = fitz.Matrix(300 / 72, 300 / 72)  # 300 DPI
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_bytes = pix.tobytes("png")
            images.append(img_bytes)
        pdf_document.close()
        return images
    except Exception as e:
        logger.error(f"PDF to image conversion error: {e}")
        return []

async def ocr_pdf_pages(pdf_content: bytes) -> str:
    """Convert PDF pages to images and run OCR on each page."""
    try:
        page_images = await pdf_to_images(pdf_content)
        if not page_images:
            return ""
        all_text = []
        for page_num, image_bytes in enumerate(page_images):
            try:
                page_text = await ocr_image_pytesseract(image_bytes)
                if page_text:
                    all_text.append(f"--- Page {page_num + 1} ---\n{page_text}")
            except Exception as e:
                logger.warning(f"OCR failed for page {page_num + 1}: {e}")
        return "\n\n".join(all_text)
    except Exception as e:
        logger.error(f"OCR PDF pages error: {e}")
        return ""

async def ocr_image_pytesseract(image_content: bytes) -> str:
    """
    Perform OCR using pytesseract. NOTE: Do not pass --tessdata-dir on Windows;
    rely on environment variable TESSDATA_PREFIX (set at startup).
    """
    if not tesseract_configured:
        logger.error("Tesseract OCR is not properly configured. Cannot perform OCR.")
        return ""

    try:
        # Validate image
        if not is_valid_image(image_content):
            logger.warning("OCR attempted on non-image file")
            return ""

        # Open image
        image = Image.open(io.BytesIO(image_content))
        # Convert to RGB if needed (some PDFs produce paletted images)
        if image.mode != "RGB":
            image = image.convert("RGB")

        # Use language parameter; rely on TESSDATA_PREFIX env var for tessdata
        text = pytesseract.image_to_string(image, lang='eng')
        return text.strip() if text else ""
    except Exception as e:
        logger.error(f"OCR error: {e}")
        logger.error(f"Tesseract command: {pytesseract.pytesseract.tesseract_cmd}")
        logger.error(f"TESSDATA_PREFIX: {os.environ.get('TESSDATA_PREFIX', 'Not set')}")
        return ""

async def translate_text(text: str, target_language: str = 'en') -> tuple:
    """
    Translate text using the 'translate' library. Detects source language via langdetect.
    Returns (translated_text, source_language).
    """
    try:
        if not text or len(text.strip()) == 0:
            return text, 'en'
        try:
            source_lang = detect(text)
        except LangDetectException:
            source_lang = 'en'
        if source_lang == target_language:
            return text, source_lang
        try:
            translator = Translator(from_lang=source_lang, to_lang=target_language)
            translated_text = translator.translate(text)
            return translated_text, source_lang
        except Exception as translate_error:
            logger.warning(f"Translation failed; returning original text: {translate_error}")
            return text, source_lang
    except Exception as e:
        logger.error(f"Translation error: {e}")
        return text, 'en'

async def fetch_github_stats(username: str, token: Optional[str] = None) -> Dict:
    """Fetch GitHub statistics (simplified)."""
    try:
        headers = {}
        if token:
            headers['Authorization'] = f'token {token}'
        async with aiohttp.ClientSession() as session:
            async with session.get(f'https://api.github.com/users/{username}', headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        'public_repos': data.get('public_repos', 0),
                        'followers': data.get('followers', 0),
                        'total_stars': 0
                    }
        return {'public_repos': 0, 'followers': 0, 'total_stars': 0}
    except Exception as e:
        logger.error(f"GitHub fetch error: {e}")
        return {'public_repos': 0, 'followers': 0, 'total_stars': 0}

async def fetch_leetcode_stats(username: str) -> Dict:
    """Fetch LeetCode statistics via GraphQL (simplified)."""
    try:
        query = """
        query getUserProfile($username: String!) {
            matchedUser(username: $username) {
                submitStats {
                    acSubmissionNum {
                        difficulty
                        count
                    }
                }
            }
        }
        """
        async with aiohttp.ClientSession() as session:
            async with session.post('https://leetcode.com/graphql', json={'query': query, 'variables': {'username': username}}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('data', {}).get('matchedUser'):
                        submissions = data['data']['matchedUser']['submitStats']['acSubmissionNum']
                        total = sum(item['count'] for item in submissions)
                        return {'total_solved': total}
        return {'total_solved': 0}
    except Exception as e:
        logger.error(f"LeetCode fetch error: {e}")
        return {'total_solved': 0}

async def fetch_codechef_stats(username: str) -> Dict:
    """Fetch CodeChef statistics (simplified placeholder)."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f'https://www.codechef.com/users/{username}') as resp:
                if resp.status == 200:
                    return {'problems_solved': 0, 'rating': 0}
        return {'problems_solved': 0, 'rating': 0}
    except Exception as e:
        logger.error(f"CodeChef fetch error: {e}")
        return {'problems_solved': 0, 'rating': 0}

def calculate_social_score(github_data: Dict, leetcode_data: Dict, codechef_data: Dict) -> float:
    """Calculate social score from 0-100"""
    github_score = min(100, (
        github_data.get('public_repos', 0) * 2 +
        github_data.get('followers', 0) * 1 +
        github_data.get('total_stars', 0) * 0.5
    ))
    leetcode_score = min(100, leetcode_data.get('total_solved', 0) * 0.5)
    codechef_score = min(100, (
        codechef_data.get('problems_solved', 0) * 0.3 +
        codechef_data.get('rating', 0) * 0.05
    ))
    social_score = (github_score * 0.4 + leetcode_score * 0.4 + codechef_score * 0.2)
    return min(100, social_score)

def extract_social_usernames(text: str) -> Dict[str, Optional[str]]:
    """Extract social media usernames from resume text (basic heuristics)."""
    import re
    usernames = {'github': None, 'leetcode': None, 'codechef': None}
    github_patterns = [
        r'github\.com/([\w-]+)',
        r'github:\s*([\w-]+)',
        r'github\s+username:\s*([\w-]+)'
    ]
    for pattern in github_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            usernames['github'] = match.group(1)
            break
    leetcode_patterns = [
        r'leetcode\.com/([\w-]+)',
        r'leetcode:\s*([\w-]+)',
        r'leetcode\s+username:\s*([\w-]+)'
    ]
    for pattern in leetcode_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            usernames['leetcode'] = match.group(1)
            break
    codechef_patterns = [
        r'codechef\.com/users/([\w-]+)',
        r'codechef:\s*([\w-]+)',
        r'codechef\s+username:\s*([\w-]+)'
    ]
    for pattern in codechef_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            usernames['codechef'] = match.group(1)
            break
    return usernames

# ---------------------------
# Routes
# ---------------------------
@app.get("/")
async def root():
    return {
        "message": "AI Resume Shortlisting System",
        "version": "1.0",
        "docs": "/docs",
        "api_base": "/api"
    }

@app.get("/favicon.ico")
async def favicon():
    from fastapi.responses import Response
    return Response(status_code=204)

@api_router.get("/")
async def api_root():
    return {"message": "AI Resume Shortlisting System API"}

@api_router.get("/results/all")
async def get_all_results(
    limit: int = Query(
        default=200,
        ge=1,
        le=2000,
        description="Maximum number of records to return (default 200, max 2000)."
    )
):
    """Fetch all stored results (up to the provided limit)."""
    if db is None:
        return {"message": "Database not available", "results": []}

    try:
        cursor = db.results.find({}, {"_id": 0}).sort("timestamp", -1).limit(limit)
        results = await cursor.to_list(length=limit)
        return {
            "count": len(results),
            "limit": limit,
            "results": results
        }
    except Exception as e:
        logger.error(f"All results fetch error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/process")
async def process_resumes(
    job_description: str = Form(...),
    google_credentials: str = Form(default=''),  # kept for backward compatibility
    github_token: Optional[str] = Form(None),
    resume_files: List[UploadFile] = File(...)
):
    """Main processing endpoint"""
    try:
        jd_text = job_description
        processed_resumes = []

        # STEP: Extract text from each uploaded resume
        for file in resume_files:
            content = await file.read()
            filename = file.filename
            text = ""

            if filename.lower().endswith('.pdf'):
                text = extract_text_from_pdf(content)
                # If PDF extraction failed or minimal text, try OCR on pages
                if len(text.strip()) < 100:
                    logger.info(f"PDF extraction returned minimal text for {filename}. Attempting OCR on converted images...")
                    ocr_text = await ocr_pdf_pages(content)
                    if ocr_text:
                        text = ocr_text
                        logger.info(f"Successfully extracted text from {filename} using OCR")
                    else:
                        logger.warning(f"Could not extract text from {filename} using OCR either.")
            else:
                # Assume image or other - validate image
                if is_valid_image(content):
                    text = await ocr_image_pytesseract(content)
                else:
                    logger.warning(f"File {filename} is not a valid image format")

            if not text:
                logger.warning(f"Could not extract text from {filename}. Skipping file.")
                continue

            # Translate if needed
            translated_text, source_lang = await translate_text(text)

            resume_data = {
                'id': str(uuid.uuid4()),
                'filename': filename,
                'original_text': text,
                'translated_text': translated_text,
                'language': source_lang,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            processed_resumes.append(resume_data)

        if not processed_resumes:
            raise HTTPException(status_code=400, detail="No resumes could be processed")

        # STEP: Generate embeddings (bi-encoder)
        model = get_bi_encoder()
        jd_embedding = model.encode(jd_text, convert_to_tensor=False)

        candidates = []
        for resume in processed_resumes:
            resume_text = resume['translated_text'] or resume['original_text']
            resume_embedding = model.encode(resume_text, convert_to_tensor=False)

            # Cosine similarity
            similarity = float(np.dot(jd_embedding, resume_embedding) /
                               (np.linalg.norm(jd_embedding) * np.linalg.norm(resume_embedding)))

            candidates.append({
                'resume_id': resume['id'],
                'filename': resume['filename'],
                'bi_encoder_score': similarity * 100,
                'resume_text': resume_text,
                'language': resume.get('language', 'en'),
                'translated': resume.get('language', 'en') != 'en',
                'original_data': resume
            })

        # STEP: Rerank with cross-encoder (top 20)
        candidates.sort(key=lambda x: x['bi_encoder_score'], reverse=True)
        top_candidates = candidates[:min(20, len(candidates))]

        cross_enc = get_cross_encoder()
        for candidate in top_candidates:
            pairs = [[jd_text, candidate['resume_text']]]
            try:
                score = cross_enc.predict(pairs)[0]
                candidate['cross_encoder_score'] = float(score) * 100
            except Exception as e:
                logger.warning(f"Cross-encoder scoring failed for {candidate['filename']}: {e}")
                candidate['cross_encoder_score'] = candidate['bi_encoder_score']

        # STEP: Social scores and combined score
        for candidate in top_candidates:
            usernames = extract_social_usernames(candidate['resume_text'])
            github_data = {'public_repos': 0, 'followers': 0, 'total_stars': 0}
            leetcode_data = {'total_solved': 0}
            codechef_data = {'problems_solved': 0, 'rating': 0}

            if usernames.get('github'):
                github_data = await fetch_github_stats(usernames['github'], github_token)
            if usernames.get('leetcode'):
                leetcode_data = await fetch_leetcode_stats(usernames['leetcode'])
            if usernames.get('codechef'):
                codechef_data = await fetch_codechef_stats(usernames['codechef'])

            candidate['github_data'] = github_data
            candidate['leetcode_data'] = leetcode_data
            candidate['codechef_data'] = codechef_data

            social_score = calculate_social_score(github_data, leetcode_data, codechef_data)
            candidate['social_score'] = social_score

            contextual_score = (candidate['bi_encoder_score'] * 0.3 + candidate['cross_encoder_score'] * 0.7)
            candidate['combined_score'] = contextual_score * 0.7 + social_score * 0.3

        # Final sorting and select top 10
        top_candidates.sort(key=lambda x: x['combined_score'], reverse=True)
        final_results = top_candidates[:10]

        # Prepare frontend-friendly rankings
        bi_encoder_ranking = sorted(candidates, key=lambda x: x['bi_encoder_score'], reverse=True)
        bi_encoder_ranking = [{
            'resume_id': c['resume_id'],
            'filename': c['filename'],
            'bi_encoder_score': c['bi_encoder_score'],
            'resume_text': c['resume_text'],
            'language': c['original_data'].get('language', 'en'),
            'translated': c['original_data'].get('language', 'en') != 'en'
        } for c in bi_encoder_ranking]

        cross_encoder_ranking = [{
            'resume_id': c['resume_id'],
            'filename': c['filename'],
            'bi_encoder_score': c['bi_encoder_score'],
            'cross_encoder_score': c.get('cross_encoder_score', 0),
            'resume_text': c['resume_text'],
            'language': c['original_data'].get('language', 'en'),
            'translated': c['original_data'].get('language', 'en') != 'en'
        } for c in top_candidates]

        # Persist results if DB available
        if db is not None:
            try:
                result_doc = {
                    'id': str(uuid.uuid4()),
                    'job_description': jd_text,
                    'results': final_results,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
                await db.results.insert_one(result_doc)
            except Exception as db_error:
                logger.warning(f"Failed to save results to database: {db_error}")

        return {
            'success': True,
            'total_processed': len(processed_resumes),
            'bi_encoder_ranking': bi_encoder_ranking,
            'cross_encoder_ranking': cross_encoder_ranking,
            'top_candidates': final_results
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Processing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@api_router.get("/results")
async def get_results():
    """Get latest results"""
    if db is None:
        return {"message": "Database not available", "results": []}
    try:
        results = await db.results.find({}, {"_id": 0}).sort("timestamp", -1).limit(10).to_list(10)
        return results
    except Exception as e:
        logger.error(f"Results fetch error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/results/all")
async def get_all_results(
    limit: int = Query(
        default=200,
        ge=1,
        le=2000,
        description="Maximum number of records to return (default 200, max 2000)."
    )
):
    """Fetch all stored results (up to the provided limit)."""
    if db is None:
        return {"message": "Database not available", "results": []}

    try:
        cursor = db.results.find({}, {"_id": 0}).sort("timestamp", -1).limit(limit)
        results = await cursor.to_list(length=limit)
        return {
            "count": len(results),
            "limit": limit,
            "results": results
        }
    except Exception as e:
        logger.error(f"All results fetch error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/process-new")
async def process_resumes(
    job_description: str = Form(...),
    google_credentials: str = Form(default=''),
    github_token: Optional[str] = Form(None),
    resume_files: List[UploadFile] = File(...)
):
    try:
        jd_text = job_description
        processed = []

        for file in resume_files:
            content = await file.read()
            filename = file.filename
            text = ""

            if filename.lower().endswith('.pdf'):
                text = extract_text_from_pdf(content)
                if len(text.strip()) < 100:
                    ocr_text = await ocr_pdf_pages(content)
                    if ocr_text:
                        text = ocr_text
            else:
                if is_valid_image(content):
                    text = await ocr_image_pytesseract(content)

            if not text:
                continue

            translated, lang = await translate_text(text)

            rid = str(uuid.uuid4())
            processed.append({
                'id': rid,
                'filename': filename,
                'original_text': text,
                'translated_text': translated,
                'language': lang
            })

        if not processed:
            raise HTTPException(status_code=400, detail="No resumes could be processed")

        model = get_bi_encoder()
        jd_emb = model.encode(jd_text, convert_to_tensor=False)

        pine = PineconeSingleton()
        pine.set_index("llama-text-embed-v2-index")

        all_vectors = []
        candidates = []

        for r in processed:
            r_text = r['translated_text'] or r['original_text']
            emb = model.encode(r_text, convert_to_tensor=False)
            sim = float(np.dot(jd_emb, emb) / (np.linalg.norm(jd_emb) * np.linalg.norm(emb)))
            candidates.append({
                'resume_id': r['id'],
                'filename': r['filename'],
                'bi_encoder_score': sim * 100,
                'resume_text': r_text,
                'language': r['language'],
                'translated': r['language'] != 'en',
                'original_data': r
            })
            all_vectors.append({
                'id': r['id'],
                'values': emb,
                'metadata': {'filename': r['filename'], 'language': r['language']}
            })

        pine.upsert(all_vectors)

        candidates.sort(key=lambda x: x['bi_encoder_score'], reverse=True)
        top = candidates[:min(20, len(candidates))]

        cross_enc = get_cross_encoder()
        for c in top:
            try:
                c['cross_encoder_score'] = float(cross_enc.predict([[jd_text, c['resume_text']]])[0]) * 100
            except:
                c['cross_encoder_score'] = c['bi_encoder_score']

        for c in top:
            u = extract_social_usernames(c['resume_text'])
            gh = await fetch_github_stats(u['github'], github_token) if u.get('github') else {'public_repos': 0, 'followers': 0, 'total_stars': 0}
            leet = await fetch_leetcode_stats(u['leetcode']) if u.get('leetcode') else {'total_solved': 0}
            cc = await fetch_codechef_stats(u['codechef']) if u.get('codechef') else {'problems_solved': 0, 'rating': 0}

            c['github_data'] = gh
            c['leetcode_data'] = leet
            c['codechef_data'] = cc

            s = calculate_social_score(gh, leet, cc)
            c['social_score'] = s
            ctx = (c['bi_encoder_score'] * 0.3 + c['cross_encoder_score'] * 0.7)
            c['combined_score'] = ctx * 0.7 + s * 0.3

        top.sort(key=lambda x: x['combined_score'], reverse=True)
        final = top[:10]

        bi_rank = sorted(candidates, key=lambda x: x['bi_encoder_score'], reverse=True)
        bi_rank = [{
            'resume_id': c['resume_id'],
            'filename': c['filename'],
            'bi_encoder_score': c['bi_encoder_score'],
            'resume_text': c['resume_text'],
            'language': c['original_data']['language'],
            'translated': c['original_data']['language'] != 'en'
        } for c in bi_rank]

        cross_rank = [{
            'resume_id': c['resume_id'],
            'filename': c['filename'],
            'bi_encoder_score': c['bi_encoder_score'],
            'cross_encoder_score': c.get('cross_encoder_score', 0),
            'resume_text': c['resume_text'],
            'language': c['original_data']['language'],
            'translated': c['original_data']['language'] != 'en'
        } for c in top]

        if db is not None:
            try:
                doc_id = str(uuid.uuid4())
                await db.results.insert_one({
                    'id': doc_id,
                    'job_description_id': doc_id,
                    'pinecone_vector_ids': [r['id'] for r in processed],
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })
            except:
                pass

        return clean({
        'success': True,
        'total_processed': len(processed),
        'bi_encoder_ranking': bi_rank,
        'cross_encoder_ranking': cross_rank,
        'top_candidates': final
        })

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@api_router.post("/upload-resume")
async def upload_resume(resume_files: List[UploadFile] = File(...)):
    try:
        processed = []
        for file in resume_files:
            content = await file.read()
            filename = file.filename
            text = ""
            if filename.lower().endswith('.pdf'):
                text = extract_text_from_pdf(content)
                if len(text.strip()) < 100:
                    ocr_text = await ocr_pdf_pages(content)
                    if ocr_text:
                        text = ocr_text
            else:
                if is_valid_image(content):
                    text = await ocr_image_pytesseract(content)
            if not text:
                continue
            translated, lang = await translate_text(text)
            rid = str(uuid.uuid4())
            processed.append({
                'id': rid,
                'filename': filename,
                'original_text': text,
                'translated_text': translated,
                'language': lang,
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        if not processed:
            raise HTTPException(status_code=400, detail="No resumes processed")
        model = get_bi_encoder()
        pine = PineconeSingleton()
        pine.set_index("llama-text-embed-v2-index")
        vectors = []
        for r in processed:
            emb = model.encode(r['translated_text'] or r['original_text'], convert_to_tensor=False)
            vectors.append({
                "id": r["id"],
                "values": emb,
                "metadata": {
                    "filename": r["filename"],
                    "original_text": r["original_text"],
                    "translated_text": r["translated_text"],
                    "language": r["language"],
                    "timestamp": r["timestamp"]
                }
            })
        pine.upsert(vectors)
        return clean({"success": True, "stored_ids": stored_ids})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/rank-top5")
async def rank_top5(job_description: str = Form(...)):
    try:
        model = get_bi_encoder()
        jd_emb = model.encode(job_description, convert_to_tensor=False)
        pine = PineconeSingleton()
        pine.set_index("llama-text-embed-v2-index")
        result = pine.query(jd_emb, top_k=20)
        matches = result["matches"]
        cross = get_cross_encoder()
        scored = []
        for m in matches:
            resume_text = m["metadata"]["translated_text"] or m["metadata"]["original_text"]
            cross_score = float(cross.predict([[job_description, resume_text]])[0]) * 100
            scored.append({
                "id": m["id"],
                "filename": m["metadata"]["filename"],
                "resume_text": resume_text,
                "bi_encoder_score": m["score"] * 100,
                "cross_encoder_score": cross_score,
                "combined_score": cross_score * 0.7 + (m["score"] * 100) * 0.3
            })
        scored.sort(key=lambda x: x["combined_score"], reverse=True)
        return {"top5": clean(scored[:5])}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------
# Standalone OCR & translation endpoints
# ---------------------------
@api_router.post("/ocr")
async def ocr_endpoint(
    file: UploadFile = File(...),
    google_credentials: str = Form(default='')
):
    """Direct OCR endpoint for images and PDFs"""
    try:
        content = await file.read()
        filename = file.filename
        text = ""
        if filename.lower().endswith('.pdf'):
            text = extract_text_from_pdf(content)
            if len(text.strip()) < 100:
                logger.info("PDF extraction returned minimal text. Attempting OCR on converted images...")
                ocr_text = await ocr_pdf_pages(content)
                if ocr_text:
                    text = ocr_text
                    logger.info("Successfully extracted text using OCR")
                else:
                    logger.warning("Could not extract text using OCR either.")
        else:
            if is_valid_image(content):
                text = await ocr_image_pytesseract(content)
            else:
                raise HTTPException(status_code=400, detail=f"File {filename} is not a valid image format")

        if not text:
            raise HTTPException(status_code=400, detail="Could not extract text from file")

        return {
            "success": True,
            "filename": filename,
            "extracted_text": text,
            "text_length": len(text),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OCR endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/translate")
async def translate_endpoint(
    text: str = Form(...),
    google_credentials: str = Form(default=''),
    target_language: str = Form(default='en')
):
    """Direct translation endpoint"""
    try:
        if not text.strip():
            raise HTTPException(status_code=400, detail="Text cannot be empty")

        translated_text, source_lang = await translate_text(text, target_language)

        return {
            "success": True,
            "original_text": text,
            "translated_text": translated_text,
            "source_language": source_lang,
            "target_language": target_language,
            "was_translated": source_lang != target_language,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Translation endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/batch-ocr")
async def batch_ocr_endpoint(
    google_credentials: str = Form(default=''),
    files: List[UploadFile] = File(...)
):
    """Batch OCR endpoint for multiple files"""
    try:
        if not files:
            raise HTTPException(status_code=400, detail="No files provided")
        results = []
        for file in files:
            try:
                content = await file.read()
                filename = file.filename
                text = ""
                if filename.lower().endswith('.pdf'):
                    text = extract_text_from_pdf(content)
                    if len(text.strip()) < 100:
                        logger.info(f"PDF extraction returned minimal text for {filename}. Attempting OCR on converted images...")
                        ocr_text = await ocr_pdf_pages(content)
                        if ocr_text:
                            text = ocr_text
                            logger.info(f"Successfully extracted text from {filename} using OCR")
                        else:
                            logger.warning(f"Could not extract text from {filename} using OCR either.")
                else:
                    if is_valid_image(content):
                        text = await ocr_image_pytesseract(content)
                    else:
                        logger.warning(f"File {filename} is not a valid image format")
                results.append({
                    "filename": filename,
                    "success": bool(text),
                    "extracted_text": text,
                    "text_length": len(text) if text else 0
                })
            except Exception as e:
                logger.error(f"Error processing file {file.filename}: {e}")
                results.append({
                    "filename": file.filename,
                    "success": False,
                    "error": str(e)
                })
        return {
            "success": True,
            "total_files": len(files),
            "successful": sum(1 for r in results if r['success']),
            "results": results,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Batch OCR error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/batch-translate")
async def batch_translate_endpoint(
    texts: str = Form(...),  # JSON array of texts
    google_credentials: str = Form(default=''),
    target_language: str = Form(default='en')
):
    """
    Batch translation endpoint.
    Expects `texts` as a JSON array string: '["text1", "text2", ...]'.
    """
    try:
        text_list = json.loads(texts)
        if not isinstance(text_list, list):
            raise HTTPException(status_code=400, detail="Texts must be a JSON array")
        if not text_list:
            raise HTTPException(status_code=400, detail="Text list cannot be empty")

        results = []
        for text in text_list:
            try:
                if not isinstance(text, str) or not text.strip():
                    results.append({
                        "original": text,
                        "success": False,
                        "error": "Empty or invalid text"
                    })
                    continue
                translated, source_lang = await translate_text(text, target_language)
                results.append({
                    "original": text,
                    "translated": translated,
                    "source_language": source_lang,
                    "target_language": target_language,
                    "was_translated": source_lang != target_language,
                    "success": True
                })
            except Exception as e:
                logger.error(f"Error translating text: {e}")
                results.append({
                    "original": text,
                    "success": False,
                    "error": str(e)
                })

        return {
            "success": True,
            "total_texts": len(text_list),
            "successful": sum(1 for r in results if r.get('success', False)),
            "results": results,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except HTTPException:
        raise
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format for texts")
    except Exception as e:
        logger.error(f"Batch translate error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Register router
app.include_router(api_router)

def clean(o):
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.float32, np.float64)):
        return float(o)
    if isinstance(o, (np.int32, np.int64)):
        return int(o)
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [clean(v) for v in o]
    return o


# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*", "http://localhost", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shutdown handler
@app.on_event("shutdown")
async def shutdown_db_client():
    if client is not None:
        client.close()

# Run as script
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
