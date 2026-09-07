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
import re
import sys
import time
from pathlib import Path
from typing import Optional

from answer_generator import generate_answers
from brief_mapper import map_all
from diagnosis_generator import generate_error_types, generate_misconceptions
from scaffold_generator import generate_scaffolds, guided_by_skill
from support_generator import generate_support
from mapping_generator import (
    build_misconception_errors,
    direct_failures,
    generate_question_error_map,
    generate_related_skills,
)
from docx_parser import parse_all_topic_documents
from integrity import check_workbook
from integrity import summarise as summarise_problems
from id_service import IdService
from llm_client import default_client, is_configured
from micro_skill_generator import REPAIR_PREFIX, generate_all_micro_skills
from skill_question_generator import generate_for_topic
from reference_check import build_scope_rows
from topic_generator import generate_topic_package
from usage_generator import UsagePlan, UsageError, build_usage_rows
from validation import validate_documents
from worked_example_generator import generate_worked_example
from workbook_writer import summarise, verify_written, write_workbook

# Sheets this pipeline can currently fill. The rest exist in the workbook with
# headers and no rows.
GENERATED_SHEETS = (
    "Topics", "Topic_Scope", "Source_Provenance", "Micro_Skills",
    "Questions", "Question_Usage", "Question_MicroSkills", "Answer_Specs",
    "Worked_Examples", "Worked_Example_Steps", "Worked_Example_MicroSkills",
    "Error_Types", "Misconceptions",
    "Question_Error_Map", "Misconception_Errors", "Misconception_MicroSkills",
    "Hints", "Misconception_Hints", "Visual_Cues", "Misconception_VisualCues",
    "Parallel_Examples",
    "Scaffolds", "Scaffold_Steps", "Question_Scaffolds",
)


#: How many examples of the same complaint to print before counting the rest.
MAX_NOTES_PER_KIND = 3

#: The specifics of a warning, so two warnings making the same complaint about
#: different rows can be recognised as the same complaint.
_SPECIFICS_RE = re.compile(r"'[^']*'|\"[^\"]*\"|\d+")


def _shape(message: str) -> str:
    """A warning with its particulars removed, for grouping."""
    return _SPECIFICS_RE.sub("#", message)[:80]


