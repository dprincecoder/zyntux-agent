from __future__ import annotations

import asyncio
import html
import io
import re
from typing import Any, Final

from telegram import InputFile, Update
from telegram.constants import ParseMode
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.email_service import generate_raw_evaluation_pdf
from app.public_evaluator import build_public_goods_evaluation
from app.twitter_scraper import TwitterScraperError, fetch_user_bio, fetch_user_posts_with_replies

STATE_KEY: Final[str] = "state"
EVAL_DATA_KEY: Final[str] = "current_evaluation"

STATE_AWAIT_X_HANDLE: Final[str] = "await_x_handle"
STATE_AWAIT_USER_FEEDBACK: Final[str] = "await_user_feedback"
STATE_AWAIT_GITHUB_REPO: Final[str] = "await_github_repo"
STATE_AWAIT_ADDITIONAL_INFO_OPT_IN: Final[str] = "await_additional_info_opt_in"
STATE_AWAIT_ADDITIONAL_INFO_TEXT: Final[str] = "await_additional_info_text"
STATE_AWAIT_GOVERNANCE_DESCRIPTION: Final[str] = "await_governance_description"
STATE_AWAIT_GOVERNANCE_ARTIFACTS: Final[str] = "await_governance_artifacts"
STATE_EVALUATION_COMPLETE: Final[str] = "evaluation_complete"
# Email flow disabled — use /export for PDF instead
# STATE_AWAIT_RAW_EMAIL_OPT_IN: Final[str] = "await_raw_email_opt_in"
# STATE_AWAIT_RAW_EMAIL_ADDRESS: Final[str] = "await_raw_email_address"

SKIP_TOKENS = {"skip", "no", "next", "i don't have anything to say", "i dont have anything to say"}

GOVERNANCE_Q1 = (
    "If you don't mind, what are the governance activities for this project?\n"
    "You can describe things like:\n"
    "- how decisions are made\n"
    "- who participates (team vs community)\n"
    "- how voting works (if any)\n"
    "- how frequently governance is conducted\n\n"
    "Explain in your own words."
)

GOVERNANCE_Q2 = (
    "Do you have any links or artifacts related to the governance process?\n"
    "For example:\n"
    "- DAO / Snapshot page\n"
    "- governance forum\n"
    "- recent proposals or votes\n"
    "- any public discussion around decisions\n\n"
    "You can drop links or just describe them."
)


