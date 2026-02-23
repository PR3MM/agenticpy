import os
import requests
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate

# --- Configuration ---
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
# Make sure to set your GOOGLE_API_KEY in your environment variables too!
REPO_NAME = "YOUR_GITHUB_USERNAME/agentic-cicd-poc" # <-- CHANGE THIS
RUN_ID = "YOUR_FAILED_RUN_ID" # <-- Paste your failing GitHub Action run ID here

def get_failed_logs(repo, run_id, token):
    """Fetches the logs of a failed GitHub Action run."""
    print(f"🔍 Fetching logs for Run ID: {run_id}...")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # 1. Get the jobs for this run
    jobs_url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs"
    jobs_response = requests.get(jobs_url, headers=headers).json()
    
    if not jobs_response.get('jobs'):
        raise Exception("No jobs found for this run.")
        
    job_id = jobs_response['jobs'][0]['id']
    
    # 2. Download the logs for that specific job
    logs_url = f"https://api.github.com/repos/{repo}/actions/jobs/{job_id}/logs"
    logs_response = requests.get(logs_url, headers=headers)
    
    return logs_response.text

def analyze_logs_with_gemini(logs):
    """Passes the logs to Gemini to identify the fix."""
    print("🧠 Analyzing logs with Gemini Agent...")
    
    # Initialize the Gemini model
    llm = ChatGoogleGenerativeAI(
        model="gemini-1.5-flash", 
        temperature=0 # Temperature 0 keeps the agent focused and deterministic
    ) 
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an expert DevOps engineer and Python developer. Your job is to read CI/CD logs, identify why the build failed, and provide the exact code patch needed to fix it."),
        ("user", "The following GitHub Actions log contains a failure. Identify the error. If it is a missing dependency, tell me exactly what needs to be added to requirements.txt.\n\nLOGS:\n{logs}")
    ])
    
    chain = prompt | llm
    
    # Because Gemini handles massive context, we can pass a huge chunk of logs 
    # (grabbing the last 10,000 characters just to be safe)
    response = chain.invoke({"logs": logs[-10000:]})
    return response.content

if __name__ == "__main__":
    try:
        raw_logs = get_failed_logs(REPO_NAME, RUN_ID, GITHUB_TOKEN)
        fix_suggestion = analyze_logs_with_gemini(raw_logs)
        
        print("\n================ GEMINI DIAGNOSIS ================\n")
        print(fix_suggestion)
        print("\n==================================================")
        
    except Exception as e:
        print(f"Error: {e}")