def _report(say, issues) -> None:
    """Surface what a generator recovered from, rather than hiding it.

    A dropped row and a repaired field are both successes, but silent ones,
    and a table nobody was told was salvaged reads as authored.

    This used to print only warnings whose text contained one of four
    keywords. That filter was opt-in, so a warning added later was invisible
    until somebody remembered to add its wording to the list, and nobody did:
    the run of 7 September reported three problems while suppressing 134
    warnings saying a question had no diagnosis attached to any of its wrong
    answers. A third of the bank could not diagnose a mistake and the log
    said the workbook was fine.

    So the rule is now the other way round. Every warning prints. The only
    thing suppressed is the fourth and later REPEAT of the same complaint,
    replaced by a count, because the reason the old filter existed was real:
    134 near-identical lines bury the three that are different.
    """
    groups: dict[str, list] = {}
    for issue in issues:
        if not issue.is_error:
            groups.setdefault(_shape(issue.message), []).append(issue)

    for group in groups.values():
        for issue in group[:MAX_NOTES_PER_KIND]:
            say(f"    note: {issue.message}")
        if len(group) > MAX_NOTES_PER_KIND:
            say(f"    note: ... and {len(group) - MAX_NOTES_PER_KIND} more of "
                f"the same ({len(group)} in total)")


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
    #: Skills that did not meet the coverage plan. Not failures -- their
    #: questions are usable -- but the run must not call itself complete.
    incomplete: list[str] = []

    say("\nGenerating micro-skills for every topic first...")
    say("  (the dependency graph crosses topics, so later ones need earlier ones)")
    skill_sets = generate_all_micro_skills(briefs, client, strict=strict, repair=True)
    # Held back rather than written now. A topic whose package fails later
    # never gets a Topics row, and its skills would then point at a topic that
    # does not exist -- which is exactly what happened to T02 on a six-topic
    # run: ten micro-skills left dangling by a failure three steps later.
    skills_by_topic = {}
    for brief, skills in zip(briefs, skill_sets):
        skills_by_topic[brief.topic_code] = skills.rows
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
            # The topic exists, so its skills can be written safely now.
            rows["Topics"].append(package.topic)
            rows["Micro_Skills"].extend(skills_by_topic[code])
            rows["Source_Provenance"].append(package.source_provenance)
            rows["Topic_Scope"].extend(package.scope_items)
            say(f"  topic, {len(package.scope_items)} scope items, provenance")

            # CG-011 rewritten: one call per micro-skill, filling the
            # coverage plan. Phase and difficulty are inputs here, so
            # plan_phases and its heuristic are no longer used at all.
            sets = generate_for_topic(
                brief, skills.rows, client,
                source_provenance_id=package.source_provenance.source_provenance_id,
                strict=strict, id_service=service,
                progress=say if verbose else None,
            )
            questions = [q for s in sets for q in s.rows]
            slots = {qid: sl for s in sets for qid, sl in s.slots.items()}
            skill_map = [m for s in sets for m in s.skill_map]
            for one in sets:
                _report(say, one.issues)

            short = [s for s in sets if not s.is_complete]
            incomplete.extend(
                f"{s.micro_skill_id}: missing {', '.join(str(x) for x in s.missing)}"
                for s in short
            )
            say(f"  {len(questions)} questions over {len(sets)} skills"
                + (f"  ({len(short)} skill(s) below minimum)" if short else ""))

            # The phase of every question is known, so the usage rows are
            # built from fact rather than from a guess about the question's
            # shape. This is what the old plan_phases was standing in for.
            usage_rows, usage_issues = build_usage_rows(
                [
                    UsagePlan(q.question_id, slots[q.question_id].phase,
                              role=slots[q.question_id].role)
                    for q in questions
                ],
                questions, code, service,
            )
            usage_errors = [i for i in usage_issues if i.is_error]
            if usage_errors and strict:
                raise UsageError(
                    f"{code}: usage rows could not be built.\n"
                    + "\n".join(f"  {i}" for i in usage_errors)
                )

            answers = generate_answers(
                questions, client, code,
                misconceptions=brief.misconceptions_to_prevent,
                strict=strict, drop_invalid=True, id_service=service,
            )
            _report(say, answers.issues)

            # A question whose answer could not be trusted is removed from
            # every sheet that refers to it, not just from the answer key.
            # These rows are held back until now precisely so this is a
            # filter rather than a retraction: leaving a question in the bank
            # with no key would look complete and be unusable.
            gone = answers.dropped_question_ids
            rows["Questions"].extend(
                q for q in questions if q.question_id not in gone)
            rows["Question_Usage"].extend(
                u for u in usage_rows if u.question_id not in gone)
            rows["Question_MicroSkills"].extend(
                m for m in skill_map if m.question_id not in gone)
            rows["Answer_Specs"].extend(answers.rows)

            if gone:
                # Dropping a question can take a slot with it, so coverage is
                # recomputed against what actually survives rather than what
                # the generator returned.
                for one in sets:
                    lost = [q for q in one.rows if q.question_id in gone]
                    if lost:
                        incomplete.append(
                            f"{one.micro_skill_id}: {len(lost)} question(s) "
                            f"dropped with their answers"
                        )

            say(f"  {len(usage_rows) - len(gone)} usage rows, "
                f"{len(answers.rows)} answer specs"
                + (f"  ({len(gone)} question(s) dropped with their answers)"
                   if gone else ""))

            example = generate_worked_example(
                brief, client, micro_skills=skills.rows,
                strict=strict, id_service=service,
            )
            if example.example is not None:
                rows["Worked_Examples"].append(example.example)
                rows["Worked_Example_Steps"].extend(example.steps)
                rows["Worked_Example_MicroSkills"].extend(example.skill_map)
                say(f"  worked example, {len(example.steps)} steps")

            # CG-015. Errors first: a misconception's diagnosis_rule names
            # error codes in prose, so they have to exist before it is written.
            error_types = generate_error_types(
                brief, client, micro_skills=skills.rows,
                strict=strict, drop_invalid=True, id_service=service,
            )
            rows["Error_Types"].extend(error_types.rows)
            _report(say, error_types.issues)
            say(f"  {len(error_types.rows)} error types")

            misconceptions = generate_misconceptions(
                brief, client, error_types=error_types.rows,
                strict=strict, drop_invalid=True, id_service=service,
            )
            rows["Misconceptions"].extend(misconceptions.rows)
            _report(say, misconceptions.issues)
            say(f"  {len(misconceptions.rows)} misconceptions")

            # CG-016. Two of these three tables are derived rather than
            # generated -- see mapping_generator -- so this adds one model
            # call per topic, not three.
            linked, link_issues = build_misconception_errors(
                misconceptions.rows, error_types.rows, f"{code} misconception errors")
            _report(say, link_issues)
            rows["Misconception_Errors"].extend(linked)

            broken = direct_failures(linked, error_types.rows)
            related, related_issues, _ = generate_related_skills(
                misconceptions.rows, skills.rows, broken, client, code,
                strict=strict,
            )
            _report(say, related_issues)
            rows["Misconception_MicroSkills"].extend(broken + related)

            # The question's one skill, so the error map never has to ask.
            skill_of_question = {
                m.question_id: m.micro_skill_id for m in skill_map
                if m.question_id not in gone
            }
            say("    labelling wrong answers with their errors...")
            error_map, map_issues, _ = generate_question_error_map(
                [a for a in answers.rows], 
                [q for q in questions if q.question_id not in gone],
                error_types.rows, client, code,
                skill_of_question=skill_of_question, strict=strict,
            )
            _report(say, map_issues)
            rows["Question_Error_Map"].extend(error_map)

            say(f"  {len(linked)} misconception-error links, "
                f"{len(broken) + len(related)} skill links, "
                f"{len(error_map)} wrong answers mapped")

            # CG-017. Five tables, three calls: both joins are derived.
            say("    hints, visual cues, parallel examples...")
            support = generate_support(
                misconceptions.rows, client, code, brief.topic_id,
                id_service=service, strict=strict,
            )
            _report(say, support.issues)
            rows["Hints"].extend(support.hints)
            rows["Misconception_Hints"].extend(support.hint_links)
            rows["Visual_Cues"].extend(support.visual_cues)
            rows["Misconception_VisualCues"].extend(support.cue_links)
            rows["Parallel_Examples"].extend(support.parallel_examples)
            say(f"  {len(support.hints)} hints, "
                f"{len(support.visual_cues)} visual cues, "
                f"{len(support.parallel_examples)} parallel examples")

            # CG-018. One scaffold per skill, serving that skill's guided
            # questions. Runs after CG-017 because a step falls back to a
            # hint or a cue, and those ids have to exist to be checked.
            guided = guided_by_skill(
                [q for q in questions if q.question_id not in gone],
                slots, skill_of_question,
            )
            if guided:
                say("    scaffolds...")
                scaffolding = generate_scaffolds(
                    skills.rows, guided, support.hints, support.visual_cues,
                    client, code, id_service=service, strict=strict,
                )
                _report(say, scaffolding.issues)
                rows["Scaffolds"].extend(scaffolding.scaffolds)
                rows["Scaffold_Steps"].extend(scaffolding.steps)
                rows["Question_Scaffolds"].extend(scaffolding.links)
                say(f"  {len(scaffolding.scaffolds)} scaffolds, "
                    f"{len(scaffolding.steps)} steps, "
                    f"{len(scaffolding.links)} questions covered")

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
        say("Structure does NOT match the platform template:")
        for problem in structure:
            say(f"  {problem}")
    else:
        say("Structure matches the platform template.")

    if failures:
        say(f"\n{len(failures)} topic(s) failed:")
        for failure in failures:
            say(f"  {failure}")

    # A shortfall is not a failure -- the questions that exist are usable and
    # the workbook is worth looking at -- but the run must not report success.
    # The review is explicit: "if any required micro-skill/phase/difficulty
    # combination is below the minimum, generation should be marked
    # incomplete". Exiting 0 here would let a partial bank travel as a
    # finished one.
    # CG-019. The file is what the platform imports, so it is checked as a
    # file rather than trusted from the generators that wrote it.
    problems = check_workbook(destination)
    say()
    say(summarise_problems(problems))

    if incomplete:
        say(f"\n{len(incomplete)} micro-skill(s) below the coverage minimum:")
        for gap in incomplete:
            say(f"  {gap}")
        say("  The workbook is written and reviewable, but this run is "
            "INCOMPLETE.")

    say(f"\nDone in {time.time() - started:.1f}s")
    return 1 if (structure or failures or incomplete or problems) else 0


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
