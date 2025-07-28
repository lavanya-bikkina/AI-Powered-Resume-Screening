import os
import fitz  # PyMuPDF
import spacy
import sqlite3
import smtplib
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from docx import Document
from datetime import datetime
from dotenv import load_dotenv
import torch

from sentence_transformers import SentenceTransformer, util
model = SentenceTransformer('all-MiniLM-L6-v2')

# Load environment variables
load_dotenv(dotenv_path="secret.env")
SENDER_EMAIL = os.getenv("EMAIL_USER")
SENDER_PASSWORD = os.getenv("EMAIL_PASS")

nlp = spacy.load("en_core_web_sm")

CV_FOLDER = "cvs1"
DB_PATH = "job_screening.db"
SKILL_FILE = "skills.txt"

# ------------------ DB Init ------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS Candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, email TEXT, phone TEXT, skills TEXT, score REAL, created_at TEXT
        )
    ''')
    conn.commit()
    return conn, c

# ------------------ File Reading ------------------
def extract_text_from_file(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        doc = fitz.open(file_path)
        return "\n".join([page.get_text() for page in doc])
    elif ext == ".docx":
        doc = Document(file_path)
        return "\n".join([para.text for para in doc.paragraphs])
    elif ext == ".txt":
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    return ""

# ------------------ Info Extraction ------------------
def extract_email(text):
    match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', text)
    return match.group() if match else "unknown@example.com"

def extract_phone(text):
    matches = re.findall(r'((?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{3,4})', text)
    for match in matches:
        cleaned = re.sub(r'[^\d+]', '', match)
        if len(cleaned) >= 9:
            return match.strip()
    return "N/A"

def extract_name(text):
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    top5 = "\n".join(lines[:5])
    doc = nlp(top5)
    for ent in doc.ents:
        if ent.label_ == "PERSON" and len(ent.text.split()) >= 2:
            return ent.text.strip()
    return "Unknown"

# ------------------ Skill Extraction ------------------
def load_skills(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        return [line.strip().lower() for line in f if line.strip()]

def extract_skills(text, skill_list):
    text = text.lower()
    doc = nlp(text)
    tokens = set([token.lemma_ for token in doc if not token.is_stop])
    matched = []
    for skill in skill_list:
        skill_tokens = [token.lemma_ for token in nlp(skill.lower())]
        if all(token in tokens for token in skill_tokens):
            matched.append(skill)
    return matched

# ------------------ Score Calculation ------------------

def calculate_score(jd_skills, resume_skills, resume_text):
    if not jd_skills or not resume_skills:
        return 0.0

    jd_embeddings = model.encode(jd_skills, convert_to_tensor=True)
    resume_embeddings = model.encode(resume_skills, convert_to_tensor=True)

    cosine_scores = util.pytorch_cos_sim(jd_embeddings, resume_embeddings)

    match_score = 0
    matched_skills = 0

    for i in range(len(jd_skills)):
        max_score = float(torch.max(cosine_scores[i]))
        if max_score > 0.6:
            matched_skills += 1
            experience_years = extract_experience_for_skill(resume_text, jd_skills[i])
            weight = 1 + (experience_years / 10)  # Max 2x
            match_score += weight

    final_score = (match_score / len(jd_skills)) * 100
    return round(final_score, 2)

import re

def extract_experience_for_skill(text, skill):
    """
    Attempts to find years of experience for a given skill in the resume text.
    e.g., "5 years of experience in Python"
    """
    pattern = re.compile(rf'(\d+)\+?\s+(?:years|yrs)\s+(?:of\s+)?experience.*?{skill}', re.IGNORECASE)
    match = pattern.search(text)
    if match:
        return int(match.group(1))
    return 0

# ------------------ DB Insert or Update ------------------
def insert_or_update_candidate(cv, score, c, conn):
    print(f"Saving {cv['name']} to database...") 
    c.execute("SELECT * FROM Candidates WHERE email = ?", (cv['email'],))
    row = c.fetchone()
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    skills_str = ", ".join(cv['skills'])

    if row:
        # Update existing
        c.execute('''
            UPDATE Candidates
            SET name = ?, phone = ?, skills = ?, score = ?, created_at = ?
            WHERE email = ?
        ''', (cv['name'], cv['phone'], skills_str, score, created_at, cv['email']))
        print(f"🔄 Updated candidate: {cv['name']}")
    else:
        # Insert new
        c.execute('''
            INSERT INTO Candidates (name, email, phone, skills, score, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (cv['name'], cv['email'], cv['phone'], skills_str, score, created_at))
        print(f"✅ Inserted new candidate: {cv['name']}")
    conn.commit()

