"""
Editor Agent — Transforms Scout findings into publishable content.

Uses Gemini 2.0 Pro for higher quality writing with a specific persona:
professional, slightly witty, tech-savvy.

Produces both LinkedIn posts (short-form) and Medium articles (long-form).

Usage:
    editor = EditorAgent()
    output = editor.write(scout_report)
    print(output.linkedin_draft.content)
    print(output.medium_draft.content_markdown)
"""
import logging

from google import genai
from google.genai.types import GenerateContentConfig, HttpOptions

from config.settings import settings
from models.schemas import (
    EditorOutput,
    LinkedInDraft,
    MediumDraft,
    ScoutReport,
)

logger = logging.getLogger(__name__)

# Persona system instruction — kept as a module constant for easy tuning.
PERSONA_INSTRUCTION = """You are a senior technology writer with the following voice:

TONE: Professional but approachable. You explain complex tech concepts clearly
without being condescending. You use light wit — a well-placed observation or
clever phrasing — but never forced jokes or puns.

STYLE:
- LinkedIn posts: 150-300 words. Hook in the first line. Use line breaks for
  readability. End with a thought-provoking question or call to action.
  Include 3-5 relevant hashtags at the end.
- Medium articles: 800-1500 words. Clear sections with headers. Code examples
  where relevant. Practical takeaways. Written in Markdown format.

PERSPECTIVE: You are a practitioner who builds things, not just a commentator.
Reference real-world implications. Think "what does this mean for engineers
and product teams?"

DO NOT:
- Use clickbait or sensationalist language
- Start with "In today's rapidly evolving..."
- Use excessive emojis (1-2 max per LinkedIn post)
- Include disclaimers about being AI
- Use the word "delve"
"""


class EditorAgent:
    """Transforms Scout output into polished LinkedIn posts and Medium articles."""

    def __init__(self) -> None:
        self.client = genai.Client(
            vertexai=True,
            project=settings.GCP_PROJECT,
            location=settings.GCP_REGION,
            http_options=HttpOptions(api_version="v1"),
        )
        self.model = settings.EDITOR_MODEL

    def write(self, scout_report: ScoutReport) -> EditorOutput:
        """
        Generate LinkedIn post and Medium article from Scout findings.

        Args:
            scout_report: The ScoutReport containing discovered news items.

        Returns:
            EditorOutput with LinkedIn and Medium drafts.
        """
        findings_text = self._format_findings(scout_report)

        linkedin_draft = self._write_linkedin_post(findings_text, scout_report)
        medium_draft = self._write_medium_article(findings_text, scout_report)

        return EditorOutput(
            scout_report_id=str(scout_report.generated_at.isoformat()),
            linkedin_draft=linkedin_draft,
            medium_draft=medium_draft,
        )

    def _write_linkedin_post(
        self, findings: str, report: ScoutReport
    ) -> LinkedInDraft:
        """Generate a LinkedIn post draft."""
        prompt = f"""Based on these trending AI/tech news findings, write a LinkedIn post.

FINDINGS:
{findings}

REQUIREMENTS:
- Pick the single most compelling story or combine 2-3 into a theme
- Hook in the first line (pattern-interrupt or surprising stat)
- 150-300 words
- End with a question or call to action
- Include 3-5 hashtags
- Cite sources where relevant
- Format for LinkedIn (line breaks between paragraphs, no markdown)
"""

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=GenerateContentConfig(
                    system_instruction=PERSONA_INSTRUCTION,
                    temperature=0.7,
                    max_output_tokens=1024,
                ),
            )
            return LinkedInDraft(
                content=response.text,
                source_items=[item.headline for item in report.items],
            )
        except Exception as e:
            logger.error(f"LinkedIn draft generation failed: {e}", exc_info=True)
            raise

    def _write_medium_article(
        self, findings: str, report: ScoutReport
    ) -> MediumDraft:
        """Generate a Medium article draft in Markdown."""
        prompt = f"""Based on these trending AI/tech news findings, write a Medium article.

FINDINGS:
{findings}

REQUIREMENTS:
- Markdown format
- 800-1500 words
- Clear title as a # heading on the first line
- 3-4 sections with ## headers
- Practical takeaways for engineers/product teams
- Include source attribution with links
- End with a summary and forward-looking thought
"""

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=GenerateContentConfig(
                    system_instruction=PERSONA_INSTRUCTION,
                    temperature=0.7,
                    max_output_tokens=4096,
                ),
            )
            text = response.text
            title = self._extract_title(text)

            return MediumDraft(
                title=title,
                content_markdown=text,
                tags=report.topics[:5],
                source_items=[item.headline for item in report.items],
            )
        except Exception as e:
            logger.error(f"Medium draft generation failed: {e}", exc_info=True)
            raise

    def _format_findings(self, report: ScoutReport) -> str:
        """Format ScoutReport items into a text block for the editor prompt."""
        parts = []
        for i, item in enumerate(report.items, 1):
            parts.append(
                f"Story {i}: {item.headline}\n"
                f"Summary: {item.summary}\n"
                f"Source: {item.source_url}\n"
                f"LinkedIn angle: {item.linkedin_angle}\n"
                f"Tags: {', '.join(item.topic_tags)}"
            )
        return "\n\n---\n\n".join(parts)

    def _extract_title(self, text: str) -> str:
        """Extract title from the first markdown heading."""
        for line in text.strip().split("\n"):
            stripped = line.strip()
            if stripped.startswith("# ") and not stripped.startswith("## "):
                return stripped.lstrip("# ").strip()
        return "AI/Tech Weekly Roundup"
