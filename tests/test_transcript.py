import json

from buddy import transcript


def entry(text, kind="user"):
    return json.dumps({"type": kind, "message": {"role": kind, "content": [{"type": "text", "text": text}]}}) + "\n"


def test_spots_an_interrupt_written_after_the_prompt(tmp_path):
    log = tmp_path / "session.jsonl"
    log.write_text(entry("old turn") + entry("[Request interrupted by user]"))  # an earlier turn's interrupt
    watch = transcript.watch(str(log))
    assert watch.interrupted() is False
    with log.open("a") as f:
        f.write(entry("thinking about it", kind="assistant"))
    assert watch.interrupted() is False
    with log.open("a") as f:
        f.write(entry("[Request interrupted by user for tool use]"))
    assert watch.interrupted() is True


def test_waits_for_the_rest_of_a_half_written_line(tmp_path):
    log = tmp_path / "session.jsonl"
    log.write_text("")
    watch = transcript.watch(str(log))
    line = entry("[Request interrupted by user]")
    with log.open("a") as f:
        f.write(line[:20])
    assert watch.interrupted() is False
    with log.open("a") as f:
        f.write(line[20:])
    assert watch.interrupted() is True


def test_the_marker_inside_other_text_does_not_count(tmp_path):
    log = tmp_path / "session.jsonl"
    log.write_text("")
    watch = transcript.watch(str(log))
    with log.open("a") as f:
        f.write(entry("why does it say [Request interrupted by user] here?"))
        f.write(entry("[Request interrupted by user]", kind="assistant"))
        f.write(json.dumps({"type": "user", "message": {"content": "[Request interrupted by user]"}}) + "\n")
        f.write("[Request interrupted by user] not json\n")
    assert watch.interrupted() is False


def test_a_transcript_created_after_the_prompt_is_read_from_the_start(tmp_path):
    log = tmp_path / "session.jsonl"
    watch = transcript.watch(str(log))
    assert watch.interrupted() is False
    log.write_text(entry("[Request interrupted by user]"))
    assert watch.interrupted() is True


def test_a_huge_line_is_skipped_without_buffering_it(tmp_path):
    log = tmp_path / "session.jsonl"
    log.write_text("")
    watch = transcript.watch(str(log))
    with log.open("a") as f:
        f.write('{"type": "user", "pasted": "' + "x" * (transcript.MAX_LINE * 2))
    assert watch.interrupted() is False
    with log.open("a") as f:
        f.write('"}\n' + entry("[Request interrupted by user]"))
    assert watch.interrupted() is True


def test_only_absolute_jsonl_paths_are_watched(tmp_path):
    assert transcript.watch("") is None
    assert transcript.watch("session.jsonl") is None
    assert transcript.watch(str(tmp_path / "notes.txt")) is None
    assert transcript.watch(str(tmp_path / "session.jsonl")) is not None
