import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

RANDOM_SEED = 528


def split_data(frame, target):
    development, test = train_test_split(
        frame,
        test_size=0.20,
        random_state=RANDOM_SEED,
        stratify=frame[target]
    )

    train, validation = train_test_split(
        development,
        test_size=0.25,
        random_state=RANDOM_SEED,
        stratify=development[target]
    )

    groups = [
        set(part["request_id"])
        for part in (train, validation, test)
    ]

    if any(
        groups[left] & groups[right]
        for left, right in ((0, 1), (0, 2), (1, 2))
    ):
        raise ValueError("Request IDs overlap between data splits")

    if sum(len(part) for part in (train, validation, test)) != len(frame):
        raise ValueError("Data split sizes do not match the source")

    return train.copy(), validation.copy(), test.copy()


def ip_features(frame):
    octets = frame["client_ip"].str.split(".", expand=True).astype("int64")
    octets.columns = ["ip_1", "ip_2", "ip_3", "ip_4"]

    result = octets.copy()
    result["ip_number"] = (
        octets["ip_1"] * 16777216
        + octets["ip_2"] * 65536
        + octets["ip_3"] * 256
        + octets["ip_4"]
    )

    return result


def income_features(frame):
    result = frame[["country", "gender", "age_group"]].copy()
    result = pd.concat([result, ip_features(frame)], axis=1)

    hours = frame["client_time"].dt.hour
    result["client_hour"] = hours
    result["hour_sin"] = np.sin(2 * np.pi * hours / 24)
    result["hour_cos"] = np.cos(2 * np.pi * hours / 24)

    result["file_number"] = pd.to_numeric(
        frame["requested_file"].str.extract(
            r"(?:^|/)(\d+)\.html$",
            expand=False
        ),
        errors="coerce"
    ).fillna(-1)

    return result
