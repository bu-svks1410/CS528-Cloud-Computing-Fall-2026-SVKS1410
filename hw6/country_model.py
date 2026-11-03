from pathlib import Path

import joblib
import pandas as pd
from sklearn.metrics import accuracy_score
from sklearn.tree import DecisionTreeClassifier

from model_utils import RANDOM_SEED, ip_features, split_data


def train_country(frame, output_directory):
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)

    train, validation, test = split_data(frame, "country")

    train_x = ip_features(train)
    validation_x = ip_features(validation)

    candidates = []
    best_score = -1.0
    best_parameters = None

    for depth in (8, 16, None):
        for minimum_leaf in (1, 5):
            parameters = {
                "max_depth": depth,
                "min_samples_leaf": minimum_leaf,
                "random_state": RANDOM_SEED
            }

            model = DecisionTreeClassifier(**parameters)
            model.fit(train_x, train["country"])

            predictions = model.predict(validation_x)
            score = float(
                accuracy_score(validation["country"], predictions)
            )

            candidates.append({
                "max_depth": depth,
                "min_samples_leaf": minimum_leaf,
                "validation_accuracy": score
            })

            print(
                f"Country validation: depth={depth}, "
                f"minimum_leaf={minimum_leaf}, accuracy={score:.4%}",
                flush=True
            )

            if score > best_score:
                best_score = score
                best_parameters = parameters.copy()

    pd.DataFrame(candidates).to_csv(
        output / "country_validation.csv",
        index=False
    )

    development = pd.concat([train, validation], axis=0)

    final_model = DecisionTreeClassifier(**best_parameters)
    final_model.fit(ip_features(development), development["country"])

    predictions = final_model.predict(ip_features(test))
    test_accuracy = float(accuracy_score(test["country"], predictions))

    seen_ip = test["client_ip"].isin(set(development["client_ip"]))

    test_output = pd.DataFrame({
        "request_id": test["request_id"].to_numpy(),
        "client_ip": test["client_ip"].to_numpy(),
        "actual_country": test["country"].to_numpy(),
        "predicted_country": predictions,
        "ip_seen_in_training": seen_ip.to_numpy()
    })

    test_output["correct"] = (
        test_output["actual_country"] == test_output["predicted_country"]
    )

    test_output.to_csv(output / "country_test_predictions.csv", index=False)
    joblib.dump(final_model, output / "country_model.joblib")

    subgroup_results = {}

    for label, mask in (
        ("seen_ips", seen_ip.to_numpy()),
        ("unseen_ips", ~seen_ip.to_numpy())
    ):
        count = int(mask.sum())
        subgroup_results[label] = {
            "test_requests": count,
            "accuracy": (
                float(accuracy_score(test["country"].to_numpy()[mask], predictions[mask]))
                if count else None
            )
        }

    baseline_country = train["country"].value_counts().idxmax()
    baseline_accuracy = float(test["country"].eq(baseline_country).mean())

    metrics = {
        "model": "DecisionTreeClassifier",
        "target": "country",
        "features": list(train_x.columns),
        "random_seed": RANDOM_SEED,
        "training_rows": len(train),
        "validation_rows": len(validation),
        "final_training_rows": len(development),
        "test_rows": len(test),
        "selected_parameters": best_parameters,
        "selected_validation_accuracy": best_score,
        "test_accuracy": test_accuracy,
        "majority_baseline_accuracy": baseline_accuracy,
        "target_accuracy": 0.99,
        "target_met": test_accuracy >= 0.99,
        "ip_overlap_results": subgroup_results
    }

    print(f"Country test accuracy: {test_accuracy:.4%}", flush=True)
    print(f"Country accuracy target met: {metrics['target_met']}", flush=True)

    return metrics
