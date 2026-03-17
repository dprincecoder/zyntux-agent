from __future__ import annotations

import asyncio
import re
from typing import Any, Final

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.email_service import EmailServiceError, is_valid_email, send_raw_evaluation_email
from app.public_evaluator import build_public_goods_evaluation
from app.twitter_scraper import TwitterScraperError, fetch_user_bio

STATE_KEY: Final[str] = "state"
EVAL_DATA_KEY: Final[str] = "current_evaluation"

STATE_AWAIT_X_HANDLE: Final[str] = "await_x_handle"
STATE_AWAIT_USER_FEEDBACK: Final[str] = "await_user_feedback"
STATE_AWAIT_GITHUB_REPO: Final[str] = "await_github_repo"
STATE_EVALUATION_COMPLETE: Final[str] = "evaluation_complete"
STATE_AWAIT_RAW_EMAIL_OPT_IN: Final[str] = "await_raw_email_opt_in"
STATE_AWAIT_RAW_EMAIL_ADDRESS: Final[str] = "await_raw_email_address"

SKIP_TOKENS = {"skip", "no", "next", "i don't have anything to say", "i dont have anything to say"}


def _set_state(context: ContextTypes.DEFAULT_TYPE, state: str | None) -> None:
    if state is None:
        context.chat_data.pop(STATE_KEY, None)
    else:
        context.chat_data[STATE_KEY] = state


def _normalize_email(text: str) -> str:
    return re.sub(r"\s+", "", text).strip()


async def _send(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
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

    await update.message.reply_text(text)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _set_state(context, None)
    context.chat_data.pop(EVAL_DATA_KEY, None)

    message = (
        "Hello, I am ZynthClaw.\n\n"
        "I am a Public Goods Evaluation Agent. I guide you through:\n"
        "- Collecting community sentiment (via X handle),\n"
        "- Capturing your direct human-impact story,\n"
        "- Optionally checking GitHub developer activity,\n"
        "- Producing an impact evaluation and mechanism design insight.\n\n"
        "Commands:\n"
        "/evaluate_project - start a new project evaluation\n"
        "/request_raw_data - email the raw collated data from your last evaluation\n"
    )
    await _send(update, context, message)


async def evaluate_project_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _set_state(context, STATE_AWAIT_X_HANDLE)
    context.chat_data[EVAL_DATA_KEY] = {}
    await _send(
        update,
        context,
        "Great. Let's start.\n\nPlease send me the project's X (Twitter) handle (e.g. @project).",
    )


async def request_raw_data_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    evaluation = context.chat_data.get(EVAL_DATA_KEY)
    if not evaluation or "created_at" not in evaluation:
        await _send(
            update,
            context,
            "I don't have a completed evaluation yet. Run /evaluate_project first.",
        )
        return

    _set_state(context, STATE_AWAIT_RAW_EMAIL_ADDRESS)
    await _send(update, context, "Send me the email address where I should send the raw evaluation PDF.")


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

    await _send(update, context, "Thanks. Let me analyze everything and prepare an evaluation report...")

    def _evaluate() -> dict[str, Any]:
        return build_public_goods_evaluation(x_handle=x_handle, user_feedback=user_feedback, repo_url=repo_url)

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
    lines.append("4) Overall impact classification")
    lines.append(evaluation.get("impact_classification", "N/A"))
    lines.append("")
    lines.append("5) Mechanism design insight")
    lines.append(evaluation.get("mechanism_design_recommendation", ""))

    await _send(update, context, "\n".join(lines).strip())

    # Schedule follow-up asking about emailing raw collated data
    chat = update.effective_chat
    if not chat:
        return

    async def _delayed_followup(chat_id: int) -> None:
        await asyncio.sleep(60)
        eval_data = context.chat_data.get(EVAL_DATA_KEY)
        if not eval_data:
            return
        _set_state(context, STATE_AWAIT_RAW_EMAIL_OPT_IN)
        await context.bot.send_message(
            chat_id=chat_id,
            text="If you want, I can email you the raw collated data for manual review. Yes?",
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
                f"Great, project found: @{handle}\n\nAccording to X, this is how the project describes itself:\n{bio}",
            )
        else:
            await _send(
                update,
                context,
                f"Great, project found: @{handle}",
            )

        _set_state(context, STATE_AWAIT_USER_FEEDBACK)
        await _send(
            update,
            context,
            (
                "How has this project impacted your workflow, business, or people around you?\n"
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
                "If you can, please send the project's GitHub repository URL for a deeper evaluation.\n"
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
        await _run_evaluation_and_reply(update, context)
        return

    if state == STATE_AWAIT_RAW_EMAIL_OPT_IN:
        lowered = text.lower()
        if lowered in {"yes", "y", "yeah", "yep"}:
            _set_state(context, STATE_AWAIT_RAW_EMAIL_ADDRESS)
            await _send(update, context, "Great. Please send the email address to receive the raw evaluation PDF.")
            return
        if lowered in {"no", "n", "nope"}:
            _set_state(context, STATE_EVALUATION_COMPLETE)
            await _send(update, context, "Alright, I won't email the raw data. Evaluation completed.")
            return
        await _send(update, context, "Please reply with \"Yes\" or \"No\".")
        return

    if state == STATE_AWAIT_RAW_EMAIL_ADDRESS:
        email = _normalize_email(text)
        if not is_valid_email(email):
            await _send(update, context, "Please send a valid email address.")
            return

        evaluation = context.chat_data.get(EVAL_DATA_KEY)
        if not evaluation:
            await _send(update, context, "I no longer have the evaluation data. Please run /evaluate_project again.")
            _set_state(context, None)
            return

        await _send(update, context, "Preparing the PDF and sending the raw evaluation data to your email...")

        try:
            await asyncio.to_thread(send_raw_evaluation_email, email, evaluation)
            await _send(update, context, f"Email sent to {email}. Also check your spam folder.")
            _set_state(context, STATE_EVALUATION_COMPLETE)
        except EmailServiceError as exc:
            await _send(update, context, str(exc))
        except Exception as exc:
            await _send(update, context, f"Error while sending email: {exc}")
        return

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
    application.add_handler(CommandHandler("request_raw_data", request_raw_data_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))

    return application

