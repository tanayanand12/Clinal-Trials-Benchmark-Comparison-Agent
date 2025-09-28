from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any
from main import BenchmarkComparison
import json
import os 
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()


# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Benchmark Comparison API",
    description="API for comparing the benchmark results on user clinical trials data and other clinical trials data",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# # Define request/response models
# class QueryRequest(BaseModel):
#     query: str
#     model_id: str

from pydantic import BaseModel, ConfigDict

class QueryRequest(BaseModel):
    query: str
    model_id: str
    model_config = ConfigDict(protected_namespaces=())  # silence "model_" warning


# Helper function for parallel processing
async def create_comparison_report_async(
    benchmark_agent: BenchmarkComparison,
    query: str,
    local_study: str,
    nct_id: str,
    content: str,
    executor: ThreadPoolExecutor
) -> Dict[str, Any]:
    """
    Async wrapper for creating individual comparison reports
    """
    def _create_report():
        try:
            return benchmark_agent.create_benchmark_comparison_1_v_1(
                question=query,
                local_agent_summary=local_study,
                study_id=nct_id,
                study_content=str(content)
            )
        except Exception as e:
            logger.error(f"Error creating report for NCT ID {nct_id}: {str(e)}")
            return f"Error generating report: {str(e)}"
    
    # Run the synchronous function in a thread executor
    loop = asyncio.get_event_loop()
    report = await loop.run_in_executor(executor, _create_report)
    
    return {
        "nct_id": nct_id,
        "report": report,
        "formatted_report": f"Comparison report for NCT ID {nct_id}:\n{report}"
    }

# Alternative approach using asyncio.gather for batch processing
async def create_all_comparison_reports_parallel(
    benchmark_agent: BenchmarkComparison,
    query: str,
    local_study: str,
    clinical_trials_data: Dict[str, Any],
    max_workers: int = 5
) -> List[str]:
    """
    Create all comparison reports in parallel using ThreadPoolExecutor
    """
    individual_reports = []
    individual_comparisons = {}
    # Create thread pool executor
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Create tasks for all comparisons
        tasks = []
        for nct_id, content in clinical_trials_data.items():
            logger.info(f"Scheduling 1-v-1 comparison report for NCT ID: {nct_id}")
            task = create_comparison_report_async(
                benchmark_agent=benchmark_agent,
                query=query,
                local_study=local_study,
                nct_id=nct_id,
                content=content,
                executor=executor
            )
            tasks.append(task)
        
        # Wait for all tasks to complete
        if tasks:
            logger.info(f"Running {len(tasks)} comparison reports in parallel...")
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Task failed with exception: {str(result)}")
                    individual_reports.append(f"Error generating report: {str(result)}")
                else:
                    logger.info(f"Completed report for NCT ID: {result['nct_id']}")
                    individual_reports.append(result['formatted_report'])
                    individual_comparisons[result['nct_id']] = result['report']
    
    return {"individual_reports": individual_reports, "individual_comparisons": individual_comparisons}

# Alternative approach using asyncio.as_completed for progressive results
async def create_comparison_reports_progressive(
    benchmark_agent: BenchmarkComparison,
    query: str,
    local_study: str,
    clinical_trials_data: Dict[str, Any],
    max_workers: int = 5
) -> List[str]:
    """
    Create comparison reports with progressive completion updates
    """
    individual_reports = []
    individual_comparisons = {}
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Create tasks
        tasks = {
            create_comparison_report_async(
                benchmark_agent=benchmark_agent,
                query=query,
                local_study=local_study,
                nct_id=nct_id,
                content=content,
                executor=executor
            ): nct_id for nct_id, content in clinical_trials_data.items()
        }
        
        # Process as they complete
        completed_count = 0
        total_count = len(tasks)
        
        for coro in asyncio.as_completed(tasks.keys()):
            try:
                result = await coro
                completed_count += 1
                nct_id = result['nct_id']
                logger.info(f"Completed {completed_count}/{total_count}: NCT ID {nct_id}")
                individual_reports.append(result['formatted_report'])
                individual_comparisons[nct_id] = result['report']
            except Exception as e:
                completed_count += 1
                logger.error(f"Completed {completed_count}/{total_count} with error: {str(e)}")
                individual_reports.append(f"Error generating report: {str(e)}")
    
    return {"individual_reports": individual_reports, "individual_comparisons": individual_comparisons}

@app.post("/benchmark_comparison/query")
async def benchmark_comparison(request: QueryRequest):
    try:
        start_time = datetime.now()
        benchmark_agent = BenchmarkComparison()
        logger.info(f"Received query: {request.query} for model_id: {request.model_id}")
        
        # Create local study profile
        local_study = benchmark_agent.create_local_study_profile(
            question=request.query,
            context={"model_id": request.model_id}
        )
        logger.info("Local study profile created successfully")
        # print(local_study)
        # print("********************************")
        
        # Fetch clinical trials data
        clinical_success = False
        attempt = 0
        while clinical_success == False:
            clinical_trials = benchmark_agent.fetch_clinical_ncts(local_study)
            # print(f"---------------{clinical_trials}")
            clinical_success = clinical_trials['success']
            attempt += 1
            logger.info(f"Attempt {attempt}: Clinical trials fetch success: {clinical_success} time elapsed: {datetime.now() - start_time}")
            if attempt > 5:
                break
        
        if clinical_success:
            # Limit to top 5 NCT IDs for faster parallel comparison
            clinical_trials_data = clinical_trials['data']
            if isinstance(clinical_trials_data, dict):
                # Select top 5 NCT IDs only
                limited_trials_data = dict(list(clinical_trials_data.items())[:5])
            else:
                limited_trials_data = clinical_trials_data

            parallel_run_reports = await create_all_comparison_reports_parallel(
                benchmark_agent=benchmark_agent,
                query=request.query,
                local_study=local_study,
                clinical_trials_data=limited_trials_data,
                max_workers=5  # Lowered for faster inference
            )

            individual_reports = parallel_run_reports['individual_reports']
            individual_comparisons = parallel_run_reports['individual_comparisons']

            logger.info(f"Created {len(individual_reports)} individual comparison reports, time elapsed: {datetime.now() - start_time}")

            # Create final combined report
            final_report = benchmark_agent.create_benchmark_comparison_combined(
                question=request.query,
                local_agent_summary=local_study,
                individual_reports=individual_reports
            )

            logger.info(f"Final combined report created, total time elapsed: {datetime.now() - start_time}")

            # NEW: parse if it is JSON; fall back gracefully
            try:
                parsed_final = json.loads(final_report) if isinstance(final_report, str) else final_report
            except json.JSONDecodeError:
                parsed_final = {"Response": str(final_report), "Statistics": {}}

            logger.info(f"Benchmark comparison process completed successfully in {datetime.now() - start_time}")

            return {
                "local_study": local_study,
                "clinical_trials": clinical_trials,
                "individual_comparison": individual_comparisons,
                "combined_comparison": parsed_final     # <-- now an object, not a string
            }
        else:
            return {
                "local_study": local_study,
                "clinical_trials": clinical_trials,
                "individual_comparison": [],
                "combined_comparison": "No clinical trials found after multiple attempts."
            }
            
    except Exception as e:
        logger.error(f"Error processing query: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/benchmark_comparison/health")
async def health_check():
    return {"status": "ok"}

@app.get("/benchmark_comparison/summary")
async def get_summary():
    return {
        "message": "This endpoint provides comparative benchmarking between local clinical trials research data and similar clinical trials in the clinicaltrials.gov database."
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "benchmark_comparison_api:app",
        host="0.0.0.0",
        port=8174,
        reload=True
    )
