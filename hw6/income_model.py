from pathlib import Path

import joblib
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from model_utils import RANDOM_SEED, income_features, split_data


def build_pipeline(estimator):
    preprocessing = ColumnTransformer(
        [
            (
                "categories",
                OneHotEncoder(
                    handle_unknown="ignore",
                    sparse_output=False
                ),
                ["country", "gender", "age_group"]
            )
        ],
        remainder="passthrough"
    )

    return Pipeline([
        ("preprocessing", preprocessing),
        ("model", estimator)
    ])


def train_income(frame, output_directory):
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)

    train, validation, test = split_data(frame, "income_group")

    train_x = income_features(train)
    validation_x = income_features(validation)

    candidates = {
        "majority_baseline": DummyClassifier(strategy="most_frequent"),
        "random_forest_leaf_5": RandomForestClassifier(
            n_estimators=200,
            min_samples_leaf=5,
            max_features=0.7,
            n_jobs=2,
            random_state=RANDOM_SEED
        ),
        "random_forest_leaf_20": RandomForestClassifier(
            n_estimators=200,
            min_samples_leaf=20,
            max_features=0.7,
            n_jobs=2,
            random_state=RANDOM_SEED
        ),
        "gradient_boosting_15_leaves": HistGradientBoostingClassifier(
            max_iter=150,
            max_leaf_nodes=15,
            learning_rate=0.1,
            l2_regularization=1.0,
            early_stopping=True,
            random_state=RANDOM_SEED
        ),
        "gradient_boosting_31_leaves": HistGradientBoostingClassifier(
            max_iter=150,
            max_leaf_nodes=31,
            learning_rate=0.1,
            l2_regularization=1.0,
            early_stopping=True,
            random_state=RANDOM_SEED
        )
    }

    validation_results = []
    best_name = None
    best_score = -1.0

    for name, estimator in candidates.items():
        pipeline = build_pipeline(clone(estimator))
        pipeline.fit(train_x, train["income_group"])

        predictions = pipeline.predict(validation_x)
        score = float(
            accuracy_score(validation["income_group"], predictions)
        )

        validation_results.append({
            "model": name,
            "validation_accuracy": score
        })

        print(
            f"Income validation: model={name}, accuracy={score:.4%}",
            flush=True
        )

        if score > best_score:
            best_name = name
            best_score = score

        del pipeline

    pd.DataFrame(validation_results).to_csv(
        output / "income_validation.csv",
        index=False
    )

    development = pd.concat([train, validation], axis=0)

    final_model = build_pipeline(clone(candidates[best_name]))
    final_model.fit(
        income_features(development),
        development["income_group"]
    )

    predictions = final_model.predict(income_features(test))
    test_accuracy = float(
        accuracy_score(test["income_group"], predictions)
    )

    test_output = pd.DataFrame({
        "request_id": test["request_id"].to_numpy(),
        "actual_income": test["income_group"].to_numpy(),
        "predicted_income": predictions
    })

    test_output["correct"] = (
        test_output["actual_income"] == test_output["predicted_income"]
    )

    test_output.to_csv(output / "income_test_predictions.csv", index=False)
    joblib.dump(final_model, output / "income_model.joblib")

    labels = sorted(development["income_group"].unique())

    matrix = confusion_matrix(
        test["income_group"],
        predictions,
        labels=labels
    )

    pd.DataFrame(
        matrix,
        index=pd.Index(labels, name="actual_income"),
        columns=labels
    ).to_csv(output / "income_confusion_matrix.csv")

    report = classification_report(
        test["income_group"],
        predictions,
        labels=labels,
        output_dict=True,
        zero_division=0
    )

    pd.DataFrame(report).transpose().to_csv(
        output / "income_classification_report.csv"
    )

    baseline_income = train["income_group"].value_counts().idxmax()
    baseline_accuracy = float(
        test["income_group"].eq(baseline_income).mean()
    )

    metrics = {
        "model": best_name,
        "target": "income_group",
        "features": list(train_x.columns),
        "random_seed": RANDOM_SEED,
        "training_rows": len(train),
        "validation_rows": len(validation),
        "final_training_rows": len(development),
        "test_rows": len(test),
        "selected_validation_accuracy": best_score,
        "test_accuracy": test_accuracy,
        "majority_baseline_accuracy": baseline_accuracy,
        "target_accuracy": 0.35,
        "target_met": test_accuracy >= 0.35,
        "training_income_counts": {
            str(label): int(count)
            for label, count in train["income_group"].value_counts().items()
        },
        "validation_results": validation_results
    }

    print(f"Selected income model: {best_name}", flush=True)
    print(f"Income test accuracy: {test_accuracy:.4%}", flush=True)
    print(f"Income accuracy target met: {metrics['target_met']}", flush=True)

    return metrics
