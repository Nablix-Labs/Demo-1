"""End-to-end run: topic documents in, workbook out.

Every module has its own `__main__` for debugging, but until now "run the
pipeline" meant knowing which one to call in which order. That is fine for the
person who wrote it and useless for anyone else, which is the whole problem
with a tool nobody but its author can operate.

    python pipeline.py --out generated.xlsx

Order is fixed by real dependencies, not preference:

    parse documents           CG-005 to CG-008
    Topics, Scope, Provenance CG-009    needs the brief
    micro-skills              CG-010    needs the brief, and earlier topics
    questions                 CG-011    needs the micro-skills to link to
    usage and skill mapping   CG-012    needs the questions
    answer key                CG-013    needs the questions
    worked example            CG-014    needs the micro-skills
    write the workbook        CG-022

Micro-skills are generated for every topic before anything else, because the
dependency graph crosses topics: T02.M1 depends on T01.M6, so a topic cannot
be generated until its predecessors exist.

What this does not do
----------------------

No validation. CG-020 owns the 17 blocking checks, and it is not built. A row
that would fail one is still written, deliberately: the file is for looking at,
and a row you cannot see is a row you cannot judge.

Sheets from M4 -- errors, misconceptions, hints, scaffolds -- have no generator
yet. They are written empty rather than omitted, so the gaps are visible in the
file rather than being mistaken for a complete workbook.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Optional

from answer_generator import generate_answers
from brief_mapper import map_all
from docx_parser import parse_all_topic_documents
from id_service import IdService
from llm_client import default_client, is_configured
from micro_skill_generator import REPAIR_PREFIX, generate_all_micro_skills
from question_generator import generate_questions
from reference_check import build_scope_rows
from topic_generator import generate_topic_package
from usage_generator import build_usage_and_skills, plan_phases
from validation import validate_documents
from worked_example_generator import generate_worked_example
from workbook_writer import summarise, verify_written, write_workbook

# Sheets this pipeline can currently fill. The rest exist in the workbook with
# headers and no rows.
GENERATED_SHEETS = (
    "Topics", "Topic_Scope", "Source_Provenance", "Micro_Skills",
    "Questions", "Question_Usage", "Question_MicroSkills", "Answer_Specs",
    "Worked_Examples", "Worked_Example_Steps", "Worked_Example_MicroSkills",
)


def run(
    destination: Path,
    limit: Optional[int] = None,
    strict: bool = True,
    verbose: bool = True,
) -> int:
    """Generate everything and write the workbook. Returns an exit code."""
    def say(message: str = "") -> None:
        if verbose:
            print(message, flush=True)

    started = time.time()
    client = default_client()

    say("Reading topic documents...")
    documents = parse_all_topic_documents()
    problems = [i for i in validate_documents(documents) if i.is_error]
    if problems:
        say("The source documents did not validate:")
        for issue in problems:
            say(f"  {issue}")
        return 1

    briefs = map_all(documents)
    if limit:
        briefs = briefs[:limit]
    say(f"  {len(briefs)} topic(s): {', '.join(b.topic_code for b in briefs)}")

    # One id service per topic, shared across every generator for that topic,
    # so collision detection sees the whole topic rather than one table.
    services = {b.topic_code: IdService(b.topic_code) for b in briefs}

    rows: dict[str, list] = {sheet: [] for sheet in GENERATED_SHEETS}
    failures: list[str] = []

    say("\nGenerating micro-skills for every topic first...")
    say("  (the dependency graph crosses topics, so later ones need earlier ones)")
    skill_sets = generate_all_micro_skills(briefs, client, strict=strict, repair=True)
    for brief, skills in zip(briefs, skill_sets):
        rows["Micro_Skills"].extend(skills.rows)
        say(f"  {brief.topic_code}  {len(skills.rows)} skills")
        for issue in skills.issues:
            if issue.message.startswith(REPAIR_PREFIX):
                say(f"    note: {issue.field}: {issue.message}")

    for brief, skills in zip(briefs, skill_sets):
        code = brief.topic_code
        service = services[code]
        say(f"\n{code}  {brief.topic_title}")

        try:
            package = generate_topic_package(
                next(d for d in documents if d.source_file_name == brief.source_file_name),
                client, strict=strict, id_service=service,
            )
            rows["Topics"].append(package.topic)
            rows["Source_Provenance"].append(package.source_provenance)
            rows["Topic_Scope"].extend(package.scope_items)
            say(f"  topic, {len(package.scope_items)} scope items, provenance")

            questions = generate_questions(
                brief, client, micro_skills=skills.rows,
                source_provenance_id=package.source_provenance.source_provenance_id,
                strict=strict, drop_invalid=True, id_service=service,
            )
            rows["Questions"].extend(questions.rows)
            for issue in questions.issues:
                if not issue.is_error and "dropped" in issue.message:
                    say(f"  note: {issue.message}")
            say(f"  {len(questions.rows)} questions")

            usage = build_usage_and_skills(
                plan_phases(questions.rows), questions.rows,
                questions.skill_links, code, strict=strict, id_service=service,
            )
            rows["Question_Usage"].extend(usage.usage)
            rows["Question_MicroSkills"].extend(usage.skill_map)
            say(f"  {len(usage.usage)} usage rows, {len(usage.skill_map)} skill links")

            answers = generate_answers(
                questions.rows, client, code,
                misconceptions=brief.misconceptions_to_prevent,
                strict=strict, id_service=service,
            )
            rows["Answer_Specs"].extend(answers.rows)
            say(f"  {len(answers.rows)} answer specs")

            example = generate_worked_example(
                brief, client, micro_skills=skills.rows,
                strict=strict, id_service=service,
            )
            if example.example is not None:
                rows["Worked_Examples"].append(example.example)
                rows["Worked_Example_Steps"].extend(example.steps)
                rows["Worked_Example_MicroSkills"].extend(example.skill_map)
                say(f"  worked example, {len(example.steps)} steps")

        except Exception as exc:
            # One topic failing should not lose the others, and it should not
            # lose the workbook either. An earlier version re-raised on a
            # single-topic run to show the traceback, which meant a debugging
            # run produced no file at all -- exactly when seeing the partial
            # output is most useful. The error is reported below instead.
            failures.append(f"{code}: {type(exc).__name__}: {exc}")
            say(f"  FAILED: {type(exc).__name__}: {exc}")

    say(f"\nWriting {destination}...")
    write_workbook(rows, destination)

    structure = verify_written(destination)
    say()
    say(summarise(destination))

    say()
    if structure:
        say("Structure does NOT match the reference:")
        for problem in structure:
            say(f"  {problem}")
    else:
        say("Structure matches the reference workbook.")

    if failures:
        say(f"\n{len(failures)} topic(s) failed:")
        for failure in failures:
            say(f"  {failure}")

    say(f"\nDone in {time.time() - started:.1f}s")
    return 1 if (structure or failures) else 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the Nablix content workbook from topic documents.",
    )
    parser.add_argument(
        "--out", type=Path, default=Path("generated_workbook.xlsx"),
        help="where to write the workbook (default: generated_workbook.xlsx)",
    )
    parser.add_argument(
        "--topics", type=int, default=None, metavar="N",
        help="only the first N topics, for a cheaper run while iterating",
    )
    parser.add_argument(
        "--continue-on-error", action="store_true",
        help="keep going when a generator rejects a model response, instead "
             "of stopping at the first problem",
    )
    parser.add_argument("--quiet", action="store_true", help="print only the summary")
    args = parser.parse_args(argv)

    if not is_configured():
        print(
            "No OpenAI API key found. Set OPENAI_API_KEY (or "
            "NABLIX_OPENAI_API_KEY) in your environment.",
            file=sys.stderr,
        )
        return 2

    return run(
        args.out,
        limit=args.topics,
        strict=not args.continue_on_error,
        verbose=not args.quiet,
    )


if __name__ == "__main__":
    raise SystemExit(main())
