import streamlit as st
import os
from job_screening_pipeline import run_pipeline  # 🔁 Must return shortlist list

st.set_page_config(page_title="AI Job Screening System", page_icon="🤖", layout="centered")

st.title("🤖 AI-Driven Job Screening System")
st.subheader("Upload resumes and job description to match candidates intelligently")

# --- Upload Job Description ---
st.markdown("### 📋 Paste Job Description")
jd_text = st.text_area("Provide a clear job description with Skills, Experience, and Education required.", height=200)

# --- Upload Resumes ---
st.markdown("### 📂 Upload Resumes")
uploaded_files = st.file_uploader("Upload multiple .pdf, .docx, or .txt resumes", type=["pdf", "docx", "txt"], accept_multiple_files=True)

# --- Match Threshold Slider ---
threshold = st.slider("🎯 Minimum Match Score to Shortlist", min_value=10, max_value=100, value=80, step=5)

# --- Email Toggle ---
send_email_toggle = st.toggle("📧 Send Emails to Shortlisted Candidates", value=True)

# --- Run Button ---
if st.button("🚀 Run Screening"):
    if not jd_text.strip():
        st.warning("Please enter a valid job description.")
    elif not uploaded_files:
        st.warning("Please upload at least one resume.")
    else:
        # Create/reuse directory
        CV_FOLDER = "cvs"
        os.makedirs(CV_FOLDER, exist_ok=True)

        # Save resumes to disk
        for uploaded_file in uploaded_files:
            with open(os.path.join(CV_FOLDER, uploaded_file.name), "wb") as f:
                f.write(uploaded_file.getbuffer())

        # Call the main pipeline with params
        with st.spinner("Processing resumes and evaluating candidates..."):
            shortlisted = run_pipeline(jd_text, threshold=threshold, send_emails=send_email_toggle)

        st.success("✅ Screening complete.")
        st.balloons()

        if shortlisted:
            st.markdown("### 🏆 Shortlisted Candidates")
            import pandas as pd
            df = pd.DataFrame(shortlisted, columns=["ID", "Name", "Email", "Phone", "Skills", "Match Score (%)"])
            st.dataframe(df)

            # ✅ Download CSV
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Shortlisted Candidates as CSV",
                data=csv,
                file_name='shortlisted_candidates.csv',
                mime='text/csv'
            )
        else:
            st.info("No candidates met the shortlisting criteria.")
