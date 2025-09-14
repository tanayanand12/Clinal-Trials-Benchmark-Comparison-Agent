# benchmark_comparison_agent/prompts.py
from string import Template
from textwrap import dedent

def create_study_profile_prompt(documents: list[dict]) -> str:
    """
    Creates the prompt to synthesize a structured study profile from a list of
    document dictionaries, including metadata and content.
    """
    concatenated_text = ""
    for doc in documents:
        # Extract metadata and page_content from the document dictionary
        metadata = doc.get('metadata', {})
        page_content = doc.get('page_content', '')
        
        # Format the metadata into a readable string
        meta_info = f"Source: {metadata.get('pdf_name', 'N/A')}, Page: {metadata.get('page_number', 'N/A')}, Topic: {metadata.get('topic', 'N/A')}"
        
        # Combine metadata and content for each chunk
        concatenated_text += f"--- Chunk Start ---\n"
        concatenated_text += f"[{meta_info}]\n\n"
        concatenated_text += f"{page_content}\n"
        concatenated_text += f"--- Chunk End ---\n\n"
    
    return f"""
    **System**: You are a meticulous medical research analyst. Your task is to read the following unstructured text extracted from a research paper and synthesize a structured, comprehensive summary formatted like a clinical trial record. Extract and clearly label the following sections. If a section is not mentioned, explicitly state "Not specified in provided text."

    **Instructions**:
    1.  **Brief Title**: Create a concise, descriptive title for the study.
    2.  **Detailed Summary**: Write a comprehensive paragraph summarizing the study's background, methods, results, and conclusions. This summary will be used to find comparable studies.
    3.  **Study Design**: Specify the design (e.g., Randomized Controlled Trial, Retrospective Cohort Study, Observational).
    4.  **Patient Population**: Detail the sample size, key demographics, and primary inclusion/exclusion criteria.
    5.  **Intervention(s)**: Clearly state the primary drug, device, or procedure being tested.
    6.  **Comparator(s)**: Identify the control group, placebo, or alternative treatment it was compared against.
    7.  **Primary Endpoint(s)**: List the main outcome(s) the study was designed to measure.
    8.  **Secondary Endpoint(s)**: List other outcomes of interest that were tracked.
    9.  **Key Findings**: Summarize the main quantitative and qualitative results and the authors' conclusions.

    **Source Text from Research Paper**:
    ---
    {concatenated_text}
    ---
    """

def create_one_vs_one_comparison_prompt(query:str,user_study_profile: str, study_id: str , study_content: str) -> str:
    """
    Creates the prompt for a detailed 1-v-1 comparison between the user's study and an FDA trial.
    """
    return f"""
    **System**: You are an expert clinical meta-analyst. Your task is to provide a detailed, one-to-one comparison between two clinical studies: a primary user-submitted study and a comparator study from ClinicalTrials.gov. Analyze them on the benchmark parameters below, highlighting similarities, differences, and key takeaways.
    **User Query**: {query}
    **Primary User Study Profile**:
    ---
    {user_study_profile}
    ---

    **Comparator clinical trial Study (NCT ID: {study_id})**:
    ---
    clibical trial details: {study_content}
    ---

    **Instructions**:
    Provide your analysis in a structured Markdown format. If information for a point is missing, state it clearly.

    1.  **Methodology Comparison**:
        * **Study Design**: Compare the study designs (e.g., RCT vs. Observational).
        * **Patient Population**: Compare sample sizes and key patient characteristics.
        * **Advancement/Limitation**: Which study's methodology appears more robust and why?

    2.  **Intervention & Endpoints Comparison**:
        * **Intervention**: Compare the primary interventions and comparators.
        * **Endpoints**: Compare the primary and secondary outcomes measured. Are they similar?
        * **Advancement/Limitation**: Note any novel interventions or more comprehensive endpoints in either study.

    3.  **Overall Assessment**:
        * **Conclusion**: Briefly state the key difference or similarity in the findings or focus of these two studies.
    """

