import os
import fitz  # PyMuPDF
import spacy
import sqlite3
import smtplib
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fuzzywuzzy import fuzz
from dotenv import load_dotenv
from docx import Document
import google.generativeai as genai
load_dotenv(dotenv_path="secret.env")
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
from datetime import datetime
import os
import google.generativeai as genai

SENDER_EMAIL = os.getenv("EMAIL_USER")
SENDER_PASSWORD = os.getenv("EMAIL_PASS")

# ----------------- Constants -----------------
CV_FOLDER = "cvs1"
DB_PATH = "job_screening.db"
nlp = spacy.load("en_core_web_sm")


# ----------------- Database Setup -----------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS Candidates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, email TEXT, phone TEXT, skills TEXT, score REAL
    )''')
    try:
        c.execute("ALTER TABLE Candidates ADD COLUMN created_at TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists

    conn.commit()
    return conn, c

# ----------------- CV Parser -----------------
def extract_text_from_file(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == ".pdf":
        doc = fitz.open(file_path)
        return "\n".join([page.get_text("text") for page in doc])

    elif ext == ".docx":
        doc = Document(file_path)
        return "\n".join([para.text for para in doc.paragraphs])

    elif ext == ".txt":
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    else:
        print(f"⚠️ Unsupported file type: {ext}")
        return ""
    
def extract_email(text):
    email_regex = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'
    matches = re.findall(email_regex, text)
    if matches:
        return matches[0]
    return None


def extract_phone(text):
    # Matches numbers like +1-123-4567, (123) 456-7890, 123-456-7890, 1234567890
    phone_regex = r'((?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{3,4})'
    matches = re.findall(phone_regex, text)

    # Filter out very short strings like "+1-" or "123"
    for match in matches:
        cleaned = re.sub(r'[^\d+]', '', match)  # Keep digits and +
        if len(cleaned) >= 9:  # Must be at least 8 digits
            return match.strip()
    return "N/A"


from spacy.matcher import PhraseMatcher

from spacy.matcher import PhraseMatcher

import spacy
nlp = spacy.load("en_core_web_sm")

def extract_skills_from_cv(cv_text, jd_skills):
    cv_doc = nlp(cv_text.lower())
    cv_tokens = set([token.lemma_ for token in cv_doc if not token.is_stop])
    
    matched_skills = []
    for skill in jd_skills:
        skill_doc = nlp(skill.lower())
        skill_tokens = [token.lemma_ for token in skill_doc if not token.is_stop]
        if all(token in cv_tokens for token in skill_tokens):
            matched_skills.append(skill)
    return matched_skills

import spacy

# Load SpaCy English model
nlp = spacy.load("en_core_web_sm")

def extract_name(text):
    # Get the first 5 non-empty lines
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    top5 = "\n".join(lines[:5])  # Combine top 5 lines

    doc = nlp(top5)

    # Look for PERSON entities with at least a first and last name
    for ent in doc.ents:
        if ent.label_ == "PERSON" and len(ent.text.split()) >= 2:
            return ent.text.strip()

    return extract_name_from_gemini(text)
def extract_name_from_gemini(text):
    # Use Gemini AI to extract the name if the initial extraction is unknown
    try:
        prompt = f"Extract the name of the person from the following CV text:\n{text}"
        response = genai.GenerativeModel("gemini-1.5-pro").generate_content(prompt)
        name = response.text.strip()
        if name and len(name.split()) >= 2:
            return name
    except Exception as e:
        print(f"Error extracting name using Gemini AI: {e}")
    
    return "Unknown"

def parse_cv(cv_text, jd_keywords_list):
    doc = nlp(cv_text)
    

    #print("🧾 Text Sample:", cv_text[:100])
    name= extract_name(cv_text)
    phone = extract_phone(cv_text)
    email = extract_email(cv_text)
    skills = extract_skills_from_cv(cv_text,jd_keywords_list)

    return {
        "name": name or "Unknown",
        "email": email or "unknown@example.com",
        "phone": phone or "N/A",
        "skills": skills,
        "raw_text": cv_text
    }

# ----------------- JD Summarizer -----------------
def summarize_jd(jd_text):
    prompt = f"""
You are an expert job analyst.

From the following Job Description, extract only the most important and relevant **keywords** that describe:
- Technical skills (e.g. programming languages, tools, frameworks, platforms)
- Soft skills (e.g. communication, leadership, teamwork)
- Job titles,Experience not Education.


Only return a **comma-separated list** of the extracted keywords. Do not return anything else — no explanations, no formatting, just the keywords.

Job Description:
{jd_text}
"""

    model = genai.GenerativeModel("gemini-1.5-pro")
    response = model.generate_content(prompt)

    # Clean and return comma-separated keyword string
    try:
        keywords = response.text.strip()
        # Optional: remove newlines or extra formatting
        keywords = keywords.replace("\n", "").strip(", ")
        return keywords
    except Exception as e:
        print("Error extracting keywords:", e)
        print("Raw response:", response.text)
        return ""



# ----------------- Score Calculator -----------------
def calculate_match_score(cv, jd_summary):
    skill_match = len(set(cv['skills']) & set(jd_summary['skills_required']))
    total_required = len(jd_summary['skills_required']) or 1
    return round((skill_match / total_required) * 100, 2)

# ----------------- Email Sender -----------------
def send_email(to_email, candidate_name, score):
    subject = "Interview Invitation from [Your Company]"

    body = f"""
    <html>
    <body>
        <p>Dear {candidate_name},</p>
        <p>We are pleased to inform you that you have been shortlisted for the role based on your impressive profile (Match Score: {score}%).</p>
        <p><b>Interview Details:</b></p>
        <ul>
            <li><b>Date:</b> Choose between April 10–12</li>
            <li><b>Time:</b> 10:00 AM to 4:00 PM IST</li>
            <li><b>Mode:</b> Virtual (Zoom link will be shared upon confirmation)</li>
        </ul>
        <p>Please reply to this email with your preferred time slot.</p>
        <p>Warm regards,<br>HR Team<br>Your Company</p>
    </body>
    </html>
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
            print(f"📨 Email sent to {candidate_name} at {to_email}")
    except Exception as e:
        print(f"❌ Failed to send email to {to_email}: {e}")

# ----------------- Database Insertion -----------------
def insert_candidate(cv, score, c, conn):
    c.execute("SELECT * FROM Candidates WHERE email = ?", (cv['email'],))
    if c.fetchone():
        print(f"🔁 Candidate {cv['name']} already exists in the database.")
        return
    skills_str = ", ".join(cv['skills'])

    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO Candidates (name, email, phone, skills, score, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (cv['name'], cv['email'], cv['phone'], skills_str, score, created_at))
    conn.commit()

# ----------------- Shortlist & Notify -----------------
def shortlist_candidates(c, threshold=50):
    c.execute("SELECT * FROM Candidates WHERE score >= ?", (threshold,))
    return c.fetchall()

# ----------------- Main Pipeline -----------------
def run_pipeline(jd_text, threshold=80, send_emails=True):
    print("\n📌 Extracted Skills from JD:")
    jd_keywords = summarize_jd(jd_text)

    # Convert to list
    jd_keywords_list = [kw.strip() for kw in jd_keywords.split(",") if kw.strip()]

    # Print keywords
    print(", ".join(jd_keywords_list) or "No skills extracted")


    conn, c = init_db()
    # ⚠️ Clear existing records for fresh testing
    #c.execute("DELETE FROM Candidates")
    conn.commit()

    for file in os.listdir(CV_FOLDER):
        if file.endswith((".pdf", ".docx", ".txt")):  # ✅ Multiple formats
            file_path = os.path.join(CV_FOLDER, file)
            cv_text = extract_text_from_file(file_path)
            
            if not cv_text.strip():
                print(f"⚠️ Empty or unsupported file: {file}")
                continue

            parsed_cv = parse_cv(cv_text, jd_keywords_list)

            print(f"\n📄 CV: {file}")
            print(f"👤 Name: {parsed_cv['name']}")
            print(f"📧 Email: {parsed_cv['email']}")
            print(f"📞 Phone: {parsed_cv['phone']}")
            print(f"🛠 Extracted Skills from Resume: {', '.join(parsed_cv['skills']) or 'None'}")
            score = calculate_match_score(parsed_cv, {"skills_required": jd_keywords_list})
            insert_candidate(parsed_cv, score, c, conn)
            print(f"✅ Match Score: {score}%")
# Only test one specific resume
    # resume_filename = "C1234.pdf"  # 🔁 Change this to your actual file name
    # file_path = os.path.join(CV_FOLDER, resume_filename)

    # if os.path.exists(file_path):
    #     cv_text = extract_text_from_pdf(file_path)
    #     parsed_cv = parse_cv(cv_text)
    #     score = calculate_match_score(parsed_cv, jd_summary)
    #     insert_candidate(parsed_cv, score, c, conn)
    #     print(f"✅ Processed {parsed_cv['name']} — Match Score: {score}%")
    # else:
    #     print(f"❌ File not found: {file_path}")

    print("\n📋 Shortlisted Candidates:")
    shortlisted = shortlist_candidates(c)
    for cand in shortlisted:
        candidate_id, name, email, phone, skills, score = cand
        if email == "unknown@example.com":
            print(f"⚠️ Skipping {name} — no valid email found.")
            continue
        if not SENDER_EMAIL or not SENDER_PASSWORD:
            raise EnvironmentError("Missing email credentials in .env file!")

        print(f"- {name} ({email}) — Score: {score}%")
        if send_emails:
            send_email(to_email=email, candidate_name=name, score=score)

    conn.close()
    return shortlisted


# ----------------- Example Usage -----------------
if __name__ == "__main__":
    job_description = """  Robotics Engineer,"Description:
We are seeking an innovative Robotics Engineer to design, develop, and optimize robotic systems for automation and intelligent applications. You will work on hardware-software integration, motion control, and AI-driven robotics solutions.

Responsibilities:
Design, build, and test robotic systems for industrial or research applications.
Develop software algorithms for navigation, control, and automation.
Integrate sensors, actuators, and AI-based decision-making systems.
Troubleshoot and optimize robotic performance.
Stay updated with emerging robotics technologies and advancements.
Qualifications:
Bachelor�s or Master�s degree in Robotics, Mechanical Engineering, or related field.
Proficiency in C++, Python, and ROS (Robot Operating System).
Experience with embedded systems, motion planning, and AI applications in robotics.
Strong analytical and problem-solving skills",


"""
    run_pipeline(job_description) 

# taking job description as input in the terminal
#if __name__ == "__main__":
    # print("Enter Job Description below (use line breaks):\n")
    # print("Format:\nJob Title: ...\nSkills Required: ...\nExperience Required: ...\nEducation Required: ...\n")
    # print("End input with Ctrl+D (Linux/macOS) or Ctrl+Z then Enter (Windows):")

    # import sys
    # jd_input = sys.stdin.read()  # Read multiline input from terminal

    # run_pipeline(jd_input)

# If you prefer to write the JD in a .txt file (e.g., jd.txt) and read it:
# if __name__ == "__main__":
#     with open("jd.txt", "r") as file:
#         job_description = file.read()

#     run_pipeline(job_description)
