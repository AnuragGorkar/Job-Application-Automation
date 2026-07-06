import sys
import asyncio
import shutil
import json
from pathlib import Path


# 1. Dynamically add the 'backend' directory to sys.path
current_dir = Path(__file__).resolve().parent
root_dir = current_dir.parent.parent
backend_dir = root_dir / "backend"

sys.path.append(str(backend_dir))

# 2. Import the ResumeManager from your FastAPI app
from app.services.resume_updaters.resume_manager import ResumeManager

async def main():
    # 3. Define paths
    original_resume_path = backend_dir / "app" / "assets" / "resume" / "SDE.tex"
    output_resume_path = current_dir / "updated_SDE.tex"

    if not original_resume_path.exists():
        print(f"Error: Could not find original resume at {original_resume_path}")
        return

    # 4. Copy to test_scripts to avoid modifying the real template
    shutil.copy(original_resume_path, output_resume_path)
    print(f"Copied original template to {output_resume_path}")

    # 5. Initialize the manager on the copied file
    manager = ResumeManager(str(output_resume_path))

    # 6. Load the mock LLM JSON payload
    llm_payload = {
      "SUM": "\\small{Senior Software Engineer with 3+ years of experience in distributed systems. Reduced latency by 80\\% and scaled systems to handle 500M+ requests. Proficient in Python, Java, and cloud architecture.}",
      "COURSES": {
        "COURSES_1": "Courses: Distributed Systems, Advanced Algorithms, Machine Learning",
        "COURSES_2": "Courses: Data Structures, Artificial Intelligence, Web Development"
      },
      "EXP": {
        "EXP_1_B1": "Led the migration of legacy monolith to microservices using Spring Boot and Docker, handling 5x traffic spikes",
        "EXP_1_B2": "Implemented Redis caching layer decreasing database load by 60\\% and improving average response time to sub-100ms",
        "EXP_2_B1": "Engineered real-time data ingestion pipelines in Python, processing over 10K events per second with zero data loss",
        "EXP_3_B1": "Automated ETL pipelines using PySpark on AWS EMR, cutting down daily processing time by 4 hours"
      },
      "PROJ": {
        "PROJ_1_TECH": "Python $|$ React $|$ AWS $|$ Docker",
        "PROJ_1_DESC": "Designed and deployed a full-stack e-commerce platform using React and FastAPI, supporting 10K daily active users",
        "PROJ_2_TECH": "Node.js $|$ MongoDB $|$ Express",
        "PROJ_2_DESC": "Developed a RESTful backend for a local ride-sharing app, integrating Google Maps API for real-time tracking"
      },
      "TECHNICAL_SKILLS": "\\textbf{Languages}{: Python, Java, Go, C++} \\\\\n\\textbf{Backend}{: Spring Boot, Node.js, Django, FastAPI} \\\\\n\\textbf{Cloud \\& DevOps}{: AWS, Docker, Kubernetes, Jenkins} \\\\\n\\textbf{Databases}{: PostgreSQL, MongoDB, Redis, Cassandra} \\\\"
    }
    
    raw_llm_json = json.dumps(llm_payload)

    # 7. Execute the manager pipeline
    print("\nApplying changes via ResumeManager...")
    result = await manager.process_llm_response(raw_llm_json)

    if result == "SUCCESS":
        print(f"\nSUCCESS! The resume has been successfully modified.")
        print(f"Check the output file at: {output_resume_path}")
    else:
        print(f"\nVALIDATION FAILED. The manager returned the following error prompt:\n")
        print(result)

if __name__ == "__main__":
    asyncio.run(main())