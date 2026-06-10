from employment_scheduler.analysis.models import JobPostAnalysisTarget


def build_analysis_prompt(target: JobPostAnalysisTarget) -> str:
    return f"""\
You are analyzing one employment application page collected by the local employment-scheduler pipeline.

Open and inspect the apply URL when web access is available. If the page is unavailable, blocked, dynamic, or not directly inspectable, state that clearly and do not invent details.

Return a Korean Markdown report with these sections:

1. 기본 정보
2. 회사 및 포지션 추정
3. 주요 업무
4. 자격 요건
5. 우대 사항 및 기술 키워드
6. 지원 판단 메모
7. 확인 불가 또는 리스크

Keep the report concise but evidence-based. Include the source URL and any uncertainty.

Collected job post metadata:

- job_posts.id: {target.job_post_id}
- source: {target.source_key}
- external_id: {target.external_id}
- apply_url: {target.apply_url}
- first_seen_at: {target.first_seen_at}
- last_seen_at: {target.last_seen_at}
"""
