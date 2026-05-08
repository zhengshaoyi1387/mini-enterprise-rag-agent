from pathlib import Path

from mini_rag.ingestion.manifest import (
    IndexManifest,
    SourceFileState,
    build_source_state,
    detect_index_changes,
)


def test_detect_index_changes_tracks_changed_unchanged_and_deleted(tmp_path: Path):
    keep = tmp_path / "keep.txt"
    changed = tmp_path / "changed.txt"
    keep.write_text("same", encoding="utf-8")
    changed.write_text("new", encoding="utf-8")

    keep_state = build_source_state(keep, tmp_path)
    old_changed = SourceFileState(
        source="changed.txt",
        content_hash="old-hash",
        modified_time=1.0,
        chunk_ids=["old-chunk"],
    )
    manifest = IndexManifest(
        sources={
            "keep.txt": keep_state,
            "changed.txt": old_changed,
            "deleted.txt": SourceFileState(
                source="deleted.txt",
                content_hash="gone",
                modified_time=1.0,
                chunk_ids=["deleted-chunk"],
            ),
        }
    )

    changes = detect_index_changes([keep, changed], tmp_path, manifest)

    assert changes.unchanged_sources == ["keep.txt"]
    assert changes.changed_sources == ["changed.txt"]
    assert changes.deleted_sources == ["deleted.txt"]
    assert changes.chunk_ids_to_delete == ["old-chunk", "deleted-chunk"]

