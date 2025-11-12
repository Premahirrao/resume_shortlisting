from fastapi import FastAPI, APIRouter, UploadFile, File, Form, HTTPException
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

# Configure Tesseract OCR
tesseract_path = os.environ.get('TESSERACT_PATH')
if tesseract_path and os.path.exists(tesseract_path):
    pytesseract.pytesseract.pytesseract_cmd = tesseract_path
else:
    # Try common Windows path if not set
    common_paths = [
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe'
    ]
    for path in common_paths:
        if os.path.exists(path):
            pytesseract.pytesseract.pytesseract_cmd = path
            break

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Initialize AI models (lazy loading)
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

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Define Models
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
    google_cloud_credentials: str  # JSON string
    github_token: Optional[str] = None
    leetcode_session: Optional[str] = None
    codechef_key: Optional[str] = None

# Helper Functions
def extract_text_from_pdf(file_content: bytes) -> str:
    """Extract text from PDF file"""
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        logging.error(f"PDF extraction error: {e}")
        return ""

async def ocr_image_pytesseract(image_content: bytes) -> str:
    """Perform OCR using Tesseract (open-source, no credentials needed)"""
    try:
        image = Image.open(io.BytesIO(image_content))
        text = pytesseract.image_to_string(image)
        return text.strip() if text else ""
    except Exception as e:
        logging.error(f"OCR error: {e}")
        return ""

async def translate_text(text: str, target_language: str = 'en') -> tuple:
    """Translate text using open-source translate library (no credentials needed)"""
    try:
        if not text or len(text.strip()) == 0:
            return text, 'en'
        
        # Detect source language
        try:
            source_lang = detect(text)
        except LangDetectException:
            source_lang = 'en'
        
        # If already English, return as-is
        if source_lang == target_language:
            return text, source_lang
        
        # Translate to target language
        try:
            translator = Translator(from_lang=source_lang, to_lang=target_language)
            translated_text = translator.translate(text)
            return translated_text, source_lang
        except Exception as translate_error:
            logging.warning(f"Translation failed, returning original text: {translate_error}")
            return text, source_lang
    except Exception as e:
        logging.error(f"Translation error: {e}")
        return text, 'en'

async def fetch_github_stats(username: str, token: Optional[str] = None) -> Dict:
    """Fetch GitHub statistics"""
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
                        'total_stars': 0  # Would need to fetch repos to get stars
                    }
        return {'public_repos': 0, 'followers': 0, 'total_stars': 0}
    except Exception as e:
        logging.error(f"GitHub fetch error: {e}")
        return {'public_repos': 0, 'followers': 0, 'total_stars': 0}

