import os


def validated_checkpoint_files(checkpoint_folder, shard_names):
    folder = os.path.abspath(checkpoint_folder)
    real_folder = os.path.realpath(folder)
    allowed_targets = [real_folder]
    snapshot = os.path.basename(real_folder)
    snapshots = os.path.dirname(real_folder)
    repository = os.path.dirname(snapshots)

    # Hugging Face snapshots link shard filenames to sibling, hash-named blobs.
    if (
        os.path.basename(snapshots) == "snapshots"
        and os.path.basename(repository).startswith("models--")
        and len(snapshot) == 40
        and all(char in "0123456789abcdef" for char in snapshot)
    ):
        blobs = os.path.join(repository, "blobs")
        if os.path.realpath(blobs) == blobs and os.path.isdir(blobs):
            allowed_targets.append(blobs)

    files = []
    for name in shard_names:
        if not isinstance(name, str) or not name or os.path.isabs(name):
            raise ValueError(
                "Checkpoint shard paths must be relative non-empty strings"
            )
        path = os.path.abspath(os.path.join(folder, name))
        if os.path.commonpath([folder, path]) != folder:
            raise ValueError("Checkpoint shard path escapes its checkpoint directory")
        target = os.path.realpath(path)
        if not any(
            os.path.commonpath([root, target]) == root for root in allowed_targets
        ):
            raise ValueError("Checkpoint shard symlink escapes its checkpoint or cache")
        if not os.path.isfile(target):
            raise ValueError("Checkpoint shards must reference regular files")
        files.append(path)
    return sorted(set(files))
