import math
from typing import Any

import numpy as np
import pandas as pd

from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression


# ============================================================
# ML ENGINE
# ============================================================

class AdPilotML:

    def __init__(self):
        self.model = None
        self.model_type = None
        self.trained = False
        self.training_rows = 0

    # ========================================================
    # TRAINING DATA
    # ========================================================

    @staticmethod
    def prepare_training_data(
        rows: list[dict[str, Any]]
    ):

        if not rows:
            return None, None

        dataframe = pd.DataFrame(rows)

        required_columns = [
            "spend",
            "impressions",
            "clicks",
            "conversions",
            "revenue",
        ]

        for column in required_columns:

            if column not in dataframe.columns:
                dataframe[column] = 0

        # Derived features
        dataframe["ctr"] = np.where(
            dataframe["impressions"] > 0,
            dataframe["clicks"]
            / dataframe["impressions"],
            0,
        )

        dataframe["conversion_rate"] = np.where(
            dataframe["clicks"] > 0,
            dataframe["conversions"]
            / dataframe["clicks"],
            0,
        )

        dataframe["roas"] = np.where(
            dataframe["spend"] > 0,
            dataframe["revenue"]
            / dataframe["spend"],
            0,
        )

        features = [
            "spend",
            "impressions",
            "clicks",
            "conversions",
            "ctr",
            "conversion_rate",
        ]

        X = dataframe[features].fillna(0)

        y = dataframe["revenue"].fillna(0)

        return X, y

    # ========================================================
    # TRAIN
    # ========================================================

    def train(
        self,
        rows: list[dict[str, Any]],
    ):

        X, y = self.prepare_training_data(rows)

        if X is None:
            return {
                "trained": False,
                "reason": "No training data."
            }

        if len(X) < 3:
            return {
                "trained": False,
                "reason": "At least 3 data points are recommended."
            }

        # Small datasets benefit from a simple model.
        if len(X) < 25:

            model = LinearRegression()

            self.model_type = "linear_regression"

        else:

            model = RandomForestRegressor(
                n_estimators=100,
                random_state=42,
            )

            self.model_type = "random_forest"

        model.fit(X, y)

        self.model = model
        self.trained = True
        self.training_rows = len(X)

        return {
            "trained": True,
            "model": self.model_type,
            "training_rows": self.training_rows,
        }

    # ========================================================
    # PREDICT
    # ========================================================

    def predict_revenue(
        self,
        spend: float,
        impressions: float,
        clicks: float,
        conversions: float,
    ):

        if not self.trained or self.model is None:
            return {
                "predicted_revenue": None,
                "predicted_roas": None,
                "trained": False,
            }

        ctr = (
            clicks / impressions
            if impressions > 0
            else 0
        )

        conversion_rate = (
            conversions / clicks
            if clicks > 0
            else 0
        )

        X = pd.DataFrame([
            {
                "spend": spend,
                "impressions": impressions,
                "clicks": clicks,
                "conversions": conversions,
                "ctr": ctr,
                "conversion_rate": conversion_rate,
            }
        ])

        prediction = float(
            self.model.predict(X)[0]
        )

        prediction = max(
            0.0,
            prediction,
        )

        roas = (
            prediction / spend
            if spend > 0
            else 0
        )

        return {
            "predicted_revenue": round(
                prediction,
                2,
            ),

            "predicted_roas": round(
                roas,
                4,
            ),

            "trained": True,

            "model": self.model_type,
        }


# ============================================================
# SIMPLE OPPORTUNITY SCORING
# ============================================================

def calculate_opportunity_score(
    expected_roas: float,
    confidence: float,
    sample_size: int,
):

    expected_roas = max(
        0,
        expected_roas,
    )

    confidence = min(
        max(confidence, 0),
        1,
    )

    # More data increases trust but has diminishing returns.
    sample_factor = min(
        1.0,
        math.log10(
            max(sample_size, 1) + 1
        ),
    )

    score = (
        expected_roas
        * confidence
        * sample_factor
    )

    return round(
        score,
        4,
    )


# ============================================================
# GLOBAL ML INSTANCE
# ============================================================

ml_engine = AdPilotML()