async def fetch_leetcode_stats(username: str) -> Dict:
    """Fetch LeetCode statistics"""
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
            async with session.post(
                'https://leetcode.com/graphql',
                json={'query': query, 'variables': {'username': username}}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('data', {}).get('matchedUser'):
                        submissions = data['data']['matchedUser']['submitStats']['acSubmissionNum']
                        total = sum(item['count'] for item in submissions)
                        return {'total_solved': total}
        return {'total_solved': 0}
    except Exception as e:
        logging.error(f"LeetCode fetch error: {e}")
        return {'total_solved': 0}

async def fetch_codechef_stats(username: str) -> Dict:
    """Fetch CodeChef statistics"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f'https://www.codechef.com/users/{username}') as resp:
                if resp.status == 200:
                    # This is simplified - actual implementation would parse HTML
                    return {'problems_solved': 0, 'rating': 0}
        return {'problems_solved': 0, 'rating': 0}
    except Exception as e:
        logging.error(f"CodeChef fetch error: {e}")
        return {'problems_solved': 0, 'rating': 0}

def calculate_social_score(github_data: Dict, leetcode_data: Dict, codechef_data: Dict) -> float:
    """Calculate social score from 0-100"""
    # Weights
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
    
    # Combined social score
    social_score = (github_score * 0.4 + leetcode_score * 0.4 + codechef_score * 0.2)
    return min(100, social_score)

def extract_social_usernames(text: str) -> Dict[str, str]:
    """Extract social media usernames from resume text"""
    import re
    
    usernames = {
        'github': None,
        'leetcode': None,
        'codechef': None
    }
    
    # GitHub patterns
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
    
    # LeetCode patterns
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
    
    # CodeChef patterns
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

# API Routes
@api_router.get("/")
async def root():
    return {"message": "AI Resume Shortlisting System"}

@api_router.post("/process")
async def process_resumes(
    job_description: str = Form(...),
    google_credentials: str = Form(default=''),  # kept for backward compatibility but not used
    github_token: Optional[str] = Form(None),
    resume_files: List[UploadFile] = File(...)
):
    """Main processing endpoint"""
    try:
        # Step 1: Extract job description
        jd_text = job_description
        
        # Step 2: Process resumes
        processed_resumes = []
        
        for file in resume_files:
            content = await file.read()
            filename = file.filename
            
            # Extract text based on file type
            text = ""
            if filename.lower().endswith('.pdf'):
                text = extract_text_from_pdf(content)
                
                # If PDF extraction failed or minimal text, try OCR
                if len(text.strip()) < 100:
                    text = await ocr_image_pytesseract(content)
            else:
                # Assume image file
                text = await ocr_image_pytesseract(content)
            
            if not text:
                continue
            
            # Translate if needed
            translated_text, source_lang = await translate_text(text)
            
            # Store resume
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
        
        # Step 3: Generate embeddings with Bi-Encoder
        model = get_bi_encoder()
        jd_embedding = model.encode(jd_text, convert_to_tensor=False)
        
        candidates = []
        for resume in processed_resumes:
            resume_text = resume['translated_text'] or resume['original_text']
            resume_embedding = model.encode(resume_text, convert_to_tensor=False)
            
            # Calculate cosine similarity
            similarity = float(np.dot(jd_embedding, resume_embedding) / 
                             (np.linalg.norm(jd_embedding) * np.linalg.norm(resume_embedding)))
            
            candidates.append({
                'resume_id': resume['id'],
                'filename': resume['filename'],
                'bi_encoder_score': similarity * 100,  # Convert to 0-100 scale
                'resume_text': resume_text,
                'original_data': resume
            })
        
        # Step 4: Rerank with Cross-Encoder (top 20 if more candidates)
        candidates.sort(key=lambda x: x['bi_encoder_score'], reverse=True)
        top_candidates = candidates[:min(20, len(candidates))]
        
        cross_enc = get_cross_encoder()
        for candidate in top_candidates:
            pairs = [[jd_text, candidate['resume_text']]]
            score = cross_enc.predict(pairs)[0]
            candidate['cross_encoder_score'] = float(score) * 100
        
        # Step 5: Fetch social scores
        for candidate in top_candidates:
            usernames = extract_social_usernames(candidate['resume_text'])
            
            # Fetch social data
            github_data = await fetch_github_stats(usernames['github'], github_token) if usernames['github'] else {'public_repos': 0, 'followers': 0, 'total_stars': 0}
            leetcode_data = await fetch_leetcode_stats(usernames['leetcode']) if usernames['leetcode'] else {'total_solved': 0}
            codechef_data = await fetch_codechef_stats(usernames['codechef']) if usernames['codechef'] else {'problems_solved': 0, 'rating': 0}
            
            candidate['github_data'] = github_data
            candidate['leetcode_data'] = leetcode_data
            candidate['codechef_data'] = codechef_data
            
            # Calculate social score
            social_score = calculate_social_score(github_data, leetcode_data, codechef_data)
            candidate['social_score'] = social_score
            
            # Calculate combined score (70% contextual + 30% social)
            contextual_score = (candidate['bi_encoder_score'] * 0.3 + candidate['cross_encoder_score'] * 0.7)
            candidate['combined_score'] = contextual_score * 0.7 + social_score * 0.3
        
        # Step 6: Sort by combined score and get top 10
        top_candidates.sort(key=lambda x: x['combined_score'], reverse=True)
        final_results = top_candidates[:10]
        
        # Save results to database
        result_doc = {
            'id': str(uuid.uuid4()),
            'job_description': jd_text,
            'results': final_results,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        await db.results.insert_one(result_doc)
        
        return {
            'success': True,
            'total_processed': len(processed_resumes),
            'top_candidates': final_results
        }
        
    except Exception as e:
        logging.error(f"Processing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/results")
async def get_results():
    """Get latest results"""
    try:
        results = await db.results.find({}, {"_id": 0}).sort("timestamp", -1).limit(10).to_list(10)
        return results
    except Exception as e:
        logging.error(f"Results fetch error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Standalone Vision & Translation Endpoints
@api_router.post("/ocr")
async def ocr_endpoint(
    file: UploadFile = File(...),
    google_credentials: str = Form(...)
):
    """Direct OCR endpoint for images and PDFs
    
    Usage:
    - Upload image (JPG, PNG) or PDF file
    - (Google credentials kept for backward compatibility but not required)
    - Returns extracted text
    """
    try:
        content = await file.read()
        filename = file.filename
        
        # Handle PDF or image
        text = ""
        if filename.lower().endswith('.pdf'):
            text = extract_text_from_pdf(content)
            # Fallback to OCR if PDF text extraction minimal
            if len(text.strip()) < 100:
                text = await ocr_image_pytesseract(content)
        else:
            # Image file
            text = await ocr_image_pytesseract(content)
        
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
        logging.error(f"OCR endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/translate")
async def translate_endpoint(
    text: str = Form(...),
    google_credentials: str = Form(default='') ,  # kept for backward compatibility but not used
    target_language: str = Form(default='en')
):
    """Direct translation endpoint
    
    Usage:
    - Provide text to translate
    - (Google credentials kept for backward compatibility but not required)
    - Optionally specify target language (default: English)
    - Returns translated text and detected source language
    """
    try:
        if not text.strip():
            raise HTTPException(status_code=400, detail="Text cannot be empty")
        
        translated_text, source_lang = await translate_text(
            text, 
            target_language
        )
        
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
        logging.error(f"Translation endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/batch-ocr")
async def batch_ocr_endpoint(
    google_credentials: str = Form(default=''),  # kept for backward compatibility but not used
    files: List[UploadFile] = File(...)
):
    """Batch OCR endpoint for multiple files
    
    Usage:
    - Upload multiple image or PDF files
    - (Google credentials kept for backward compatibility but not required)
    - Returns extracted text for each file
    """
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
                        text = await ocr_image_pytesseract(content)
                else:
                    text = await ocr_image_pytesseract(content)
                
                results.append({
                    "filename": filename,
                    "success": bool(text),
                    "extracted_text": text,
                    "text_length": len(text) if text else 0
                })
            except Exception as e:
                logging.error(f"Error processing file {file.filename}: {e}")
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
        logging.error(f"Batch OCR error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/batch-translate")
async def batch_translate_endpoint(
    texts: str = Form(...),  # JSON array of texts
    google_credentials: str = Form(...),
    target_language: str = Form(default='en')
):
    """Batch translation endpoint for multiple texts
    
    Usage:
    - Provide JSON array of texts: ["text1", "text2", ...]
    - Provide Google Cloud credentials JSON
    - Optionally specify target language
    - Returns translated texts with language detection
    """
    try:
        # Parse JSON array
        import json
        text_list = json.loads(texts)
        
        if not isinstance(text_list, list):
            raise HTTPException(status_code=400, detail="Texts must be a JSON array")
        
        if not text_list:
            raise HTTPException(status_code=400, detail="Text list cannot be empty")
        
        results = []
        for text in text_list:
            try:
                if not text.strip():
                    results.append({
                        "original": text,
                        "success": False,
                        "error": "Empty text"
                    })
                    continue
                
                translated, source_lang = await translate_text(
                    text,
                    google_credentials,
                    target_language
                )
                
                results.append({
                    "original": text,
                    "translated": translated,
                    "source_language": source_lang,
                    "target_language": target_language,
                    "was_translated": source_lang != target_language,
                    "success": True
                })
            except Exception as e:
                logging.error(f"Error translating text: {e}")
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
        logging.error(f"Batch translate error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