# ------------------ Email Sender ------------------
def send_email(to_email, name, score):
    subject = "🎯 Interview Shortlisting Notification"

    body = f"""
    <html><body>
    <p>Dear {name},</p>
    <p>Congratulations! You have been shortlisted based on your resume with a match score of <strong>{score}%</strong>.</p>
    <p>Please reply to this email to confirm your availability for the interview.</p>
    <p>Best regards,<br>HR Team</p>
    </body></html>
    """

    msg = MIMEMultipart("alternative")
    msg["From"] = SENDER_EMAIL
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
            print(f"📩 Email sent to {name} ({to_email})")
    except Exception as e:
        print(f"❌ Failed to send email to {to_email}: {e}")

# ------------------ Shortlist ------------------
def shortlist_candidates(c, threshold=60):
    c.execute("SELECT * FROM Candidates WHERE score >= ?", (threshold,))
    return c.fetchall()

# ------------------ Main Pipeline ------------------
def run_pipeline(jd_text, resume_folder="cvs", threshold=60, skills_file=SKILL_FILE, send_emails=True):
    import pandas as pd  # Make sure pandas is imported

    all_skills = load_skills(skills_file)
    jd_skills = extract_skills(jd_text, all_skills)
    print("\n📌 Extracted JD Skills:", jd_skills)

    conn, c = init_db()
    shortlisted = []

    if not os.path.exists(resume_folder):
        print(f"⚠️ Folder '{resume_folder}' not found.")
        return []

    for file in os.listdir(resume_folder):
        if file.endswith((".pdf", ".docx", ".txt")):
            path = os.path.join(resume_folder, file)
            text = extract_text_from_file(path)
            if not text.strip():
                print(f"⚠️ Empty file: {file}")
                continue

            cv = {
                "name": extract_name(text),
                "email": extract_email(text),
                "phone": extract_phone(text),
                "skills": extract_skills(text, all_skills),
                "raw_text": text
            }

            score = calculate_score(jd_skills, cv["skills"], cv["raw_text"])

            print(f"\n📄 CV: {file}")
            print(f"👤 Name: {cv['name']}")
            print(f"📧 Email: {cv['email']}")
            print(f"📞 Phone: {cv['phone']}")
            print(f"🛠 Skills: {cv['skills']}")
            print(f"✅ Match Score: {score}%")

            if score >= threshold:
                insert_or_update_candidate(cv, score, c, conn)
                shortlisted.append((cv["name"], cv["email"], cv["phone"], ", ".join(cv["skills"]), score))

    print("\n📋 Shortlisted Candidates:")
    shortlisted_db = shortlist_candidates(c, threshold)
    for cand in shortlisted_db:
        candidate_id, name, email, phone, skills, score, timestamp = cand
        if send_emails and email != "unknown@example.com":
            send_email(email, name, score)
        print(f"- {name} ({email}) — Score: {score}%")

    # Create DataFrame with 7 columns including Timestamp
    df = pd.DataFrame(shortlisted_db, columns=["ID", "Name", "Email", "Phone", "Skills", "Match Score (%)", "Timestamp"])

    files = os.listdir(resume_folder)
    print(f"📂 Found {len(files)} files in '{resume_folder}'")

    conn.close()
    return df  # Optionally return df instead of raw DB records if you want to use it elsewhere


# ------------------ Run Example ------------------
if __name__ == "__main__":
    job_description = """
    We are seeking an innovative AI Researcher to develop cutting-edge AI models and algorithms.
    You will work on advancing machine learning techniques, optimizing AI systems, and applying research
    to real-world applications.

    Responsibilities:
    - Conduct research in AI, deep learning, and NLP.
    - Develop and optimize machine learning models.
    - Collaborate with cross-functional teams.
    - Stay updated with the latest AI advancements.

    Qualifications:
    - Strong programming skills in Python, TensorFlow, or PyTorch.
    - Experience with model optimization, NLP, and data science tools.
    - Excellent problem-solving and analytical skills.
    """
    run_pipeline(job_description)

   
