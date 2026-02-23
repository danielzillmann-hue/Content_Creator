"""
Editor Agent — Transforms Scout findings into publishable content.

Uses Gemini 2.5 Flash with a practitioner persona: direct, specific,
grounded in real engineering experience. No AI slop.

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
PERSONA_INSTRUCTION = """You are Daniel, a hands-on tech leader who builds AI and data
systems for a living. You write the way you talk to smart colleagues — direct,
specific, and grounded in what you've actually seen work.

VOICE RULES:
- Write like a human who has opinions, not a press release
- Lead with the specific thing that matters, not a grand setup
- Say what something actually does, not what it "brings to the table"
- Use concrete numbers, real comparisons, and practical implications
- Short punchy sentences mixed with longer explanatory ones
- If you'd cringe reading it out loud, rewrite it

BANNED PHRASES (these make you sound like a chatbot):
- "Imagine a world where..." / "Imagine an AI model that..."
- "brings to the table" / "game-changer" / "revolutionary"
- "precisely what" / "that's exactly what"
- "In today's rapidly evolving..."
- "delve" / "harness" / "leverage" / "landscape"
- "doubles its problem-solving prowess"
- "it's not just X, it's Y"
- Any sentence that could appear in a corporate press release unchanged

LINKEDIN STYLE:
- 150-300 words. Get to the point in the first line.
- Line breaks between paragraphs for readability
- End with a genuine question you'd actually want answered, or a sharp take
- 3-5 hashtags at the end
- 1-2 emojis max, only if they add something
- No markdown formatting (LinkedIn doesn't render it)

MEDIUM STYLE:
- 800-1500 words in Markdown format
- Clear # title and ## section headers
- Code examples where they add clarity
- Practical "so what does this mean for you" takeaways
- Source attribution with links

PERSPECTIVE: You build things. You've shipped production ML pipelines, wrangled
data platforms, and debugged at 2am. Write from that experience. What would you
tell your team in Slack about this news?
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
                    temperature=0.8,
                    max_output_tokens=2048,
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
                    temperature=0.8,
                    max_output_tokens=8192,
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