async def _send_analysing_social_and_dev(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await _send(update, context, "Analysing social activity")
    await asyncio.sleep(0.45)
    await _send(update, context, "Analysing developer activity")
    await asyncio.sleep(0.35)


async def _send_analysing_social_dev_and_governance(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await _send(update, context, "Analysing social activity")
    await asyncio.sleep(0.45)
    await _send(update, context, "Analysing developer activity")
    await asyncio.sleep(0.45)
    await _send(update, context, "Analysing governance activity")
    await asyncio.sleep(0.35)


async def _begin_governance_phase(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """After optional info: status lines, then governance Q1."""
    await _send_analysing_social_and_dev(update, context)
    _set_state(context, STATE_AWAIT_GOVERNANCE_DESCRIPTION)
    await _send(update, context, GOVERNANCE_Q1)


def _set_state(context: ContextTypes.DEFAULT_TYPE, state: str | None) -> None:
    if state is None:
        context.chat_data.pop(STATE_KEY, None)
    else:
        context.chat_data[STATE_KEY] = state


async def _send(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    *,
    parse_mode: str | None = None,
    disable_web_page_preview: bool = True,
) -> None:
    """Send a message with a short 'typing' effect first."""
    chat = update.effective_chat
    if not chat or not update.message:
        return

    # Simulate typing based on length, but keep it snappy.
    approx_seconds = min(max(len(text) / 60.0, 0.5), 3.0)
    try:
        await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)
    except Exception:
        approx_seconds = 0.0

    if approx_seconds > 0:
        await asyncio.sleep(approx_seconds)

    await update.message.reply_text(
        text,
        parse_mode=parse_mode,
        disable_web_page_preview=disable_web_page_preview,
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _set_state(context, None)
    context.chat_data.pop(EVAL_DATA_KEY, None)

    message = (
        "Hello, I am ZynthClaw.\n\n"
        "I am a Public Goods Data Collector Agent. I guide you through:\n"
        "- Collecting community sentiment typically via X (formerly Twitter),\n"
        "- Capturing your direct human-impact story,\n"
        "- Optionally, I also collect GitHub developer activity,\n"
        "- Optionally capturing governance signals,\n"
        "- Therefore producing an impact evaluation and mechanism design insight.\n\n"
        "<i>i plan to plug this collected data into a large LLM for better evaluation, mechanism design, and analysis. (still in beta)</i>\n\n"
        "Commands:\n"
        "/evaluate_project - start a new project collection\n"
        "/export - download the raw collated data as a PDF (after a completed evaluation)\n"
    )
    await _send(update, context, message, parse_mode=ParseMode.HTML)


async def evaluate_project_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _set_state(context, STATE_AWAIT_X_HANDLE)
    context.chat_data[EVAL_DATA_KEY] = {}
    await _send(
        update,
        context,
        "Great. Let's start.\n\nPlease send me the project's X (Twitter) handle (e.g. @project).",
    )


async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send raw evaluation PDF in Telegram (no email)."""
    evaluation = context.chat_data.get(EVAL_DATA_KEY)
    if not evaluation or "created_at" not in evaluation:
        await _send(
            update,
            context,
            "I don't have a completed evaluation yet. Run /evaluate_project first.",
        )
        return

    if not update.message:
        return

    await _send(update, context, "Preparing your PDF…")

    def _pdf() -> bytes:
        return generate_raw_evaluation_pdf(evaluation)

    try:
        pdf_bytes = await asyncio.to_thread(_pdf)
    except Exception as exc:
        await _send(update, context, f"Could not build the PDF: {exc}")
        return

    buf = io.BytesIO(pdf_bytes)
    buf.seek(0)
    await update.message.reply_document(
        document=InputFile(buf, filename="zynthclaw_public_goods_raw_evaluation.pdf"),
        caption="ZynthClaw — raw public goods evaluation data (PDF).",
    )


def _is_skip_feedback(text: str) -> bool:
    lowered = text.strip().lower()
    if lowered in SKIP_TOKENS:
        return True
    words = lowered.split()
    return len(words) < 20


async def _run_evaluation_and_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    data: dict[str, Any] = context.chat_data.get(EVAL_DATA_KEY) or {}
    x_handle = data.get("x_handle", "")
    user_feedback = data.get("user_feedback", "")
    repo_url = data.get("github_repo_url")
    optional_user_info = data.get("optional_user_info")
    governance_description = data.get("governance_description")
    governance_artifacts = data.get("governance_artifacts")

    await _send(update, context, "Building your Impact Evaluation Report…")

    def _evaluate() -> dict[str, Any]:
        return build_public_goods_evaluation(
            x_handle=x_handle,
            user_feedback=user_feedback,
            repo_url=repo_url,
            optional_user_info=optional_user_info,
            governance_description=governance_description,
            governance_artifacts=governance_artifacts,
        )

    try:
        evaluation = await asyncio.to_thread(_evaluate)
    except Exception as exc:
        await _send(update, context, f"Something went wrong while evaluating this project: {exc}")
        return

    context.chat_data[EVAL_DATA_KEY] = evaluation
    _set_state(context, STATE_EVALUATION_COMPLETE)

    lines: list[str] = []
    lines.append(f"Impact Evaluation Report for @{evaluation.get('x_handle', 'unknown')}")
    lines.append("")
    lines.append("1) Community sentiment (X)")
    lines.append(evaluation.get("community_sentiment_summary", "No X analysis is available yet."))
    lines.append("")
    lines.append("2) Real user impact (your feedback)")
    lines.append(evaluation.get("user_feedback", "No feedback captured."))
    lines.append("")
    if evaluation.get("github_repo_url"):
        lines.append("3) Developer activity (GitHub)")
        if evaluation.get("github_summary"):
            lines.append(evaluation.get("github_summary", "No GitHub summary available."))
        else:
            lines.append(
                evaluation.get(
                    "github_error",
                    "GitHub repository could not be analyzed; developer signals were not included.",
                )
            )
        lines.append("")
    else:
        lines.append("3) Developer activity (GitHub)")
        lines.append("No GitHub repository was provided, so developer signals were not included.")
        lines.append("")
    lines.append("4) Governance (your input)")
    if evaluation.get("governance_summary"):
        lines.append(evaluation.get("governance_summary", ""))
    elif evaluation.get("governance_description") or evaluation.get("governance_artifacts"):
        if evaluation.get("governance_description"):
            lines.append(evaluation.get("governance_description", ""))
        if evaluation.get("governance_artifacts"):
            lines.append("")
            lines.append("Links / artifacts:")
            lines.append(evaluation.get("governance_artifacts", ""))
    else:
        lines.append("No governance description captured.")
    lines.append("")
    lines.append("5) Overall impact classification")
    lines.append(evaluation.get("impact_classification", "N/A"))
    lines.append("")
    lines.append("6) Mechanism design insight")
    lines.append(evaluation.get("mechanism_design_recommendation", ""))

    await _send(update, context, "\n".join(lines).strip())

    # Schedule follow-up: offer PDF export (Telegram /export or HTTP POST /export for agents)
    chat = update.effective_chat
    if not chat:
        return

    async def _delayed_followup(chat_id: int) -> None:
        await asyncio.sleep(60)
        eval_data = context.chat_data.get(EVAL_DATA_KEY)
        if not eval_data:
            return
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "If you want, I can export the raw collated data (including governance) as a PDF.\n"
                "Send /export here in Telegram when you're ready.\n\n"
            ),
        )

    asyncio.create_task(_delayed_followup(chat.id))


async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    state = context.chat_data.get(STATE_KEY)
    data: dict[str, Any] = context.chat_data.get(EVAL_DATA_KEY) or {}

    if state == STATE_AWAIT_X_HANDLE:
        handle = text.lstrip("@").strip()
        if not handle:
            await _send(update, context, "Please send a valid X handle (e.g. @project).")
            return

        data["x_handle"] = handle
        context.chat_data[EVAL_DATA_KEY] = data

        await _send(
            update,
            context,
            "Checking X (formerly Twitter) for project handle, please wait…",
        )

        # Try to fetch and show the project's X bio before asking for feedback.
        bio: str | None = None
        try:
            bio = await asyncio.to_thread(fetch_user_bio, handle)
        except TwitterScraperError as exc:
            print(f"[Bot] TwitterScraperError while fetching bio for @{handle}: {exc}")
        except Exception as exc:
            print(f"[Bot] Unexpected error while fetching bio for @{handle}: {exc}")

        if bio:
            await _send(
                update,
                context,
                f"Great, project found: @{handle}\n\nAccording to X, @{handle} is:\n{bio}",
            )
        else:
            await _send(
                update,
                context,
                f"Great, project found: @{handle}",
            )

        # Show a small preview of raw X posts + replies (limit 3) in-chat.
        try:
            preview_threads = await asyncio.to_thread(
                fetch_user_posts_with_replies,
                handle,
                3,
                10,
            )
            if preview_threads:
                parts: list[str] = []
                parts.append(f"<b>Recent X posts from @{handle}</b>")
                for idx, th in enumerate(preview_threads, start=1):
                    post_text = (th.post.text or "").strip()
                    post_one_line = " ".join(post_text.split())
                    parts.append("")
                    parts.append(f"<b>Post {idx}</b>")
                    parts.append(f"<blockquote>{html.escape(post_one_line[:800])}{'…' if len(post_one_line) > 800 else ''}</blockquote>")
                    if th.replies:
                        parts.append("<b>What others are saying</b>")
                        for r in th.replies[:10]:
                            author = (r.author_username or "user").lstrip("@")
                            txt = " ".join((r.text or "").strip().split())
                            parts.append(
                                f"<blockquote><b>@{html.escape(author)}</b>\n{html.escape(txt[:800])}{'…' if len(txt) > 800 else ''}</blockquote>"
                            )
                    else:
                        parts.append("<blockquote><i>No replies captured (or all were filtered).</i></blockquote>")

                parts.append("")
                parts.append(
                    "To get the full raw data (up to 10 posts + replies) as a PDF, finish the evaluation and send <b>/export</b>."
                )
                await _send(update, context, "\n".join(parts), parse_mode=ParseMode.HTML)
        except TwitterScraperError as exc:
            print(f"[Bot] TwitterScraperError while building X preview for @{handle}: {exc}")
        except Exception as exc:
            print(f"[Bot] Unexpected error while building X preview for @{handle}: {exc}")

        _set_state(context, STATE_AWAIT_USER_FEEDBACK)
        await _send(
            update,
            context,
            (
                "Moving forward, tell me how has this project impacted your workflow, business, or people around you?\n"
                "Please explain in detail (at least 20 words). You can use bullet points if you like."
            ),
        )
        return

    if state == STATE_AWAIT_USER_FEEDBACK:
        if _is_skip_feedback(text):
            await _send(
                update,
                context,
                "I need to understand how this project has impacted you to be able to proceed.",
            )
            return
        data["user_feedback"] = text
        context.chat_data[EVAL_DATA_KEY] = data
        _set_state(context, STATE_AWAIT_GITHUB_REPO)
        await _send(
            update,
            context,
            (
                "To gain even deeper understanding, please send the project's GitHub repository URL for evaluation.\n"
                "If you don't have it or want to skip, just reply \"skip\"."
            ),
        )
        return

    if state == STATE_AWAIT_GITHUB_REPO:
        lowered = text.lower()
        if lowered in SKIP_TOKENS:
            handle = (data.get("x_handle") or "").lstrip("@")
            handle_display = f"@{handle}" if handle else "this project"
            await _send(
                update,
                context,
                (
                    f"I strongly recommend you send me the {handle_display} repo as this will help in my "
                    "evaluation and mechanism design.\n\nSince you chose to skip, I will continue with the "
                    "information I have."
                ),
            )
            data["github_repo_url"] = None
        else:
            data["github_repo_url"] = text.strip()
        context.chat_data[EVAL_DATA_KEY] = data
        _set_state(context, STATE_AWAIT_ADDITIONAL_INFO_OPT_IN)
        await _send(
            update,
            context,
            (
                "Optionally, would you like to add any additional information to strengthen this analysis?\n"
                "For example: a link to an article, docs, a blog post, or any context you think matters.\n\n"
                "Reply \"Yes\" to add more info, or \"No\" to proceed."
            ),
        )
        return

    if state == STATE_AWAIT_ADDITIONAL_INFO_OPT_IN:
        lowered = text.lower()
        if lowered in {"no", "n", "nope", "nah", "skip", "i don't have anything to add", "I don't care"}:
            data["optional_user_info"] = None
            context.chat_data[EVAL_DATA_KEY] = data
            await _begin_governance_phase(update, context)
            return
        if lowered in {"yes", "y", "yeah", "yep", "yes please", "great!", "okay", "sure", "alright", "ok"}:
            _set_state(context, STATE_AWAIT_ADDITIONAL_INFO_TEXT)
            await _send(
                update,
                context,
                "Great — please drop the additional info (links + any notes).",
            )
            return
        await _send(update, context, "Please reply with \"Yes\" or \"No\".")
        return

    if state == STATE_AWAIT_ADDITIONAL_INFO_TEXT:
        data["optional_user_info"] = text.strip()
        context.chat_data[EVAL_DATA_KEY] = data
        await _begin_governance_phase(update, context)
        return

    if state == STATE_AWAIT_GOVERNANCE_DESCRIPTION:
        data["governance_description"] = text.strip()
        context.chat_data[EVAL_DATA_KEY] = data
        _set_state(context, STATE_AWAIT_GOVERNANCE_ARTIFACTS)
        await _send(update, context, GOVERNANCE_Q2)
        return

    if state == STATE_AWAIT_GOVERNANCE_ARTIFACTS:
        data["governance_artifacts"] = text.strip()
        context.chat_data[EVAL_DATA_KEY] = data
        await _send_analysing_social_dev_and_governance(update, context)
        await _run_evaluation_and_reply(update, context)
        return

    # --- Email flow disabled (see /export) ---
    # if state == STATE_AWAIT_RAW_EMAIL_OPT_IN: ...
    # if state == STATE_AWAIT_RAW_EMAIL_ADDRESS: ...

    # If we reach here there is no active stateful flow; encourage starting one.
    await _send(
        update,
        context,
        "If you want to run a new evaluation, use /evaluate_project.",
    )


def build_application(token: str) -> Application:
    """
    Build and return the python-telegram-bot Application with all handlers
    registered. This is used by the main entrypoint to start polling.
    """
    application = ApplicationBuilder().token(token).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("evaluate_project", evaluate_project_command))
    application.add_handler(CommandHandler("export", export_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))

    return application
