import os
import time
import sys
import requests
import io
import zipfile
from github import Github
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate

# --- Configuration (read from env when possible) ---
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = os.getenv("REPO_NAME", "PR3MM/agenticpy")
RUN_ID = os.getenv("RUN_ID", "")

def get_failed_logs_and_details():
    if not GITHUB_TOKEN:
        print("ERROR: GITHUB_TOKEN environment variable is required.")
        sys.exit(1)

    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(REPO_NAME)
    run = None

    # If RUN_ID provided, try to fetch it
    if RUN_ID:
        try:
            run = repo.get_workflow_run(int(RUN_ID))
        except Exception as e:
            print(f"Warning: could not fetch run id {RUN_ID}: {e}")

    # Fallback: find the most recent failed run
    if run is None:
        print("Searching for the latest failed workflow run in the repository...")
        try:
            runs = repo.get_workflow_runs()
            for r in runs:
                conclusion = getattr(r, "conclusion", None)
                if conclusion == "failure":
                    run = r
                    break
        except Exception as e:
            print(f"ERROR: could not list workflow runs: {e}")
            raise

    if run is None:
        raise RuntimeError("No failed workflow run found for repository")

    # Attempt to download run logs ZIP from the REST API and extract text
    owner_repo = REPO_NAME.split("/", 1)
    if len(owner_repo) != 2:
        raise RuntimeError("REPO_NAME must be in the form 'owner/repo'")
    owner, repo_name = owner_repo

    logs_endpoint = f"https://api.github.com/repos/{owner}/{repo_name}/actions/runs/{run.id}/logs"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}

    resp = requests.get(logs_endpoint, headers=headers, stream=True, allow_redirects=True)
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to download logs archive: {resp.status_code} {resp.text}")

    # Load ZIP into memory and concatenate text files
    bio = io.BytesIO(resp.content)
    logs = ""
    try:
        with zipfile.ZipFile(bio) as z:
            for name in z.namelist():
                try:
                    with z.open(name) as f:
                        part = f.read().decode("utf-8", errors="ignore")
                        logs += f"\n--- {name} ---\n" + part
                except Exception:
                    continue
    except zipfile.BadZipFile:
        # If not a zip, try decode as text
        try:
            logs = resp.content.decode("utf-8", errors="ignore")
        except Exception:
            logs = ""

    return repo, run, logs


def get_fix_from_gemini(logs):
    llm = ChatGoogleGenerativeAI(model="gemini-3-flash-preview", temperature=0)

    # We ask Gemini to return ONLY the library name to keep it simple for now
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a DevOps bot. Analyze the logs. If a Python module is missing, return ONLY the name of the library that needs to be added to requirements.txt. No prose, no markdown."),
        ("user", "LOGS:\n{logs}")
    ])

    chain = prompt | llm
    response = chain.invoke({"logs": logs[-5000:]})
    
    content = response.content
    if isinstance(content, list) and content:
        # Assuming the text is in the first part of the list
        part = content[0]
        if isinstance(part, dict) and "text" in part:
            return part["text"].strip()
    elif isinstance(content, str):
        return content.strip()
    
    return "" # Return empty if no valid content found


def apply_fix_and_create_pr(repo, lib_name):
    print(f"🛠️ Creating fix for: {lib_name}...")

    # 1. Create a new branch
    main_branch = repo.get_branch("main")
    new_branch_name = f"fix-build-{int(time.time())}"
    repo.create_git_ref(ref=f"refs/heads/{new_branch_name}", sha=main_branch.commit.sha)

    # 2. Update requirements.txt by appending the missing lib
    try:
        file = repo.get_contents("requirements.txt", ref=new_branch_name)
        current = file.decoded_content.decode("utf-8") if file.decoded_content else ""
        if lib_name in current:
            new_content = current
        else:
            new_content = (current + "\n" + lib_name).strip() + "\n"

        repo.update_file(
            file.path,
            f"chore: add {lib_name} to requirements",
            new_content,
            file.sha,
            branch=new_branch_name,
        )
    except Exception:
        # If requirements.txt doesn't exist, create it
        repo.create_file(
            "requirements.txt",
            f"chore: add {lib_name} to requirements",
            lib_name + "\n",
            branch=new_branch_name,
        )

    # 3. Open the Pull Request
    pr = repo.create_pull(
        title=f"🚀 AI Fix: Add missing dependency {lib_name}",
        body="This PR was automatically generated by the Gemini Pipeline Doctor after a CI/CD failure.",
        head=new_branch_name,
        base="main",
    )
    print(f"✅ Success! PR opened at: {pr.html_url}")


if __name__ == "__main__":
    repo, run, logs = get_failed_logs_and_details()
    print(f"Using workflow run id: {run.id} (url: {run.html_url})")
    suggested_lib = get_fix_from_gemini(logs)

    if suggested_lib:
        apply_fix_and_create_pr(repo, suggested_lib)
    else:
        print("❌ Gemini couldn't find a missing library.")