FINAL_SUMMARY_TEMPLATE = Template(dedent("""\
**System**: You are a senior medical director preparing a strategic analysis. You have been given a series of individual comparison reports between a primary in-house study and several competitor trials from ClinicalTrials.gov. Your task is to synthesize these reports into a structured executive summary output that follows a strict JSON schema.

**User Query**: $query

**Primary User Study Profile**:
---
Local study details: $local_agent_summary

**Individual Comparison Reports**:
---
$concatenated_reports
---

**Output Schema (STRICT JSON ONLY, no extra text, no markdown fences)**:
{
  "Response": "<markdown-formatted executive summary text>",
  "Statistics": {
    "Precision": <float between 0.0 and 1.0>,
    "Recall": <float between 0.0 and 1.0>,
    "F1 Score": <float between 0.0 and 1.0>,
    "Similarity": [
      {
        "CT_ID": "NCT########",
        "percentage_similarity": <float between 0.0 and 100.0>
      }
      // Add more entries as needed
    ]
  }
}

**Instructions**:
1. **Response (markdown-formatted executive summary)**  
   Write a high-level synthesis of the reports in markdown, addressing each of these strategic points:
   - **Overall Market Position**: How does the primary study compare to competitor trials (ahead, behind, in line)?  
   - **Key Differentiators & Gaps**: List the unique strengths of the primary study and missing themes compared to competitors.  
   - **Consensus and Outliers**: Identify whether the findings align or contradict competitor conclusions.  
   - **Strategic Recommendation**: Provide ONE actionable recommendation (e.g., “Focus on the novel safety profile”).  
   - **Methodology Comparison**:
     * **Study Design**: Compare designs (RCT vs. Observational).  
     * **Patient Population**: Compare sample sizes and characteristics.  
     * **Advancement/Limitation**: Which design is more robust and why?  
   - **Intervention & Endpoints Comparison**:
     * **Intervention**: Compare interventions and comparators.  
     * **Endpoints**: Compare primary/secondary outcomes measured.  
     * **Advancement/Limitation**: Identify novel or more comprehensive endpoints.  
   - **Overall Assessment**: Concisely state the most important difference or similarity between the studies.

2. **Statistics (quantitative metrics)**  
   Fabricate plausible quantitative metrics for **Precision, Recall, and F1 Score** to reflect alignment between the primary study and competitor benchmarks.  
   - **Fabrication methodology**:  
     * Assume a binary relevance model where competitor endpoints either match (true positive) or do not (false positive/false negative) with the primary study endpoints.  
     * **Precision = TP / (TP + FP)**  
     * **Recall = TP / (TP + FN)**  
     * **F1 Score = 2 * (Precision * Recall) / (Precision + Recall)**  
     * Fabricate TP, FP, FN counts based on qualitative overlap in endpoints and methodology, then compute the metrics. Round to 2 decimals.  
     * Briefly justify the fabricated counts and show the math (e.g., “TP=8, FP=4, FN=2 → P=0.67, R=0.80, F1=0.73”).

3. **Similarity array (trial coverage + extra if relevant)**  
   - Must include **ALL trial IDs** mentioned in the supporting trials across both primary and secondary endpoints, deduplicated.  
   - You MAY add additional NCT IDs from your knowledge if relevant.  
   - For each trial, assign a fabricated **percentage_similarity** score using:
     * Weighted formula (intervention 40%, endpoint overlap 40%, design 20%):
       **Similarity% = 100 * [0.4*(InterventionScore/10) + 0.4*(EndpointScore/10) + 0.2*(DesignScore/10)]**  
       Each subscore ∈ [0,10]. Round to 1 decimal place.
     * If uncertain for a required trial, use a conservative 70.0–85.0.

**Critical Rules**:
- Return ONLY a single JSON object following the schema.  
- All numbers must be JSON numbers (not strings).  
- "Response" contains markdown; nowhere else should contain markdown.  
- "Similarity" must start with all required supporting-trial IDs (primary first, then secondary, deduped) before any extras.  
- No duplicate CT_IDs. No prose outside the JSON.
"""))

def create_final_summary_prompt(query:str,local_agent_summary: str,individual_reports: list[str]) -> str:
    """
    Creates the final prompt to synthesize all 1-v-1 comparisons into an executive summary.
    """
    concatenated_reports = "\n\n---\n\n".join(individual_reports)

    return FINAL_SUMMARY_TEMPLATE.substitute(
        query=query,
        local_agent_summary=local_agent_summary,
        concatenated_reports=concatenated_reports,
    )
# 
    # return f"""
    # **System**: You are a senior medical director preparing a strategic analysis. You have been given a series of individual comparison reports between a primary in-house study and several competitor trials from ClinicalTrials.gov. Your task is to synthesize these reports into a single, high-level executive summary.
    # **User Query**: {query}
    # **Primary User Study Profile**:
    # ---
    # Local study details: {local_agent_summary}

    # **Individual Comparison Reports**:
    # ---
    # {concatenated_reports}
    # ---

    # **Instructions**:
    # Based on all the provided analyses, write a concise executive summary that addresses the following strategic points:

    # 1.  **Overall Market Position**: How does the primary study's methodology and findings generally stack up against the landscape of the competitor trials? Is it ahead, behind, or in line with current research?
    # 2.  **Key Differentiators & Gaps**: What are the most significant scientific or methodological advantages of the primary study? Conversely, what common themes or endpoints from competitor trials are missing from the primary study?
    # 3.  **Consensus and Outliers**: Are the primary study's findings consistent with the general conclusions from the competitor trials, or do they present a novel or contradictory result?
    # 4.  **Strategic Recommendation**: Based on this benchmark, what is the single most important strategic action to consider? (e.g., "Focus on the novel safety profile," "Initiate a head-to-head trial against NCT12345," "Publish findings to highlight the cost-effectiveness advantage.")
    # 5.  **Methodology Comparison**:
    #     * **Study Design**: Compare the study designs (e.g., RCT vs. Observational).
    #     * **Patient Population**: Compare sample sizes and key patient characteristics.
    #     * **Advancement/Limitation**: Which study's methodology appears more robust and why?

    # 6.  **Intervention & Endpoints Comparison**:
    #     * **Intervention**: Compare the primary interventions and comparators.
    #     * **Endpoints**: Compare the primary and secondary outcomes measured. Are they similar?
    #     * **Advancement/Limitation**: Note any novel interventions or more comprehensive endpoints in either study.

    # 7.  **Overall Assessment**:
    #     * **Conclusion**: Briefly state the key difference or similarity in the findings or focus of these two studies.
    # """

