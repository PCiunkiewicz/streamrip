import functools


def get_album_track_ids(resp) -> list[str]:
    return [track["id"] for track in resp["tracks"]]


def safe_get(dictionary, *keys, default=None):
    return functools.reduce(
        lambda d, key: d.get(key, default) if isinstance(d, dict) else default,
        keys,
        dictionary,
    )
