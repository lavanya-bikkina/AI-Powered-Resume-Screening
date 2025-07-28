import streamlit as st
import os
from job_screening_pipeline import run_pipeline  # 🔁 Must return shortlist list

import tempfile
import pandas as pd




# --- Page Config ---
st.set_page_config(page_title="AI Job Screening System", page_icon="🤖", layout="centered")

# --- Title & Subtitle ---
st.title("🤖 AI-Driven Job Screening System")
st.markdown("Upload candidate resumes and a job description to intelligently match and shortlist candidates.")

# --- Job Description Input ---
st.markdown("### 📋 Paste Job Description")
jd_text = st.text_area("Provide a clear job description with skills, experience, and education required:", height=200)

# --- Resume Upload Section ---
st.markdown("### 📂 Upload Resumes")
uploaded_files = st.file_uploader("Upload multiple resumes (.pdf, .docx, .txt)", type=["pdf", "docx", "txt"], accept_multiple_files=True)

# --- Threshold & Email Options ---
threshold = st.slider("🎯 Match Score Threshold to Shortlist", min_value=10, max_value=100, value=80, step=5)
send_email_toggle = st.toggle("📧 Send Emails to Shortlisted Candidates", value=True)

# --- Screening Button ---
if st.button("🚀 Run Screening"):
    if not jd_text.strip():
        st.warning("❗ Please enter a valid job description.")
    elif not uploaded_files:
        st.warning("❗ Please upload at least one resume.")
    else:
        with st.spinner("🔍 Screening resumes..."):

            # Save resumes temporarily
            with tempfile.TemporaryDirectory() as tmpdirname:
                for file in uploaded_files:
                    filepath = os.path.join(tmpdirname, file.name)
                    with open(filepath, "wb") as f:
                        f.write(file.getbuffer())

                # 🔁 Run the screening pipeline
                try:
                    shortlisted = run_pipeline(jd_text, resume_folder=tmpdirname, threshold=threshold, send_emails=send_email_toggle)
                except Exception as e:
                    st.error(f"⚠️ Error during processing: {e}")
                    shortlisted = []

        st.success("✅ Screening Complete.")
        st.balloons()

        # Display Results
        if len(shortlisted) > 0:

            st.markdown("### 🏆 Shortlisted Candidates")
            df = pd.DataFrame(shortlisted, columns=["ID", "Name", "Email", "Phone", "Skills", "Match Score (%)", "Timestamp"])
            st.dataframe(df)

            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Shortlisted Candidates as CSV",
                data=csv,
                file_name='shortlisted_candidates.csv',
                mime='text/csv'
            )
        else:
            st.info("No candidates met the shortlisting criteria. Try lowering the match threshold.")
